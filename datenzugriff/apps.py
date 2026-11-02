from django.apps import AppConfig


class DatenzugriffConfig(AppConfig):
    """Unmittelbarer Datenzugriff für die Betriebsprüfung: Prüfer lesen, ändern nichts."""

    name = "datenzugriff"
    verbose_name = "Datenzugriff"
