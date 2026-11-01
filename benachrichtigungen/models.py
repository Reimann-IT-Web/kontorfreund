from datetime import time

from django.conf import settings
from django.db import models


class Einstellung(models.Model):
    """Benachrichtigungen per SMS; es gibt genau einen Datensatz.

    Gemeldet werden die Wiedervorlagen des Inhabers, der sie eingerichtet hat, und
    die ohne Zuständigen, dazu Rechnungen und Eingangsrechnungen (nachrichten.py).
    """

    VORLAUF = [
        (0, "nicht extra, nur in der Übersicht"),
        (15, "15 Minuten vorher"),
        (30, "30 Minuten vorher"),
        (60, "1 Stunde vorher"),
        (120, "2 Stunden vorher"),
    ]

    # Liest auch das Startprogramm (core/firmen.py, benachrichtigt).
    aktiv = models.BooleanField("SMS senden", default=False)
    handy = models.CharField("Handynummer", max_length=20, blank=True)
    api_schluessel = models.CharField(
        "API-Schlüssel von seven.io", max_length=200, blank=True
    )
    uhrzeit = models.TimeField("Tagesübersicht um", default=time(7, 30))
    vorlauf = models.PositiveSmallIntegerField(
        "Termine mit Uhrzeit", choices=VORLAUF, default=30
    )
    empfaenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    gesendet_am = models.DateTimeField(null=True, blank=True, editable=False)
    fehler = models.CharField(max_length=300, blank=True, editable=False)
    fehler_am = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Benachrichtigungen"
        verbose_name_plural = "Benachrichtigungen"

    def __str__(self):
        return "Benachrichtigungen"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def bereit(self):
        return bool(self.aktiv and self.handy and self.api_schluessel)


class Gemeldet(models.Model):
    """Was schon per SMS kam, damit nichts doppelt kommt."""

    anlass = models.CharField(max_length=20)
    schluessel = models.CharField(max_length=100)
    zeitpunkt = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["anlass", "schluessel"], name="einmal_gemeldet"
            )
        ]

    def __str__(self):
        return f"{self.anlass} {self.schluessel}"
