# -*- coding: utf-8 -*-
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.shortcuts import redirect, render

from masterdata.models import Customer, ExchangeRate, ItemMaster, Supplier

from . import services
from .models import ErpLog


def _latest_sync(model):
    return (model.objects.filter(synced_at__isnull=False)
            .order_by("-synced_at")
            .values_list("synced_at", flat=True)
            .first())


@login_required
def sync_page(request):
    if not request.user.is_staff:
        messages.error(request, "只有管理员可以触发 ERP 同步")
        return redirect("dashboard")

    if request.method == "POST":
        action = request.POST.get("action", "sync")
        what = request.POST.get("what", "all")
        if action == "test":
            info = services.test_connection()
            (messages.success if info["ok"] else messages.error)(
                request, f"{info['message']}（{info['elapsed_ms']} ms）")
        else:
            try:
                results = services.sync_one(what)
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                failed = [r for r in results.values() if not r.ok]
                done = [r for r in results.values() if r.ok]
                if done:
                    messages.success(
                        request, "同步成功：" + " / ".join(f"{r.label} {r.total}" for r in done))
                for result in failed:
                    messages.error(request, result.summary)
        return redirect("erp_sync")

    context = {
        "mode": getattr(settings, "ERP_MODE", "mock"),
        "base_url": getattr(settings, "ERP_BASE_URL", ""),
        "acct_id": getattr(settings, "ERP_ACCT_ID", ""),
        "erp_user": getattr(settings, "ERP_USER", ""),
        "timeout": getattr(settings, "ERP_TIMEOUT", 30),
        "max_attempts": getattr(settings, "ERP_MAX_ATTEMPTS", 3),
        "rate_count": ExchangeRate.objects.count(),
        "supplier_count": Supplier.objects.count(),
        "item_count": ItemMaster.objects.count(),
        "customer_count": Customer.objects.count(),
        "rate_synced": _latest_sync(ExchangeRate),
        "supplier_synced": _latest_sync(Supplier),
        "item_synced": _latest_sync(ItemMaster),
        "customer_synced": _latest_sync(Customer),
        "logs": ErpLog.objects.all()[:12],
        "ok_logs": ErpLog.objects.filter(ok=True).count(),
        "fail_logs": ErpLog.objects.filter(ok=False).count(),
    }
    return render(request, "erp/sync.html", context)