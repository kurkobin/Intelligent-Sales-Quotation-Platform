from django.contrib import admin

from .models import ErpLog


@admin.register(ErpLog)
class ErpLogAdmin(admin.ModelAdmin):
    """只读流水：日志是系统写的，后台只能看。"""

    list_display = ("created_at", "action", "entity", "ok", "duration_ms", "error_short")
    list_filter = ("ok", "action", "entity")
    search_fields = ("entity", "error")
    date_hierarchy = "created_at"
    readonly_fields = ("action", "entity", "request", "response", "ok", "error",
                       "duration_ms", "created_at")

    @admin.display(description="错误摘要")
    def error_short(self, obj):
        return (obj.error[:80] + "…") if len(obj.error) > 80 else (obj.error or "-")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True