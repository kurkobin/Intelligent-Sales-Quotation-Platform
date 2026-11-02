# -*- coding: utf-8 -*-
"""给角色组批量分配权限：uv run python setup_group_permissions.py
可重复运行：以后新增功能/模型后，再跑一次即可把新权限补进对应组。
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

from django.contrib.auth.models import Group, Permission

# 业务 app（不含 auth/admin，避免把「用户管理」权限也给出去）
APPS = ["projects", "parts", "quotes", "masterdata"]

all_perms = Permission.objects.filter(content_type__app_label__in=APPS)
view_perms = Permission.objects.filter(content_type__app_label__in=APPS,
                                      codename__startswith="view_")
quote_part_perms = Permission.objects.filter(
    content_type__app_label__in=["quotes", "parts"],
    codename__in=["view_quote", "change_quote", "view_part"],
)
purchase_perms = Permission.objects.filter(
    content_type__app_label__in=["quotes", "parts"],
    codename__in=["view_supplierquote", "add_supplierquote", "change_supplierquote",
                  "delete_supplierquote", "view_part"],
)

PLAN = {
    "成本人员": all_perms,
    "销售人员": view_perms,
    "评估人员": quote_part_perms,
    "模具工程师": quote_part_perms,
    "模具采购": quote_part_perms,
    "委外采购": quote_part_perms,
    "数控工程师": quote_part_perms,
    "采购员": purchase_perms,
}

for group_name, perms in PLAN.items():
    group, created = Group.objects.get_or_create(name=group_name)
    group.permissions.set(perms)
    print(f"{group_name:<10} 权限 {perms.count():>3} 项  {'（新建组）' if created else ''}")

print("\n完成。以后新增功能后重新运行本脚本即可。")
