# -*- coding: utf-8 -*-
"""金蝶 K/3 Cloud 的适配器 —— 真接 ERP 时，主要改这个文件。

字段名都来自金蝶星空公开的 BD_* 表单；如果贵司的字段做过自定义，
把下面的 FIELDS 里的 FieldKeys 和 fetch_* 里的取值键一起改掉即可。
"""

import time
from datetime import date
from decimal import Decimal, InvalidOperation

from ..client import KingdeeClient
from .base import BaseErpAdapter, is_active_of, text_of, year_of

# FieldKeys 的顺序 = 查询返回二维数组的列顺序，必须一一对应
RATE_FIELDS = "FExchangeRateId,FCurrencyId.FNumber,FExchangeRate,FBeginDate,FRateTypeId.FNumber"
SUPPLIER_FIELDS = "FSupplierId,FNumber,FName,FContact,FEmail,FForbidStatus"
ITEM_FIELDS = (
    "FMATERIALID,FNumber,FName,FSpecification,"
    "FBaseUnitId.FName,FMaterialGroup.FName,FMaterial.FName,FErpClsID,FForbidStatus"
)
CUSTOMER_FIELDS = (
    "FCUSTID,FNumber,FName,FContact,FPhone,FEmail,"
    "FSettleCurrId.FNumber,FCreditLimit,FForbidStatus"
)

# 金蝶即期汇率的汇率类型编码
SPOT_RATE_TYPE = "001"


class KingdeeAdapter(BaseErpAdapter):
    name = "kingdee"
    form_rates = "BD_ExchangeRate"
    form_suppliers = "BD_Supplier"
    form_items = "BD_MATERIAL"
    form_customers = "BD_Customer"

    def __init__(self, client=None):
        self.client = client or KingdeeClient.from_settings()

    # ------------------------------------------------------------------
    def _records(self, form_id, field_keys):
        """查询 + 把二维数组按 FieldKeys 顺序还原成字典列表。"""
        keys = [key.strip() for key in field_keys.split(",")]
        rows = self.client.query(form_id, field_keys)
        records = []
        for row in rows:
            if not isinstance(row, (list, tuple)):
                continue
            records.append(dict(zip(keys, row)))
        return records

    # ------------------------------------------------------------------
    def fetch_rates(self):
        """取即期汇率；同一 (年份, 币别) 取生效日期最新的那条。"""
        latest = {}
        for record in self._records(self.form_rates, RATE_FIELDS):
            rate_type = text_of(record.get("FRateTypeId.FNumber"))
            if rate_type and rate_type != SPOT_RATE_TYPE:
                continue

            currency = text_of(record.get("FCurrencyId.FNumber")).upper()
            if not currency:
                continue

            try:
                value = Decimal(str(record.get("FExchangeRate")).strip())
            except (InvalidOperation, AttributeError, TypeError):
                continue
            if value <= 0:
                continue

            begin = text_of(record.get("FBeginDate"))
            year = year_of(begin, date.today().year)
            key = (year, currency)
            if key not in latest or begin > latest[key]["begin_date"]:
                latest[key] = {
                    "erp_id": text_of(record.get("FExchangeRateId")),
                    "currency": currency,
                    "rate": value,
                    "year": year,
                    "begin_date": begin,
                }

        return [
            {k: v for k, v in item.items() if k != "begin_date"}
            for item in sorted(latest.values(), key=lambda x: (x["year"], x["currency"]))
        ]

    def fetch_suppliers(self):
        suppliers = []
        for record in self._records(self.form_suppliers, SUPPLIER_FIELDS):
            number = text_of(record.get("FNumber"))
            name = text_of(record.get("FName"))
            if not name:
                continue
            suppliers.append({
                "erp_id": text_of(record.get("FSupplierId")),
                "number": number,
                "name": name,
                "contact": text_of(record.get("FContact")),
                "email": text_of(record.get("FEmail")),
                "is_active": is_active_of(record),
            })
        return suppliers

    def fetch_items(self):
        items = []
        for record in self._records(self.form_items, ITEM_FIELDS):
            number = text_of(record.get("FNumber"))
            name = text_of(record.get("FName"))
            if not number or not name:
                continue
            items.append({
                "erp_id": text_of(record.get("FMATERIALID")),
                "number": number,
                "name": name,
                "spec": text_of(record.get("FSpecification")),
                "unit": text_of(record.get("FBaseUnitId.FName")),
                "material": text_of(record.get("FMaterial.FName")),
                "category": text_of(record.get("FMaterialGroup.FName")),
                "is_active": is_active_of(record),
            })
        return items

    def fetch_customers(self):
        customers = []
        for record in self._records(self.form_customers, CUSTOMER_FIELDS):
            number = text_of(record.get("FNumber"))
            name = text_of(record.get("FName"))
            if not name:
                continue
            try:
                credit_limit = Decimal(str(record.get("FCreditLimit") or "0").strip())
            except (InvalidOperation, AttributeError, TypeError):
                credit_limit = Decimal("0")
            customers.append({
                "erp_id": text_of(record.get("FCUSTID")),
                "number": number,
                "name": name,
                "contact": text_of(record.get("FContact")),
                "phone": text_of(record.get("FPhone")),
                "email": text_of(record.get("FEmail")),
                "currency": (text_of(record.get("FSettleCurrId.FNumber")) or "RMB").upper(),
                "credit_limit": credit_limit,
                "is_active": is_active_of(record),
            })
        return customers

    # ------------------------------------------------------------------
    def test_connection(self):
        started = time.monotonic()
        self.client.login(force=True)
        elapsed = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "message": "连接成功",
            "elapsed_ms": elapsed,
        }