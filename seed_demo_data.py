# -*- coding: utf-8 -*-
"""灌入演示/测试用的主数据（可重复运行，不会重复插入）

用法：
    uv run python seed_demo_data.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from decimal import Decimal

from masterdata.models import (
    ExchangeRate, InjectionParam, LineWage, SheetMaterial,
    StaffMember, StampLabor, Supplier, WageRate,
)


def seed():
    # ---------- 汇率 ----------
    for currency, rate in [("RMB", "1"), ("USD", "7.20"), ("NTD", "0.23")]:
        ExchangeRate.objects.update_or_create(
            year=2026, base_currency="RMB", currency=currency,
            defaults={"rate": Decimal(rate)},
        )
    print("汇率        3 条")

    # ---------- 供应商 ----------
    suppliers = [
        ("东莞精密五金", "张伟", "zhangwei@demo.com", "冲压件"),
        ("深圳鑫达钣金", "李娜", "lina@demo.com", "钣金件"),
        ("东莞注塑科技", "王强", "wangqiang@demo.com", "注塑件"),
        ("苏州表面处理", "赵敏", "zhaomin@demo.com", "表面处理"),
        ("越南AVC配件", "Nguyen", "nguyen@demo.com", "外购件"),
    ]
    for name, contact, email, category in suppliers:
        Supplier.objects.update_or_create(
            name=name,
            defaults={"contact": contact, "email": email, "category": category, "status": "启用"},
        )
    print(f"供应商      {len(suppliers)} 条")

    # ---------- 部门人员 ----------
    staff = [
        ("李成本", "成本课", "licb@demo.com", "成本人员"),
        ("王销售", "业务部", "wangxs@demo.com", "销售人员"),
        ("陈评估", "工程部", "chenpg@demo.com", "评估人员"),
        ("刘采购", "采购部", "liucg@demo.com", "采购员"),
        ("周模具", "模具课", "zhoumj@demo.com", "模具工程师"),
    ]
    for name, dept, email, role in staff:
        StaffMember.objects.update_or_create(
            name=name,
            defaults={"department": dept, "email": email, "role": role, "status": "启用"},
        )
    print(f"部门人员    {len(staff)} 条")

    # ---------- 报价工缴 ----------
    wages = [
        ("制造部", "MFG01", "制造一課", "东莞明鑫", "张三", "35", "20"),
        ("组装部", "ASM01", "组装課", "东莞明鑫", "李四", "30", "18"),
        ("模具课", "MOL01", "模具課", "深圳奇宏", "王五", "42", "25"),
    ]
    for dept_name, code, dept, plant, sup, labor, overhead in wages:
        WageRate.objects.update_or_create(
            dept_code=code, year=2026, plant=plant,
            defaults={"dept_name": dept_name, "supervisor": sup,
                      "labor": Decimal(labor), "overhead": Decimal(overhead)},
        )
    print(f"报价工缴    {len(wages)} 条")

    # ---------- 钣金材料（密度 + 单价）----------
    materials = [
        ("宝钢", "SGCC 镀锌钢板", "7.85", "6.50"),
        ("宝钢", "SPCC 冷轧钢板", "7.85", "6.20"),
        ("南山铝业", "AL5052 铝板", "2.68", "24.00"),
        ("太钢", "SUS304 不锈钢", "7.93", "28.00"),
    ]
    for brand, material, density, price in materials:
        SheetMaterial.objects.update_or_create(
            brand=brand, material=material,
            defaults={"density": Decimal(density), "unit_price": Decimal(price)},
        )
    print(f"钣金材料    {len(materials)} 条")

    # ---------- 线别工缴率 ----------
    lines = [
        ("东莞明鑫", "线別1", 2, "4.00", "180.00"),
        ("东莞明鑫", "线別2", 3, "4.00", "220.00"),
        ("深圳奇宏", "线別1", 2, "3.00", "200.00"),
    ]
    for plant, line, machines, setup, rate in lines:
        LineWage.objects.update_or_create(
            plant=plant, line=line,
            defaults={"machine_count": machines, "setup_hours": Decimal(setup), "rate": Decimal(rate)},
        )
    print(f"线别工缴率  {len(lines)} 条")

    # ---------- 冲压人工费 ----------
    for plant, fee in [("东莞明鑫", "45.00"), ("深圳奇宏", "48.00")]:
        StampLabor.objects.update_or_create(
            plant=plant, defaults={"labor_per_hour": Decimal(fee)},
        )
    print("冲压人工费  2 条")

    # ---------- 注塑成型参数 ----------
    injections = [
        ("80T", "25.00", "60.0000", "500.00", "1200.00"),
        ("130T", "35.00", "85.0000", "400.00", "1800.00"),
        ("250T", "55.00", "120.0000", "300.00", "2600.00"),
    ]
    for machine, forming, wage, capacity, rack in injections:
        InjectionParam.objects.update_or_create(
            machine_type=machine,
            defaults={"forming_time": Decimal(forming), "wage": Decimal(wage),
                      "assembly_capacity": Decimal(capacity), "mold_rack_fee": Decimal(rack)},
        )
    print(f"注塑参数    {len(injections)} 条")


if __name__ == "__main__":
    seed()
    print("\n完成。全部为演示用 mock 数据，可重复运行。")
