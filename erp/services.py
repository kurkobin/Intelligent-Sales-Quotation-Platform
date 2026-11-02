# -*- coding: utf-8 -*-
"""同步服务：把 ERP 三张主数据全量 upsert 进本地表。

约定：
* 全部是「查一次 → 逐条 upsert」，重复跑不会产生重复数据（幂等）；
* 成功失败都返回 SyncResult，不把异常抛给命令/按钮 —— 上层只负责展示；
* 一次 sync_all 复用同一个 Client，只登录一次；连接失败时后面的实体不再重试，
  避免把「重试 3 次」变成「重试 9 次」。
"""

import time
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from masterdata.models import ExchangeRate, ItemMaster, Supplier

from .adapters import get_adapter
from .client import ErpError

SYNC_TARGETS = ("rates", "suppliers", "items")
LABELS = {"rates": "汇率", "suppliers": "供应商", "items": "料号"}
BASE_CURRENCY = "RMB"


@dataclass
class SyncResult:
    entity: str
    label: str
    ok: bool = True
    created: int = 0
    updated: int = 0
    fetched: int = 0
    skipped: int = 0
    error: str = ""
    elapsed_ms: int = 0

    @property
    def total(self):
        """实际写进本地表的条数。"""
        return self.created + self.updated

    @property
    def summary(self):
        if not self.ok:
            return f"{self.label} 同步失败：{self.error}"
        text = f"{self.label}：新增 {self.created}／更新 {self.updated}／共 {self.fetched} 条"
        if self.skipped:
            text += f"（跳过 {self.skipped} 条：缺料号或名称）"
        return text

    @property
    def short(self):
        return f"{self.label} {self.fetched}"


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def get_client(adapter=None):
    adapter = adapter or get_adapter()
    return getattr(adapter, "client", None)


def _login_once(adapter):
    """有 HTTP 客户端就先登录（幂等）；离线适配器没有 client，直接跳过。"""
    client = get_client(adapter)
    if client is not None:
        client.login()
    return adapter


def sync_rates(adapter=None):
    adapter = adapter or get_adapter()
    return _sync("rates", "汇率", adapter, adapter.fetch_rates, _upsert_rates)


def sync_suppliers(adapter=None):
    adapter = adapter or get_adapter()
    return _sync("suppliers", "供应商", adapter, adapter.fetch_suppliers, _upsert_suppliers)


def sync_items(adapter=None):
    adapter = adapter or get_adapter()
    return _sync("items", "料号", adapter, adapter.fetch_items, _upsert_items)


def sync_all(adapter=None):
    """按 汇率 → 供应商 → 料号 顺序同步；第一个失败后其余标记「跳过」。"""
    adapter = adapter or get_adapter()
    try:
        _login_once(adapter)  # 只登一次；连不上就直接整批标记失败，免得每张表都重试 3 次
    except ErpError as exc:
        # 登录都没成功：第一张表报真实原因，其余说明为什么没跑，不重复三遍长错误
        results = {}
        for index, entity in enumerate(SYNC_TARGETS):
            error = exc.message if index == 0 else f"未执行（{LABELS[SYNC_TARGETS[index - 1]]}同步失败）"
            results[entity] = SyncResult(entity=entity, label=LABELS[entity], ok=False, error=error)
        return results

    results = {}
    failure = ""
    for entity in SYNC_TARGETS:
        if failure:
            results[entity] = SyncResult(
                entity=entity, label=LABELS[entity], ok=False,
                error=f"未执行（前面的 {LABELS[SYNC_TARGETS[SYNC_TARGETS.index(entity) - 1]]} 同步已失败）",
            )
            continue
        result = _sync(entity, LABELS[entity], adapter,
                       getattr(adapter, f"fetch_{entity}"),
                       {"rates": _upsert_rates, "suppliers": _upsert_suppliers,
                        "items": _upsert_items}[entity])
        results[entity] = result
        if not result.ok:
            failure = result.error
    return results


def sync_one(what, adapter=None):
    """管理命令和后台按钮共用：what 取 rates/suppliers/items/all。"""
    what = (what or "all").lower()
    if what == "all":
        return sync_all(adapter)
    if what not in SYNC_TARGETS:
        raise ValueError(f"未知同步对象：{what}（可选 rates/suppliers/items/all）")
    adapter = adapter or get_adapter()
    try:
        _login_once(adapter)
    except ErpError as exc:
        return {what: SyncResult(entity=what, label=LABELS[what], ok=False, error=exc.message)}
    return {what: _sync(what, LABELS[what], adapter,
                        getattr(adapter, f"fetch_{what}"),
                        {"rates": _upsert_rates, "suppliers": _upsert_suppliers,
                         "items": _upsert_items}[what])}


def test_connection(adapter=None):
    """返回 {"ok", "message", "elapsed_ms"}，不抛异常。"""
    started = time.monotonic()
    try:
        adapter = adapter or get_adapter()
        info = adapter.test_connection()
        elapsed = info.get("elapsed_ms") or int((time.monotonic() - started) * 1000)
        return {"ok": True, "message": info.get("message") or "连接成功", "elapsed_ms": elapsed}
    except ErpError as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        return {"ok": False, "message": exc.message, "elapsed_ms": elapsed}
    except Exception as exc:  # 兜底：不让页面/命令因为意外异常而 500
        elapsed = int((time.monotonic() - started) * 1000)
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}", "elapsed_ms": elapsed}


# --------------------------------------------------------------------------
# 通用流程
# --------------------------------------------------------------------------
def _sync(entity, label, adapter, fetch, upsert):
    result = SyncResult(entity=entity, label=label)
    started = time.monotonic()
    try:
        records = fetch()
    except ErpError as exc:
        result.ok = False
        result.error = exc.message
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        return result
    except Exception as exc:
        result.ok = False
        result.error = f"{type(exc).__name__}: {exc}"
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        return result

    result.fetched = len(records)
    now = timezone.now()
    try:
        with transaction.atomic():
            for record in records:
                outcome = upsert(record, now)
                if outcome == "created":
                    result.created += 1
                elif outcome == "updated":
                    result.updated += 1
                else:
                    result.skipped += 1
    except Exception as exc:
        result.ok = False
        result.error = f"写入本地库失败：{type(exc).__name__}: {exc}"
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


# --------------------------------------------------------------------------
# 三张表各自的 upsert 规则
# --------------------------------------------------------------------------
def _upsert_rates(record, now):
    currency = record.get("currency")
    if not currency:
        return "skipped"
    _, created = ExchangeRate.objects.update_or_create(
        year=record["year"], base_currency=BASE_CURRENCY, currency=currency,
        defaults={"rate": record["rate"], "erp_id": record.get("erp_id", ""), "synced_at": now},
    )
    return "created" if created else "updated"


def _upsert_suppliers(record, now):
    target = _match_supplier(record)
    fields = {
        "erp_id": record.get("erp_id", ""),
        "number": record.get("number", ""),
        "name": record["name"],
        "contact": record.get("contact", ""),
        "email": record.get("email", ""),
        "status": "启用" if record.get("is_active", True) else "停用",
        "synced_at": now,
    }
    if target is None:
        Supplier.objects.create(**fields)
        return "created"
    for key, value in fields.items():
        setattr(target, key, value)
    target.save(update_fields=list(fields.keys()))
    return "updated"


def _match_supplier(record):
    """按内码 → 编码 → 同名旧数据 的顺序认领，避免第一次对接时重复插入。"""
    if record.get("erp_id"):
        found = Supplier.objects.filter(erp_id=record["erp_id"]).first()
        if found:
            return found
    if record.get("number"):
        found = Supplier.objects.filter(number=record["number"]).first()
        if found:
            return found
    # 平台里手工维护过、还没有 erp_id 的同名供应商：直接认领
    return Supplier.objects.filter(name=record["name"], erp_id="").first()


def _upsert_items(record, now):
    number = record.get("number")
    if not number or not record.get("name"):
        return "skipped"
    target = ItemMaster.objects.filter(number=number).first()
    fields = {
        "erp_id": record.get("erp_id", ""),
        "name": record["name"],
        "spec": record.get("spec", ""),
        "unit": record.get("unit", ""),
        "material": record.get("material", ""),
        "category": record.get("category", ""),
        "is_active": record.get("is_active", True),
        "synced_at": now,
    }
    if target is None:
        ItemMaster.objects.create(number=number, **fields)
        return "created"
    for key, value in fields.items():
        setattr(target, key, value)
    target.save(update_fields=list(fields.keys()))
    return "updated"