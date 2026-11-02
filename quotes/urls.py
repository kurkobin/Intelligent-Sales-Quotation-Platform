from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("project/<int:project_id>/bomcost/", views.bom_cost, name="bom_cost"),
    path("project/<int:project_id>/export/", views.export_bom_cost, name="export_bom_cost"),
    path("project/<int:project_id>/import/", views.import_parts, name="import_parts"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("my-tasks/", views.my_tasks, name="my_tasks"),
    path("part/<int:part_id>/quote/", views.edit_quote, name="edit_quote"),
    path("project/<int:project_id>/approve/", views.approve_bom, name="approve_bom"),
    path("my-parts/", views.my_parts, name="my_parts"),
    path("project/<int:project_id>/packaging/", views.packaging_tasks, name="packaging_tasks"),
    path("project/<int:project_id>/assembly/", views.assembly_tasks, name="assembly_tasks"),
    path("part/<int:part_id>/suppliers/", views.supplier_quotes, name="supplier_quotes"),
    path("tasks/<str:role>/", views.role_tasks, name="role_tasks"),
    path("report/", views.report_query, name="report_query"),
    path("project/<int:project_id>/attachments/", views.attachment_library, name="attachment_library"),
    path("project/<int:project_id>/assign/", views.assign_tasks, name="assign_tasks"),
    path("project/<int:project_id>/template/", views.download_quote_template, name="download_quote_template"),
    path("project/<int:project_id>/upload-quotes/", views.upload_quote_sheet, name="upload_quote_sheet"),
    path("project/<int:project_id>/versions/", views.version_history, name="version_history"),
    path("project/<int:project_id>/upload-3d/", views.upload_3d, name="upload_3d"),
    path("project/<int:project_id>/toggle-status/", views.toggle_project_status, name="toggle_project_status"),
    path("project/<int:project_id>/export-parts/", views.export_parts, name="export_parts"),
    path("attachments/", views.attachment_library_all, name="attachment_library_all"),
]