from django.contrib import admin
from .models import Part


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "category", "qty",
                    "size_x", "size_y", "size_z", "volume",
                    "molder", "evaluator", "purchaser", "mold_purchaser", "outsource_buyer", "cnc_engineer")
    list_filter = ("category", "project")
    search_fields = ("name", "remark")