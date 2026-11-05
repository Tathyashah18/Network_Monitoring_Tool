
import os
from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"

    def ready(self):
        if os.environ.get("RUN_MAIN") == "true":
            from monitor import start_monitor
            start_monitor()
