from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Project, VersionHistory


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "customer", "category", "owner",
                    "packaging_engineer", "ie_engineer", "version", "bom_cost_link")
    readonly_fields = ("major_version", "minor_version")

    def bom_cost_link(self, obj):
        url = reverse("bom_cost", args=[obj.id])
        return format_html('<a href="{}">查看 BOM COST</a>', url)

    bom_cost_link.short_description = "BOM COST"


@admin.register(VersionHistory)
class VersionHistoryAdmin(admin.ModelAdmin):
    list_display = ("project", "version", "quote_phase", "created_at")
    list_filter = ("quote_phase",)
    search_fields = ("project__name",)

# 自定义 admin 首页应用顺序：专案管理 → 零件清单 → 报价明细 → 主数据维护 → 认证与授权（最后）
_original_get_app_list = admin.site.get_app_list

def _get_app_list(request, app_label=None):
    app_list = _original_get_app_list(request, app_label)
    order = {"projects": 0, "parts": 1, "quotes": 2, "masterdata": 3, "auth": 99}
    app_list.sort(key=lambda app: order.get(app["app_label"], 50))
    return app_list

admin.site.get_app_list = _get_app_list


# 移除「修改密码」自助功能：只有超级用户可通过该 URL 访问，其余账号一律 403
_original_password_change = admin.site.password_change


def _admin_password_change(request, extra_context=None):
    if not request.user.is_superuser:
        raise PermissionDenied("只有管理员可以修改密码")
    return _original_password_change(request, extra_context)


admin.site.password_change = _admin_password_change


# ---------- 用户页面：只选「组」，不再一个个勾权限 ----------
class MyUserAdmin(BaseUserAdmin):
    list_display = ("username", "display_name", "login_at", "logout_at", "created_at")
    list_filter = ("is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("个人信息", {"fields": ("first_name", "last_name", "email")}),
        ("权限（只选组，权限由组自动继承）",
         {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("从组继承的权限（只读）", {"fields": ("effective_permissions",)}),
    )
    readonly_fields = ("effective_permissions",)

    @admin.display(description="姓名")
    def display_name(self, obj):
        return obj.get_full_name() or "-"

    @admin.display(description="登录时间")
    def login_at(self, obj):
        return obj.last_login

    @admin.display(description="登出时间")
    def logout_at(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.last_logout if profile else None

    @admin.display(description="创建时间")
    def created_at(self, obj):
        return obj.date_joined

    def effective_permissions(self, obj):
        if not obj or not obj.pk:
            return "保存后显示"
        perms = sorted(
            f"{p.content_type.app_label}.{p.codename}"
            for g in obj.groups.all()
            for p in g.permissions.all()
        )
        if not perms:
            return "（该用户所属的组暂无权限）"
        body = "<br>".join(perms)
        return mark_safe(
            '<div style="max-height:300px;overflow:auto;font-size:12px;'
            'line-height:1.7;color:#555;">' + body + "</div>"
        )

    effective_permissions.short_description = "从组继承的权限"


admin.site.unregister(User)
admin.site.register(User, MyUserAdmin)