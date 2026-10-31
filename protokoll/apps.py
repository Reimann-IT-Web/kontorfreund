from django.apps import AppConfig, apps
from django.db.models.signals import post_delete, post_save, pre_save


class ProtokollConfig(AppConfig):
    """Änderungsprotokoll: Anlage, Änderung und Löschung von Geschäftsdaten, Anmeldungen."""

    name = "protokoll"
    verbose_name = "Protokoll"

    def ready(self):
        from .erfassen import ERFASST, geloescht, gespeichert, vorher

        for name in ERFASST:
            modell = apps.get_model(name)
            pre_save.connect(vorher, sender=modell)
            post_save.connect(gespeichert, sender=modell)
            post_delete.connect(geloescht, sender=modell)
