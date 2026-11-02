from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

# So lange bleibt eine hochgeladene Tabelle liegen, die niemand übernimmt.
AUFBEWAHREN = timedelta(days=1)


class Ziel(models.TextChoices):
    KONTAKTE = "kontakte", "Adressen"
    ARTIKEL = "artikel", "Artikel"


class Import(models.Model):
    """Eine hochgeladene Tabelle zwischen Hochladen und Übernahme.

    Nach der Übernahme oder dem Abbrechen wird sie gelöscht, liegen gebliebene
    nach `AUFBEWAHREN` beim nächsten Hochladen (`aufraeumen`).
    """

    ziel = models.CharField(max_length=10, choices=Ziel.choices)
    dateiname = models.CharField(max_length=255)
    spalten = models.JSONField()
    # [[Zeilennummer in der Datei, [Werte je Spalte]], …]
    zeilen = models.JSONField()
    # Feld → Spaltentitel
    zuordnung = models.JSONField(default=dict)
    vorlage = models.CharField(max_length=100, blank=True)
    # Kategorie für Adressen, wenn keine Spalte sie angibt.
    kategorie = models.CharField(max_length=12, default="kunde")
    dubletten_anlegen = models.BooleanField(default=False)
    # Der Nutzer hat die Zuordnung bestätigt; erst dann gibt es Probelauf und Übernahme.
    bestaetigt = models.BooleanField(default=False)
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    erstellt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.dateiname

    @classmethod
    def aufraeumen(cls, benutzer, ziel):
        """Alte Importe aller Benutzer und die offenen dieses Benutzers für dieses Ziel."""
        cls.objects.filter(
            Q(erstellt__lt=timezone.now() - AUFBEWAHREN)
            | Q(benutzer=benutzer, ziel=ziel)
        ).delete()


class Zuordnung(models.Model):
    """Gespeicherte Zuordnung von Spalten zu Feldern, als Vorlage für weitere Dateien."""

    ziel = models.CharField(max_length=10, choices=Ziel.choices)
    name = models.CharField("Name", max_length=100)
    # Feld → Spaltentitel
    felder = models.JSONField()
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["ziel", "name"], name="zuordnung_eindeutig")
        ]

    def __str__(self):
        return self.name
