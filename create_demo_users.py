# -*- coding: utf-8 -*-
"""创建演示账号：uv run python create_demo_users.py
密码统一为 demo12345
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

from django.contrib.auth.models import Group, Permission, User

PASSWORD = "demo12345"

# username, 组名, 是否 staff, 是否授予全部后台权限
DEMO = [
    ("cost01", "成本人员", True, True),
    ("sales01", "销售人员", False, False),
    ("eval01", "评估人员", False, False),
    ("purch01", "采购员", False, False),
    ("mold01", "模具工程师", False, False),
]

all_perms = Permission.objects.all()

for username, group_name, is_staff, grant_all in DEMO:
    group, _ = Group.objects.get_or_create(name=group_name)
    user, created = User.objects.get_or_create(username=username)
    user.set_password(PASSWORD)
    user.is_staff = is_staff
    user.is_superuser = False
    user.is_active = True
    user.save()
    user.groups.add(group)
    if grant_all:
        user.user_permissions.set(all_perms)
    print(f"{username:<10} 组={group_name:<8} staff={is_staff}  密码={PASSWORD}  {'新建' if created else '已存在(重置密码)'}")

print("\n全部演示账号密码：", PASSWORD)
