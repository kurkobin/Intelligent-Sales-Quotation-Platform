# -*- coding: utf-8 -*-
"""ERP 同步的自动化测试（不联网、不依赖假 ERP 进程）。

    uv run python manage.py test erp -v 2

覆盖三块最容易出错的地方：
1. 金蝶报文映射（汇率取即期/取最新生效日、禁用状态、嵌套字段）；
2. 全量 upsert 的幂等性与首次对接「认领旧数据」；
3. 失败时不抛异常、连接失败后其余实体不再重试、后台按钮的权限。
"""

import io
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from masterdata.models import Customer, ExchangeRate, ItemMaster, Supplier

from . import services
from .adapters.base import BaseErpAdapter, is_active_of, number_of, text_of
from .adapters.kingdee import (
    CUSTOMER_FIELDS,
    ITEM_FIELDS,
    RATE_FIELDS,
    SUPPLIER_FIELDS,
    KingdeeAdapter,
)
from .client import ErpConnectionError, KingdeeClient, _extract_erp_error, _summarize


# --------------------------------------------------------------------------
# 假 HTTP 客户端：直接返回二维数组，模拟金蝶 ExecuteBillQuery 的响应
# --------------------------------------------------------------------------
class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, form_id, field_keys, **kwargs):
        self.calls.append((form_id, field_keys))
        return self.rows

    def login(self, force=False):
        return True


class AdapterMappingTests(SimpleTestCase):
    """金蝶字段 → 我们的字典，纯逻辑，不碰数据库。"""

    def test_rates_take_spot_and_latest_begin_date(self):
        rows = [
            [1, "USD", 7.2, "2026-01-01", "001"],
            [2, "USD", 7.1, "2025-06-01", "001"],
            [3, "NTD", 0.23, "2026-01-01", "001"],
            [4, "EUR", 8.1, "2026-01-01", "002"],   # 非即期汇率（002），应忽略
            [5, "USD", 7.3, "2025-12-01", "001"],   # 2025 年更新的那条，应覆盖 7.1
        ]
        adapter = KingdeeAdapter(client=FakeClient(rows))
        rates = adapter.fetch_rates()

        got = {(item["year"], item["currency"]): item["rate"] for item in rates}
        self.assertNotIn("EUR", {item["currency"] for item in rates})
        self.assertEqual(got[(2026, "USD")], Decimal("7.2"))
        self.assertEqual(got[(2025, "USD")], Decimal("7.3"))
        self.assertEqual(got[(2026, "NTD")], Decimal("0.23"))
        self.assertEqual(len(rates), 3)

    def test_supplier_fields_and_forbid_status(self):
        rows = [
            [1, "S001", "东莞精密五金", "张伟", "a@demo.com", "A"],
            [2, "S002", "深圳鑫达钣金", "李娜", "b@demo.com", "B"],
        ]
        adapter = KingdeeAdapter(client=FakeClient(rows))
        suppliers = adapter.fetch_suppliers()

        self.assertEqual(suppliers[0]["erp_id"], "1")
        self.assertEqual(suppliers[0]["number"], "S001")
        self.assertEqual(suppliers[0]["name"], "东莞精密五金")
        self.assertTrue(suppliers[0]["is_active"])
        self.assertFalse(suppliers[1]["is_active"])

    def test_item_fields(self):
        rows = [[3001, "1001", "前框支架", "SECC 1.2t", "个", "冲压件", "SECC", "1", "A"]]
        adapter = KingdeeAdapter(client=FakeClient(rows))
        items = adapter.fetch_items()

        self.assertEqual(items[0], {
            "erp_id": "3001", "number": "1001", "name": "前框支架",
            "spec": "SECC 1.2t", "unit": "个", "material": "SECC",
            "category": "冲压件", "is_active": True,
        })

    def test_customer_fields(self):
        rows = [[4001, "C001", "深圳华创电子", "陈志强", "0755-8888 1001",
                 "c@demo.com", "USD", 500000, "B"]]
        adapter = KingdeeAdapter(client=FakeClient(rows))
        customers = adapter.fetch_customers()

        self.assertEqual(customers[0]["erp_id"], "4001")
        self.assertEqual(customers[0]["number"], "C001")
        self.assertEqual(customers[0]["name"], "深圳华创电子")
        self.assertEqual(customers[0]["currency"], "USD")
        self.assertEqual(customers[0]["credit_limit"], Decimal("500000"))
        self.assertFalse(customers[0]["is_active"])

    def test_field_keys_order_matches_columns(self):
        """二维数组没有字段名，列顺序必须和 FieldKeys 一一对应。"""
        self.assertEqual(
            RATE_FIELDS.split(","),
            ["FExchangeRateId", "FCurrencyId.FNumber", "FExchangeRate", "FBeginDate", "FRateTypeId.FNumber"],
        )
        self.assertEqual(len(SUPPLIER_FIELDS.split(",")), 6)
        self.assertEqual(len(ITEM_FIELDS.split(",")), 9)
        self.assertEqual(len(CUSTOMER_FIELDS.split(",")), 9)


class BaseHelperTests(SimpleTestCase):
    def test_text_of_handles_dict_and_list(self):
        self.assertEqual(text_of({"FNumber": "USD", "FName": "美元"}), "美元")
        self.assertEqual(text_of([1001, "S001", "东莞精密五金"]), "东莞精密五金")
        self.assertEqual(text_of(None), "")

    def test_number_of_prefers_code(self):
        self.assertEqual(number_of({"FNumber": "USD", "FName": "美元"}), "USD")
        self.assertEqual(number_of([1001, "RMB", "人民币"]), "RMB")

    def test_is_active_of(self):
        self.assertTrue(is_active_of({"FForbidStatus": "A"}))
        self.assertFalse(is_active_of({"FForbidStatus": "B"}))
        self.assertTrue(is_active_of({}))


# --------------------------------------------------------------------------
# 同步服务
# --------------------------------------------------------------------------
class StubAdapter(BaseErpAdapter):
    name = "stub"
    form_rates = form_suppliers = form_items = form_customers = "STUB"

    def __init__(self, rates=None, suppliers=None, items=None, customers=None, fail=False):
        self._rates = rates or []
        self._suppliers = suppliers or []
        self._items = items or []
        self._customers = customers or []
        self._fail = fail

    def fetch_rates(self):
        if self._fail:
            raise ErpConnectionError("连接失败，已重试 3 次：连接被拒绝")
        return self._rates

    def fetch_suppliers(self):
        return self._suppliers

    def fetch_items(self):
        return self._items

    def fetch_customers(self):
        return self._customers

    def test_connection(self):
        return {"ok": True, "message": "stub", "elapsed_ms": 0}


RATE = {"erp_id": "1002", "currency": "USD", "rate": Decimal("7.2"), "year": 2026}
SUPPLIER = {"erp_id": "2001", "number": "S001", "name": "东莞精密五金",
            "contact": "张伟", "email": "a@demo.com", "is_active": True}
ITEM = {"erp_id": "3001", "number": "1001", "name": "前框支架", "spec": "SECC",
        "unit": "个", "material": "SECC", "category": "冲压件", "is_active": True}
CUSTOMER = {"erp_id": "4001", "number": "C001", "name": "深圳华创电子",
            "contact": "陈志强", "phone": "0755-8888 1001", "email": "c@demo.com",
            "currency": "RMB", "credit_limit": Decimal("500000"), "is_active": True}


class SyncServiceTests(TestCase):
    def test_sync_creates_then_updates(self):
        adapter = StubAdapter(rates=[RATE], suppliers=[SUPPLIER], items=[ITEM],
                              customers=[CUSTOMER])

        first = services.sync_all(adapter)
        self.assertEqual(first["rates"].created, 1)
        self.assertEqual(first["suppliers"].created, 1)
        self.assertEqual(first["items"].created, 1)
        self.assertEqual(first["customers"].created, 1)
        self.assertEqual(ExchangeRate.objects.count(), 1)
        self.assertEqual(ItemMaster.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)

        second = services.sync_all(adapter)
        self.assertEqual(second["rates"].created, 0)
        self.assertEqual(second["rates"].updated, 1)
        self.assertEqual(second["items"].created, 0)
        self.assertEqual(second["customers"].created, 0)
        self.assertEqual(second["customers"].updated, 1)
        self.assertEqual(ItemMaster.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)

    def test_customer_fields_persisted(self):
        services.sync_customers(StubAdapter(customers=[CUSTOMER]))

        row = Customer.objects.get(number="C001")
        self.assertEqual(row.name, "深圳华创电子")
        self.assertEqual(row.phone, "0755-8888 1001")
        self.assertEqual(row.currency, "RMB")
        self.assertEqual(row.credit_limit, Decimal("500000"))
        self.assertTrue(row.is_active)
        self.assertEqual(row.erp_id, "4001")
        self.assertIsNotNone(row.synced_at)

    def test_first_sync_adopts_existing_customer_with_same_name(self):
        old = Customer.objects.create(name="深圳华创电子", contact="旧联系人")

        services.sync_customers(StubAdapter(customers=[CUSTOMER]))

        self.assertEqual(Customer.objects.count(), 1)
        old.refresh_from_db()
        self.assertEqual(old.erp_id, "4001")
        self.assertEqual(old.number, "C001")
        self.assertEqual(old.contact, "陈志强")

    def test_rate_keyed_by_year_and_currency(self):
        ExchangeRate.objects.create(year=2026, base_currency="RMB", currency="USD",
                                    rate=Decimal("7.0"))
        services.sync_rates(StubAdapter(rates=[RATE]))

        self.assertEqual(ExchangeRate.objects.count(), 1)
        row = ExchangeRate.objects.get()
        self.assertEqual(row.rate, Decimal("7.2"))
        self.assertEqual(row.erp_id, "1002")
        self.assertIsNotNone(row.synced_at)

    def test_first_sync_adopts_existing_supplier_with_same_name(self):
        """平台里手工维护过、没有 erp_id 的供应商，应按名字认领而不是插一条新的。"""
        old = Supplier.objects.create(name="东莞精密五金", contact="旧联系人")

        services.sync_suppliers(StubAdapter(suppliers=[SUPPLIER]))

        self.assertEqual(Supplier.objects.count(), 1)
        old.refresh_from_db()
        self.assertEqual(old.erp_id, "2001")
        self.assertEqual(old.number, "S001")
        self.assertEqual(old.contact, "张伟")

    def test_connection_failure_marks_remaining_entities_skipped(self):
        results = services.sync_all(StubAdapter(fail=True))

        self.assertFalse(results["rates"].ok)
        self.assertIn("已重试 3 次", results["rates"].error)
        self.assertFalse(results["suppliers"].ok)
        self.assertIn("未执行", results["suppliers"].error)
        self.assertEqual(ItemMaster.objects.count(), 0)

    def test_unknown_target_raises(self):
        with self.assertRaises(ValueError):
            services.sync_one("invoices")

    def test_test_connection_is_offline_friendly(self):
        info = services.test_connection(StubAdapter())
        self.assertTrue(info["ok"])
        self.assertEqual(info["message"], "stub")


# --------------------------------------------------------------------------
# 管理命令
# --------------------------------------------------------------------------
@override_settings(ERP_MODE="offline", ERP_MOCK_DIR="C:/__not_exists__")
class CommandTests(TestCase):
    def test_erp_sync_offline_and_idempotent(self):
        out = io.StringIO()
        call_command("erp_sync", "--what=all", stdout=out)
        self.assertIn("同步成功", out.getvalue())
        self.assertEqual(ExchangeRate.objects.count(), 1)
        self.assertEqual(Supplier.objects.count(), 1)
        self.assertEqual(ItemMaster.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)

        call_command("erp_sync", "--what=all", stdout=io.StringIO())
        self.assertEqual(ExchangeRate.objects.count(), 1)
        self.assertEqual(Supplier.objects.count(), 1)
        self.assertEqual(ItemMaster.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)

    def test_erp_sync_customers_only(self):
        out = io.StringIO()
        call_command("erp_sync", "--what=customers", stdout=out)
        self.assertIn("客户", out.getvalue())
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Supplier.objects.count(), 0)

    def test_erp_sync_test_mode(self):
        out = io.StringIO()
        call_command("erp_sync", "--test", stdout=out)
        self.assertIn("连接成功", out.getvalue())


# --------------------------------------------------------------------------
# 后台页面权限
# --------------------------------------------------------------------------
@override_settings(ERP_MODE="offline", ERP_MOCK_DIR="C:/__not_exists__")
class PageTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("erp_staff", password="x", is_staff=True)
        self.normal = User.objects.create_user("erp_normal", password="x")

    def test_staff_can_open_sync_page(self):
        self.client.force_login(self.staff)
        response = self.client.get("/erp/sync/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ERP 主数据同步")

    def test_non_staff_is_redirected(self):
        self.client.force_login(self.normal)
        response = self.client.get("/erp/sync/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard/")

    def test_staff_can_sync_via_button(self):
        self.client.force_login(self.staff)
        response = self.client.post("/erp/sync/", {"action": "sync", "what": "all"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExchangeRate.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertContains(response, "同步成功")

    def test_sync_customers_button(self):
        self.client.force_login(self.staff)
        response = self.client.post("/erp/sync/", {"action": "sync", "what": "customers"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertContains(response, "同步成功：客户 1")


# --------------------------------------------------------------------------
# 客户端辅助逻辑（不打网络）
# --------------------------------------------------------------------------
class ClientHelperTests(SimpleTestCase):
    def test_password_is_masked_in_log_payload(self):
        client = KingdeeClient(base_url="http://x", user="api_user",
                               password="api_password", log=False)
        payload = client._safe_payload(
            {"parameters": ["acct", "api_user", "api_password", 2052], "format": "json"})
        self.assertNotIn("api_password", payload["parameters"])
        self.assertIn("***", payload["parameters"])

    def test_extract_error_from_kingdee_result(self):
        data = {"Result": {"ResponseStatus": {"IsSuccess": False, "Errors": [
            {"Message": "会话信息已丢失，请重新登录"}]}}}
        self.assertEqual(_extract_erp_error(data), "会话信息已丢失，请重新登录")

    def test_summarize_keeps_rows_count_and_sample(self):
        summary = _summarize([[1, "S001"], [2, "S002"], [3, "S003"]])
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(len(summary["sample"]), 2)

    def test_judge_detects_login_failure(self):
        client = KingdeeClient(base_url="http://x", log=False)
        ok, error = client._judge({"LoginResultType": 0, "Message": "用户名或密码错误"})
        self.assertFalse(ok)
        self.assertEqual(error, "用户名或密码错误")
        ok, _ = client._judge({"LoginResultType": 1, "Message": "登录成功"})
        self.assertTrue(ok)

    def test_missing_base_url_reports_clearly(self):
        client = KingdeeClient(base_url="", log=False)
        with self.assertRaises(ErpConnectionError) as ctx:
            client.login()
        self.assertIn("ERP_BASE_URL", str(ctx.exception))