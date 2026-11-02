from django.contrib import admin
from .models import Part


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "category", "qty", "item_master",
                    "sheet_material", "weight_display", "material_cost_display",
                    "size_x", "size_y", "size_z", "volume",
                    "molder", "evaluator", "purchaser", "mold_purchaser", "outsource_buyer", "cnc_engineer")
    list_filter = ("category", "project")
    search_fields = ("name", "remark", "item_master__number")

    @admin.display(description="重量(kg)")
    def weight_display(self, obj):
        return f"{obj.weight_kg:.2f}" if obj.weight_kg else "-"

    @admin.display(description="自动材料费")
    def material_cost_display(self, obj):
        return f"{obj.auto_material_cost:.2f}" if obj.auto_material_cost else "-"