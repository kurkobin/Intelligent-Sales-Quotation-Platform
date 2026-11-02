# -*- coding: utf-8 -*-
"""离线适配器：不联网、不起假 ERP，也能跑通同步流程（自检 / 单测用）。

数据优先读 mock ERP 目录里的 data.py 种子（ERP_MOCK_DIR），
读不到就退回内置的最小集合，保证任何机器上都能跑。
设置 ERP_MODE=offline 时启用。
"""

import importlib.util
from pathlib import Path

from django.conf import settings

from .base import BaseErpAdapter, is_active_of, number_of, text_of, year_of

FALLBACK_SEED = {
    "BD_ExchangeRate": [
        {"FExchangeRateId": 1, "FCurrencyId": {"FNumber": "USD"}, "FExchangeRate": 7.2,
         "FBeginDate": "2026-01-01", "FRateTypeId": {"FNumber": "001"}},
    ],
    "BD_Supplier": [
        {"FSupplierId": 1, "FNumber": "S001", "FName": "离线演示供应商",
         "FContact": "张三", "FEmail": "offline@demo.com", "FForbidStatus": "A"},
    ],
    "BD_MATERIAL": [
        {"FMATERIALID": 1, "FNumber": "9001", "FName": "离线演示料号",
         "FSpecification": "N/A", "FBaseUnitId": {"FName": "个"},
         "FMaterialGroup": {"FName": "外购件"}, "FMaterial": {"FName": "钢"},
         "FErpClsID": "1", "FForbidStatus": "A"},
    ],
}


def _load_seed():
    """读取假 ERP 的正本种子数据；失败就用 FALLBACK_SEED。"""
    mock_dir = Path(getattr(settings, "ERP_MOCK_DIR", "") or "")
    data_py = mock_dir / "data.py"
    if not data_py.exists():
        return FALLBACK_SEED
    try:
        spec = importlib.util.spec_from_file_location("erp_mock_data", str(data_py))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        seed = getattr(module, "SEED", None)
        return seed if isinstance(seed, dict) else FALLBACK_SEED
    except Exception:
        return FALLBACK_SEED


class MockAdapter(BaseErpAdapter):
    """假实现：结构与 KingdeeAdapter 完全一致，只是不走 HTTP。"""

    name = "offline"
    form_rates = "BD_ExchangeRate"
    form_suppliers = "BD_Supplier"
    form_items = "BD_MATERIAL"

    def __init__(self, seed=None):
        self.seed = seed or _load_seed()

    def fetch_rates(self):
        from datetime import date

        rows = []
        for record in self.seed.get("BD_ExchangeRate", []):
            currency = number_of(record.get("FCurrencyId"))
            if not currency:
                continue
            rows.append({
                "erp_id": text_of(record.get("FExchangeRateId")),
                "currency": currency.upper(),
                "rate": text_of(record.get("FExchangeRate")),
                "year": year_of(record.get("FBeginDate"), date.today().year),
            })
        return rows

    def fetch_suppliers(self):
        rows = []
        for record in self.seed.get("BD_Supplier", []):
            name = text_of(record.get("FName"))
            if not name:
                continue
            rows.append({
                "erp_id": text_of(record.get("FSupplierId")),
                "number": text_of(record.get("FNumber")),
                "name": name,
                "contact": text_of(record.get("FContact")),
                "email": text_of(record.get("FEmail")),
                "is_active": is_active_of(record),
            })
        return rows

    def fetch_items(self):
        rows = []
        for record in self.seed.get("BD_MATERIAL", []):
            number = text_of(record.get("FNumber"))
            name = text_of(record.get("FName"))
            if not number or not name:
                continue
            rows.append({
                "erp_id": text_of(record.get("FMATERIALID")),
                "number": number,
                "name": name,
                "spec": text_of(record.get("FSpecification")),
                "unit": text_of(record.get("FBaseUnitId")),
                "material": text_of(record.get("FMaterial")),
                "category": text_of(record.get("FMaterialGroup")),
                "is_active": is_active_of(record),
            })
        return rows

    def test_connection(self):
        counts = {k: len(v) for k, v in self.seed.items() if isinstance(v, list)}
        return {
            "ok": True,
            "message": f"离线模式（未联网）：本地种子 汇率 {counts.get('BD_ExchangeRate', 0)} / "
                       f"供应商 {counts.get('BD_Supplier', 0)} / 料号 {counts.get('BD_MATERIAL', 0)}",
            "elapsed_ms": 0,
        }