from django.apps import AppConfig


class KontenConfig(AppConfig):
    name = "konten"
    verbose_name = "Benutzer und Anmeldung"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .sitzungen import merken

        user_logged_in.connect(merken, dispatch_uid="konten.sitzungen.merken")
