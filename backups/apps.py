from django.apps import AppConfig, apps
from django.db.models.signals import pre_migrate


class BackupsConfig(AppConfig):
    """Datensicherung: verschlüsselt, täglich und vor jedem Update."""

    name = "backups"
    verbose_name = "Datensicherung"

    def ready(self):
        from .sicherung import vor_update

        # Django sendet pre_migrate nur an Apps mit Modellen; „core“ hat immer welche.
        pre_migrate.connect(vor_update, sender=apps.get_app_config("core"))
