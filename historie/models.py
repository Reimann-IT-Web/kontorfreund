from django.conf import settings
from django.db import models
from django.utils import timezone

from contacts.models import Kontakt


class Vorgang(models.Model):
    """Eintrag in der Kontakthistorie (Spezifikation K-2), von Hand erfasst.

    Belege, Zahlungen, Mahnungen und erledigte Wiedervorlagen stehen ebenfalls in
    der Zeitleiste, werden aber aus ihren eigenen Daten gelesen (`zeitleiste.py`).
    """

    class Art(models.TextChoices):
        NOTIZ = "notiz", "Notiz"
        ANRUF = "anruf", "Anruf"
        EMAIL = "email", "E-Mail"
        TERMIN = "termin", "Termin"

    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        on_delete=models.CASCADE,
        related_name="vorgaenge",
    )
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.NOTIZ)
    zeitpunkt = models.DateTimeField("Wann", default=timezone.now)
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    text = models.TextField("Text", blank=True)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Erfasst von",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vorgang"
        verbose_name_plural = "Vorgänge"
        ordering = ["-zeitpunkt", "-pk"]

    def __str__(self):
        return f"{self.get_art_display()}: {self.betreff or self.text[:60]}"
