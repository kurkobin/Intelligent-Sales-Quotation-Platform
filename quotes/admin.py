from django.contrib import admin

from .models import AssemblyItem, Attachment, PackagingItem, Quote, SupplierQuote


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("part", "material", "process", "finish",
                    "mold_fee", "outsource_process_fee", "outsource_finish_fee", "nct_fee", "status")
    list_filter = ("status",)
    search_fields = ("part__name",)

    def get_readonly_fields(self, request, obj=None):
        readonly = ["status"]
        if obj is not None and obj.status == "submitted":
            readonly += ["part", "material", "process", "finish",
                         "mold_fee", "outsource_process_fee", "outsource_finish_fee", "nct_fee"]
        return readonly

    @admin.action(description="提交（锁定）")
    def mark_submitted(self, request, queryset):
        queryset.update(status="submitted")

    @admin.action(description="取消提交（解锁）")
    def mark_draft(self, request, queryset):
        queryset.update(status="draft")

    actions = ["mark_submitted", "mark_draft"]


@admin.register(PackagingItem)
class PackagingItemAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "part_no", "unit", "usage", "unit_price", "amount")
    list_filter = ("project",)
    search_fields = ("name", "part_no")


@admin.register(AssemblyItem)
class AssemblyItemAdmin(admin.ModelAdmin):
    list_display = ("step", "project", "dept_name", "headcount", "capacity_per_hour", "rate_rmb", "cost")
    list_filter = ("project",)
    search_fields = ("step", "dept_name")


@admin.register(SupplierQuote)
class SupplierQuoteAdmin(admin.ModelAdmin):
    list_display = ("part", "supplier_name", "currency", "price", "mold_fee", "quota")
    list_filter = ("currency",)
    search_fields = ("supplier_name", "part__name")


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "uploaded_by", "uploaded_at")
    list_filter = ("project",)
    search_fields = ("title",)
