from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Unveraenderbar(ValidationError):
    def __init__(self):
        super().__init__("Das Protokoll lässt sich nicht ändern oder löschen.")


class EintragQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise Unveraenderbar

    def delete(self):
        raise Unveraenderbar


class Eintrag(models.Model):
    """Ein Eintrag im Änderungsprotokoll (Spezifikation K-6).

    Unveränderbar: save() legt nur an, delete() und update() gibt es weder am Eintrag
    noch an Abfragen. Löschen nach Ablauf der Aufbewahrung kommt mit 05-betrieb.
    """

    class Aktion(models.TextChoices):
        ANGELEGT = "angelegt", "Angelegt"
        GEAENDERT = "geaendert", "Geändert"
        GELOESCHT = "geloescht", "Gelöscht"
        ANMELDUNG = "anmeldung", "Angemeldet"
        FEHLVERSUCH = "fehlversuch", "Anmeldung fehlgeschlagen"
        ABLAGE = "ablage", "Abweichung in der Ablage"
        ZURUECK = "zurueck", "Aus der Sicherung zurückgeholt"

    zeit = models.DateTimeField(default=timezone.now)
    # Kein Fremdschlüssel: Das Protokoll bleibt, auch wenn es den Benutzer nicht mehr gibt.
    benutzer_id = models.PositiveIntegerField(null=True, blank=True)
    wer = models.CharField(max_length=254, blank=True)
    aktion = models.CharField(max_length=12, choices=Aktion.choices)
    art = models.CharField(max_length=50, blank=True)
    objekt_id = models.CharField(max_length=40, blank=True)
    # Bezeichnung des Objekts zum Zeitpunkt, bei Anmeldungen der Grund
    beschreibung = models.CharField(max_length=300, blank=True)
    # [[Feld, alter Wert, neuer Wert], …] als Text, wie er auf dem Bildschirm stand
    aenderungen = models.JSONField(default=list)

    objects = EintragQuerySet.as_manager()

    class Meta:
        verbose_name = "Protokolleintrag"
        verbose_name_plural = "Protokoll"
        ordering = ["-zeit", "-pk"]

    def __str__(self):
        return f"{self.zeit:%d.%m.%Y %H:%M} {self.get_aktion_display()} {self.beschreibung}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise Unveraenderbar
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise Unveraenderbar
