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


# Steht nach dem Schwärzen statt der Bezeichnung im Eintrag.
GESCHWAERZT = "geschwärzt, gelöscht auf Verlangen (Art. 17 DSGVO)"


class Eintrag(models.Model):
    """Ein Eintrag im Änderungsprotokoll (Spezifikation K-6).

    Unveränderbar: save() legt nur an, delete() und update() gibt es weder am Eintrag
    noch an Abfragen. Einzige Ausnahme ist `schwaerzen`, wenn eine Person die Löschung
    ihrer Daten verlangt (contacts/datenschutz.py) oder abgelaufene Belege gelöscht
    werden (archive/fristen.py).
    """

    class Aktion(models.TextChoices):
        ANGELEGT = "angelegt", "Angelegt"
        GEAENDERT = "geaendert", "Geändert"
        GELOESCHT = "geloescht", "Gelöscht"
        ANMELDUNG = "anmeldung", "Angemeldet"
        FEHLVERSUCH = "fehlversuch", "Anmeldung fehlgeschlagen"
        ABLAGE = "ablage", "Abweichung in der Ablage"
        ZURUECK = "zurueck", "Aus der Sicherung zurückgeholt"
        AUSKUNFT = "auskunft", "Auskunft erteilt (Art. 15 DSGVO)"
        LOESCHUNG = "loeschung", "Gelöscht auf Verlangen (Art. 17 DSGVO)"
        FRISTEN = "fristen", "Aufbewahrungsfristen geprüft"

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

    @classmethod
    def schwaerzen(cls, art, objekt_ids, grund=GESCHWAERZT):
        """Bezeichnung und Werte gelöschter Objekte entfernen; Zeitpunkt, Benutzer und
        Aktion bleiben, damit das Protokoll lückenlos bleibt."""
        eintraege = cls.objects.filter(
            art=art, objekt_id__in=[str(pk) for pk in objekt_ids]
        )
        models.QuerySet.update(eintraege, beschreibung=grund, aenderungen=[])
