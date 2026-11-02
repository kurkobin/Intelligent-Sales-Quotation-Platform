# -*- coding: utf-8 -*-
"""项目自检脚本：uv run python verify_project.py
只做检查和临时数据（用完即删），不会破坏正式数据。
"""
import os
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client

from projects.models import Project, VersionHistory
from parts.models import Part
from quotes.models import AssemblyItem, Attachment, PackagingItem, Quote, SupplierQuote
from masterdata.models import (
    ExchangeRate, InjectionParam, LineWage, SheetMaterial, StaffMember,
    StampLabor, Supplier, WageRate,
)

PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  " + detail) if detail else ""))


print("=" * 66)
print("智能销售报价平台 — 项目自检")
print("=" * 66)
print("\n[0] 环境")
print("  Python", sys.version.split()[0])
ok("Django 已加载", True, "Django " + django.get_version())

client = Client()
user = User.objects.filter(is_superuser=True).first()
ok("存在超级用户", user is not None, user.username if user else "无")
if not user:
    print("\n请先执行：uv run python manage.py createsuperuser")
    sys.exit(1)
client.force_login(user)

pid = Project.objects.first().id if Project.objects.exists() else None
part_id = Part.objects.first().id if Part.objects.exists() else None

print("\n[1] 页面可达性")
urls = ["/", "/dashboard/", "/my-tasks/", "/my-parts/", "/report/"]
if pid:
    urls += [
        f"/project/{pid}/bomcost/", f"/project/{pid}/packaging/", f"/project/{pid}/assembly/",
        f"/project/{pid}/import/", f"/project/{pid}/attachments/", f"/project/{pid}/assign/",
        f"/project/{pid}/template/", f"/project/{pid}/upload-quotes/", f"/project/{pid}/versions/",
        f"/project/{pid}/upload-3d/",
        f"/report/?project={pid}", f"/report/?rtype=supplier&project={pid}",
    ]
if part_id:
    urls += [f"/part/{part_id}/quote/", f"/part/{part_id}/suppliers/"]
urls += ["/tasks/mold/", "/tasks/moldbuy/", "/tasks/outsource/", "/tasks/cnc/", "/admin/"]

bad = 0
for u in urls:
    try:
        r = client.get(u)
        if r.status_code not in (200, 302):
            bad += 1
            print("  [FAIL]", r.status_code, u)
    except Exception as e:
        bad += 1
        print("  [ERROR]", u, type(e).__name__, e)
ok(f"页面访问（{len(urls)} 个）", bad == 0, "" if bad == 0 else f"失败 {bad} 个")

print("\n[2] 数据表记录数")
for label, model in [
    ("专案", Project), ("零件", Part), ("报价", Quote),
    ("包材项", PackagingItem), ("组装工序", AssemblyItem),
    ("供应商报价", SupplierQuote), ("报价附件", Attachment),
    ("版本历史", VersionHistory),
    ("供应商主数据", Supplier), ("部门人员", StaffMember),
    ("汇率", ExchangeRate), ("报价工缴", WageRate),
    ("钣金材料", SheetMaterial), ("线别工缴率", LineWage),
    ("冲压人工费", StampLabor), ("注塑参数", InjectionParam),
]:
    print(f"  {label:<12} {model.objects.count():>4} 条")

print("\n[3] BOM COST 公式")
if pid:
    project = Project.objects.get(pk=pid)
    parts_total = total_mold = material_total = Decimal("0")
    for p in project.parts.all():
        q = getattr(p, "quote", None)
        if q:
            parts_total += q.material + q.process + q.finish
            total_mold += q.mold_fee
            material_total += q.material
    packaging = sum((i.amount for i in project.packaging_items.all()), Decimal("0"))
    assembly = sum((i.cost for i in project.assembly_items.all()), Decimal("0"))
    qty = project.forecast_qty or 1
    amort = (total_mold - project.customer_mold_payment) / qty
    defect = (material_total + assembly) * (project.defect_rate / Decimal("100"))
    total = parts_total + amort + defect + packaging + assembly
    ok("BOM COST 可计算", True,
       f"{project.name} 单套 {total:.2f} RMB（零件 {parts_total:.2f} / 模摊 {amort:.2f} / 不良 {defect:.2f} / 包材 {packaging:.2f} / 组装 {assembly:.2f}）")
else:
    print("  没有专案，跳过")

print("\n[4] 功能自检")
if pid:
    project = Project.objects.get(pk=pid)
    item = PackagingItem.objects.create(project=project, name="__自检__", usage=Decimal("2"), unit_price=Decimal("3"))
    ok("包材：金额 = 用量 × 单价", item.amount == Decimal("6"), str(item.amount))
    item.delete()

    line = AssemblyItem.objects.create(project=project, step="__自检__",
                                       headcount=Decimal("2"), capacity_per_hour=Decimal("10"), rate_rmb=Decimal("30"))
    ok("组装：成本 = 人力 ÷ 产能 × 工缴", abs(float(line.cost) - 6.0) < 0.01, str(line.cost))
    line.delete()

    if part_id:
        part = Part.objects.get(pk=part_id)
        sq = SupplierQuote.objects.create(part=part, supplier_name="__自检__", price=Decimal("9"))
        ok("供应商报价：可创建", sq.pk is not None)
        sq.delete()

try:
    from quotes.cad_parser import parse_cad
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".step")
    tmp.close()
    box = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(box, STEPControl_AsIs)
    writer.Write(tmp.name)
    items = parse_cad(tmp.name)
    os.unlink(tmp.name)
    good = len(items) == 1 and abs(items[0]["volume"] - 6000) < 1 and abs(items[0]["x"] - 10) < 0.01
    ok("3D 解析（10×20×30 方块 → 体积 6000）", good, str(items))
except Exception as e:
    ok("3D 解析", False, f"{type(e).__name__}: {e}")

print("\n" + "=" * 66)
print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    for f in FAIL:
        print("  - 失败：", f)
    sys.exit(1)
print("全部通过")
