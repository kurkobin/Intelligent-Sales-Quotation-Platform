# -*- coding: utf-8 -*-
"""ERP 适配器的抽象契约。

上层 services 只认这套接口：
    换 ERP 就换一个实现（kingdee.py / 别的厂商.py），
    services、models、后台页面一行都不用改。
"""

from abc import ABC, abstractmethod


class BaseErpAdapter(ABC):
    """一次 sync 用的适配器：只管「把 ERP 的报文翻译成我们的字典」。"""

    name = "base"
    form_rates = ""
    form_suppliers = ""
    form_items = ""

    @abstractmethod
    def fetch_rates(self):
        """返回 [{"erp_id", "currency", "rate", "year"}, ...]"""

    @abstractmethod
    def fetch_suppliers(self):
        """返回 [{"erp_id", "number", "name", "contact", "email", "is_active"}, ...]"""

    @abstractmethod
    def fetch_items(self):
        """返回 [{"erp_id", "number", "name", "spec", "unit",
                 "material", "category", "is_active"}, ...]"""

    @abstractmethod
    def test_connection(self):
        """返回 {"ok": bool, "message": str, "elapsed_ms": int}"""


# --------------------------------------------------------------------------
# 各适配器共用的取值工具
# --------------------------------------------------------------------------
def text_of(value):
    """金蝶的字段可能是字符串、基础资料对象、或 [Id, Number, Name] 数组。

    统一成字符串：对象按 FName → FNumber → Name → Number 取第一个非空；
    数组从后往前找第一个能取到值的（金蝶习惯把显示名放最后）。
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("FName", "FNumber", "Name", "Number", "FNumber_Name"):
            candidate = value.get(key)
            if candidate not in (None, ""):
                return str(candidate).strip()
        return ""
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            text = text_of(item)
            if text:
                return text
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).strip()


def number_of(value):
    """取基础资料的「编码」而不是「名称」——币别要的是 USD，不是「美元」。

    text_of 优先 FName（适合名称类字段）；这个函数优先 FNumber。
    """
    if isinstance(value, dict):
        for key in ("FNumber", "Number", "FName", "Name"):
            candidate = value.get(key)
            if candidate not in (None, ""):
                return str(candidate).strip()
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:  # 金蝶 [Id, Number, Name] 习惯：编码在前
            text = number_of(item)
            if text:
                return text
        return ""
    return text_of(value)


def is_active_of(record):
    """金蝶用 FForbidStatus 表示禁用（B=禁用，A=可用）。字段缺失时按可用处理。"""
    status = text_of(record.get("FForbidStatus")).upper()
    return status not in ("B", "U", "禁用", "停用")


def year_of(date_text, default):
    """从 FBeginDate（2026-01-01）取年份。"""
    text = text_of(date_text)
    head = text[:4]
    return int(head) if head.isdigit() else default