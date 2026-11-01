import secrets
from datetime import time

from django.conf import settings
from django.db import models


def neuer_code():
    return secrets.token_urlsafe(12)


class Einstellung(models.Model):
    """Benachrichtigungen über Telegram; es gibt genau einen Datensatz.

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
    aktiv = models.BooleanField("Nachrichten senden", default=False)
    bot_schluessel = models.CharField("Bot-Schlüssel", max_length=100, blank=True)
    uhrzeit = models.TimeField("Tagesübersicht um", default=time(7, 30))
    vorlauf = models.PositiveSmallIntegerField(
        "Termine mit Uhrzeit", choices=VORLAUF, default=30
    )
    # Ergebnis der Verbindung (telegram.py), nicht von Hand änderbar.
    bot_name = models.CharField(max_length=100, blank=True, editable=False)
    chat = models.CharField(max_length=30, blank=True, editable=False)
    code = models.CharField(max_length=30, default=neuer_code, editable=False)
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
    def verbunden(self):
        return bool(self.bot_schluessel and self.chat)

    @property
    def bereit(self):
        return self.aktiv and self.verbunden

    @property
    def link(self):
        """Öffnet den Bot in Telegram; „Starten“ schickt dort den Code."""
        return f"https://t.me/{self.bot_name}?start={self.code}"

    def trennen(self):
        self.chat = ""
        self.aktiv = False
        self.code = neuer_code()


class Gemeldet(models.Model):
    """Was schon gemeldet ist, damit nichts doppelt kommt."""

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
