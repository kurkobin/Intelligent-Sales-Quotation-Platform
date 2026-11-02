from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = 'projects'
    verbose_name = "专案管理"

    def ready(self):
        from . import signals  # noqa: F401