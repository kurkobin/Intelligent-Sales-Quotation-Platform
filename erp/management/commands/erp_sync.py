# -*- coding: utf-8 -*-
"""从 ERP 同步主数据。

    python manage.py erp_sync --what=all
    python manage.py erp_sync --what=rates
    python manage.py erp_sync --test
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from erp import services


class Command(BaseCommand):
    help = "从 ERP 同步主数据：--what=rates|suppliers|items|all"

    def add_arguments(self, parser):
        parser.add_argument("--what", default="all",
                            choices=["rates", "suppliers", "items", "customers", "all"],
                            help="同步哪张表，默认 all")
        parser.add_argument("--test", action="store_true", help="只测连接，不同步")

    def handle(self, *args, **options):
        mode = getattr(settings, "ERP_MODE", "mock")
        base_url = getattr(settings, "ERP_BASE_URL", "")
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f"ERP 同步　模式 {mode}　地址 {base_url}"))
        self.stdout.write("-" * 62)

        if options["test"]:
            info = services.test_connection()
            self._print_test(info)
            if not info["ok"]:
                raise SystemExit(1)
            return

        results = services.sync_one(options["what"])

        failed = False
        for result in results.values():
            elapsed = f"{result.elapsed_ms / 1000:.2f}s"
            if result.ok:
                self.stdout.write(
                    f"[{result.label}] {self.style.SUCCESS('成功')}　"
                    f"新增 {result.created}／更新 {result.updated}／共 {result.fetched} 条　{elapsed}"
                )
            else:
                failed = True
                self.stdout.write(f"[{result.label}] {self.style.ERROR('失败')}　{result.error}")

        self.stdout.write("-" * 62)
        if failed:
            # 只报根因；「未执行（…）」是连带结果，不当作失败原因重复展示
            reasons = []
            for result in results.values():
                if result.ok or result.error.startswith("未执行") or result.error in reasons:
                    continue
                reasons.append(result.error)
            if not reasons:
                reasons = [r.error for r in results.values() if not r.ok]
            self.stdout.write(self.style.ERROR("同步失败：" + "；".join(reasons)))
            self.stdout.write("Django 未抛异常，失败已记入 ErpLog（后台 /admin/erp/erplog/ 可查）。")
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            "同步成功：" + " / ".join(f"{r.label} {r.total}" for r in results.values())
        ))

    def _print_test(self, info):
        state = self.style.SUCCESS("连接成功") if info["ok"] else self.style.ERROR("连接失败")
        # 消息和状态同为「连接成功/失败」时只显示一次
        message = "" if info["message"] in ("连接成功", "连接失败") else f"　{info['message']}"
        self.stdout.write(f"[连接] {state}{message}　{info['elapsed_ms']} ms")