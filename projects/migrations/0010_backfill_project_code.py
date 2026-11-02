from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    prefix = f"P{timezone.now().year}-"
    n = 0
    for project in Project.objects.filter(code="").order_by("id"):
        n += 1
        project.code = f"{prefix}{n:03d}"
        project.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0009_project_code_project_status"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
