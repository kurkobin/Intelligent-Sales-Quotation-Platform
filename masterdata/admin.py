from django.contrib import admin

from .models import (
    ExchangeRate,
    InjectionParam,
    LineWage,
    SheetMaterial,
    StaffMember,
    StampLabor,
    Supplier,
    WageRate,
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "email", "category", "status")
    list_filter = ("status", "category")
    search_fields = ("name", "contact", "email")


@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "email", "role", "status")
    list_filter = ("status", "department")
    search_fields = ("name", "department", "email", "role")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("year", "base_currency", "currency", "rate")
    list_filter = ("year", "base_currency")
    search_fields = ("currency",)


@admin.register(WageRate)
class WageRateAdmin(admin.ModelAdmin):
    list_display = ("dept_name", "dept_code", "plant", "year", "labor", "overhead", "total")
    list_filter = ("year", "plant")
    search_fields = ("dept_name", "dept_code", "supervisor")


@admin.register(SheetMaterial)
class SheetMaterialAdmin(admin.ModelAdmin):
    list_display = ("brand", "material", "density")
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
