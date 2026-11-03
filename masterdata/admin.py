from django.contrib import admin

from .models import (
    Customer,
    ExchangeRate,
    InjectionParam,
    ItemMaster,
    LineWage,
    SheetMaterial,
    StaffMember,
    StampLabor,
    Supplier,
    WageRate,
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "number", "contact", "email", "category", "status", "synced_at")
    list_filter = ("status", "category")
    search_fields = ("name", "contact", "email", "number", "erp_id")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "contact", "phone", "currency", "credit_limit",
                    "is_active", "synced_at")
    list_filter = ("is_active", "currency")
    search_fields = ("number", "name", "contact", "phone", "email", "erp_id")
    ordering = ("number",)


@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "email", "role", "status")
    list_filter = ("status", "department")
    search_fields = ("name", "department", "email", "role")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("year", "base_currency", "currency", "rate", "erp_id", "synced_at")
    list_filter = ("year", "base_currency")
    search_fields = ("currency", "erp_id")


@admin.register(WageRate)
class WageRateAdmin(admin.ModelAdmin):
    list_display = ("dept_name", "dept_code", "plant", "year", "labor", "overhead", "total")
    list_filter = ("year", "plant")
    search_fields = ("dept_name", "dept_code", "supervisor")


@admin.register(SheetMaterial)
class SheetMaterialAdmin(admin.ModelAdmin):
    list_display = ("brand", "material", "density", "unit_price")
    search_fields = ("brand", "material")


@admin.register(LineWage)
class LineWageAdmin(admin.ModelAdmin):
    list_display = ("plant", "line", "machine_count", "setup_hours", "rate",
                    "line_setup_fee", "machine_rate", "machine_setup_fee")
    list_filter = ("plant",)
    search_fields = ("plant", "line")


@admin.register(StampLabor)
class StampLaborAdmin(admin.ModelAdmin):
    list_display = ("plant", "labor_per_hour")
    search_fields = ("plant",)


@admin.register(InjectionParam)
class InjectionParamAdmin(admin.ModelAdmin):
    list_display = ("machine_type", "forming_time", "wage", "assembly_capacity", "mold_rack_fee")
    search_fields = ("machine_type",)


@admin.register(ItemMaster)
class ItemMasterAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "spec", "unit", "material", "category", "is_active", "synced_at")
    list_filter = ("is_active", "category", "material")
    search_fields = ("number", "name", "spec", "erp_id")
    ordering = ("number",)
