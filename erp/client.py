# -*- coding: utf-8 -*-
"""金蝶 K/3 Cloud WebAPI 客户端。

只做四件事：登录换 Cookie、带 Cookie 查询、超时/重试、把每次调用写进 ErpLog。

刻意用标准库 urllib 而不是 requests —— 项目依赖里没有 requests，
少一个依赖就少一次「换台机器装不上」的概率；Cookie 用 http.cookiejar 管理。

将来接真金蝶，配置都从 settings.ERP_* 来，这段代码不用动。
"""

import json
import socket
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

from django.conf import settings

from .models import ErpLog

AUTH_PATH = "/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
QUERY_PATH = "/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
LCID = 2052  # 简体中文，金蝶 ValidateUser 的第 4 个参数


# --------------------------------------------------------------------------
# 异常：message 都是能直接展示给用户的话
# --------------------------------------------------------------------------
class ErpError(Exception):
    def __init__(self, message, detail="", retryable=False):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.retryable = retryable


class ErpConnectionError(ErpError):
    """连不上、超时、5xx —— 可重试。"""


class ErpAuthError(ErpError):
    """登录失败或会话失效 —— 重试无意义。"""


class ErpQueryError(ErpError):
    """请求本身有问题（表单 ID 错、字段名错、权限不足）。"""


def _net_error_message(exc):
    """把底层网络异常翻译成看得懂的中文。"""
    reason = getattr(exc, "reason", None) or exc
    text = str(reason)

    if isinstance(reason, socket.timeout) or isinstance(exc, socket.timeout) or "timed out" in text.lower():
        return "连接超时（ERP 无响应）"
    if isinstance(reason, ConnectionRefusedError) or "10061" in text or "refused" in text.lower():
        return "连接被拒绝：目标端口没有服务在监听"
    if "11001" in text or "getaddrinfo" in text or "Name or service not known" in text:
        return "无法解析主机名（检查 ERP_BASE_URL）"
    if isinstance(reason, ConnectionResetError) or "10054" in text:
        return "连接被对端重置"
    if "10060" in text:
        return "网络不可达或连接超时"
    return text or exc.__class__.__name__


class KingdeeClient:
    """一个实例 = 一个登录会话；一次 sync 复用同一个实例，避免反复登录。"""

    def __init__(self, base_url="", acct_id="", user="", password="",
                 timeout=30, max_attempts=3, retry_delays=(1, 2, 4), log=True):
        self.base_url = (base_url or "").rstrip("/")
        self.acct_id = acct_id
        self.user = user
        self.password = password
        self.timeout = int(timeout or 30)
        self.max_attempts = max(int(max_attempts or 1), 1)
        self.retry_delays = tuple(retry_delays or ())
        self.log = log

        self._cookiejar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookiejar)
        )
        self._logged_in = False

    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, **overrides):
        kwargs = dict(
            base_url=getattr(settings, "ERP_BASE_URL", ""),
            acct_id=getattr(settings, "ERP_ACCT_ID", ""),
            user=getattr(settings, "ERP_USER", ""),
            password=getattr(settings, "ERP_PASSWORD", ""),
            timeout=getattr(settings, "ERP_TIMEOUT", 30),
            max_attempts=getattr(settings, "ERP_MAX_ATTEMPTS", 3),
            retry_delays=getattr(settings, "ERP_RETRY_DELAYS", (1, 2, 4)),
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    @property
    def mode(self):
        return getattr(settings, "ERP_MODE", "mock")

    # ------------------------------------------------------------------
    # 登录 / 查询
    # ------------------------------------------------------------------
    def login(self, force=False):
        """ValidateUser 换 kdservice-sessionid Cookie；已登录则跳过。"""
        if self._logged_in and not force:
            return True

        payload = {"parameters": [self.acct_id, self.user, self.password, LCID], "format": "json"}
        self._request(AUTH_PATH, payload, action="login", entity="", fail_cls=ErpAuthError)
        self._logged_in = True
        return True

    def query(self, form_id, field_keys, filter_string="", order_string="",
              top_row_count=0, start_row=0, limit=2000):
        """ExecuteBillQuery → 二维数组；会话失效时自动重登并重试一次。"""
        try:
            return self._query_once(form_id, field_keys, filter_string, order_string,
                                    top_row_count, start_row, limit)
        except ErpAuthError:
            self._logged_in = False
            self.login(force=True)
            return self._query_once(form_id, field_keys, filter_string, order_string,
                                    top_row_count, start_row, limit)

    def _query_once(self, form_id, field_keys, filter_string, order_string,
                    top_row_count, start_row, limit):
        params = {
            "FieldKeys": field_keys,
            "FilterString": filter_string,
            "OrderString": order_string,
            "TopRowCount": top_row_count,
            "StartRow": start_row,
            "Limit": limit,
        }
        data = self._request(QUERY_PATH, {"parameters": [form_id, params]},
                             action="query", entity=form_id)

        if isinstance(data, dict):
            raise ErpQueryError(_extract_erp_error(data) or f"{form_id} 查询返回了非数组结构")
        if not isinstance(data, list):
            raise ErpQueryError(f"{form_id} 查询返回结构无法识别：{type(data).__name__}")
        return data

    # ------------------------------------------------------------------
    # 底层：一次请求 + 重试 + 日志
    # ------------------------------------------------------------------
    def _request(self, path, payload, action, entity, fail_cls=ErpQueryError):
        if not self.base_url:
            raise ErpConnectionError("未配置 ERP_BASE_URL，请检查 .env")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "IntelligentQuotation/1.0 (KingdeeClient)",
        }
        url = self._url(path)
        attempt = 0
        last_reason = ""

        while True:
            attempt += 1
            started = time.monotonic()
            status = None
            text = None
            transport_error = ""

            try:
                request = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with self._opener.open(request, timeout=self.timeout) as response:
                    status = response.status
                    text = response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                status = exc.code
                try:
                    text = exc.read().decode("utf-8", "replace")
                except Exception:
                    text = ""
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
                transport_error = _net_error_message(exc)

            duration = int((time.monotonic() - started) * 1000)

            # ---- 网络层失败：重试 ----
            if transport_error:
                last_reason = transport_error
                self._log(action, entity, self._safe_payload(payload), {}, ok=False,
                          error=last_reason, duration_ms=duration)
                if attempt >= self.max_attempts:
                    raise ErpConnectionError(
                        f"连接失败，已重试 {attempt} 次：{last_reason}", retryable=True)
                self._sleep_before_retry(attempt)
                continue

            data = None
            try:
                data = json.loads(text) if text and text.strip() else None
            except json.JSONDecodeError:
                data = None

            # ---- 401：会话失效，交给上层重登 ----
            if status == 401:
                message = _extract_erp_error(data) or "会话已失效，请重新登录"
                self._log(action, entity, self._safe_payload(payload),
                          {"http_status": 401, "body": (text or "")[:500]}, ok=False,
                          error=message, duration_ms=duration)
                self._logged_in = False
                raise ErpAuthError(message)

            # ---- 5xx：服务端故障，可重试 ----
            if status is not None and status >= 500:
                last_reason = f"ERP 服务端错误（HTTP {status}）"
                self._log(action, entity, self._safe_payload(payload),
                          {"http_status": status, "body": (text or "")[:500]}, ok=False,
                          error=last_reason, duration_ms=duration)
                if attempt >= self.max_attempts:
                    raise ErpConnectionError(
                        f"连接失败，已重试 {attempt} 次：{last_reason}", retryable=True)
                self._sleep_before_retry(attempt)
                continue

            # ---- 其它非 200：不可重试 ----
            if status != 200:
                message = _extract_erp_error(data) or f"ERP 返回 HTTP {status}"
                self._log(action, entity, self._safe_payload(payload),
                          {"http_status": status, "body": (text or "")[:500]}, ok=False,
                          error=message, duration_ms=duration)
                raise fail_cls(message)

            # ---- 200：按业务结构判定成败 ----
            ok, error = self._judge(data)
            self._log(action, entity, self._safe_payload(payload), _summarize(data),
                      ok=ok, error=error, duration_ms=duration)
            if not ok:
                raise fail_cls(error)
            return data

    def _judge(self, data):
        if isinstance(data, dict):
            if "LoginResultType" in data:
                if int(data.get("LoginResultType") or 0) != 1:
                    return False, data.get("Message") or "登录失败"
                return True, ""
            message = _extract_erp_error(data)
            if message:
                return False, message
        return True, ""

    def _sleep_before_retry(self, attempt):
        if not self.retry_delays:
            return
        delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
        if delay:
            time.sleep(delay)

    def _url(self, path):
        return f"{self.base_url}{path}"

    # ------------------------------------------------------------------
    def _safe_payload(self, payload):
        """落日志前把密码抹掉。"""
        params = list(payload.get("parameters") or [])
        if self.password in params:
            params[params.index(self.password)] = "***"
        for index, item in enumerate(params):
            if isinstance(item, dict) and "FilterString" in item:
                params[index] = dict(item)
        return {"parameters": params, "format": payload.get("format")}

    def _log(self, action, entity, request, response, ok, error="", duration_ms=0):
        if not self.log:
            return
        try:
            ErpLog.objects.create(
                action=action,
                entity=entity or "",
                request=request or {},
                response=response or {},
                ok=ok,
                error=(error or "")[:2000],
                duration_ms=int(duration_ms or 0),
            )
        except Exception:
            # 日志写不进去（没迁移、数据库锁）不能影响同步本身
            pass


def _extract_erp_error(data):
    """从金蝶的 Result.ResponseStatus.Errors 里抠出错误信息。"""
    if not isinstance(data, dict):
        return ""
    try:
        errors = data["Result"]["ResponseStatus"]["Errors"] or []
    except (KeyError, TypeError):
        errors = []

    messages = []
    for item in errors:
        if isinstance(item, dict):
            text = item.get("Message") or item.get("message")
            if text:
                messages.append(str(text))
        elif item:
            messages.append(str(item))
    if messages:
        return "；".join(messages)

    message = data.get("Message") or data.get("message")
    return str(message) if message else ""


def _summarize(data):
    """日志里不存全量报文（可能上万行），只存形状 + 前两条样本。"""
    if isinstance(data, list):
        return {"type": "array", "rows": len(data), "sample": data[:2]}
    if isinstance(data, dict):
        slim = {k: v for k, v in data.items()
                if k in ("LoginResultType", "Message", "KDSVCSessionId", "Result")}
        if "KDSVCSessionId" in slim:
            slim["KDSVCSessionId"] = "***"
        return slim or {"type": "object"}
    return {"type": type(data).__name__}