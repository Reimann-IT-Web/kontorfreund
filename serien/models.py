"""Serienrechnungen aus einer Teilnehmerliste (Spezifikation B-11).

`Liste` hält die hochgeladene Tabelle nur bis zum Anlegen der Entwürfe oder zum
Verwerfen, liegen gebliebene löscht das nächste Hochladen nach `AUFBEWAHREN`. Danach
stehen die Angaben nur noch in Adressen, Rechnungen und `Teilnehmer`; übersprungene
Zeilen (etwa Stornos mit Grund) speichert Kontorfreund nie.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from invoicing.models import Rechnung

AUFBEWAHREN = timedelta(days=1)
# Für Beilagen zur E-Mail (PDF).
BEILAGE_MB = 5


class Vorlage(models.Model):
    """Texte und Beilage der Serienrechnungen; es gibt genau einen Datensatz.

    Platzhalter siehe `serien.texte`; die Briefanrede setzt Kontorfreund selbst vor den
    Text vor den Positionen und in die E-Mail.
    """

    betreff = models.CharField(
        "Betreff", max_length=200, default="Rechnung für die Teilnahme am {termin}"
    )
    position = models.CharField(
        "Bezeichnung der Position",
        max_length=200,
        default="Teilnahme an „{thema}“ am {termin}",
    )
    kopftext = models.TextField(
        "Text vor den Positionen",
        blank=True,
        default="vielen Dank für Ihre Anmeldung. Ich berechne Ihnen die Teilnahme:",
    )
    fusstext = models.TextField(
        "Text nach den Positionen",
        blank=True,
        default="Den Zugang zur Veranstaltung finden Sie hier:\n{link}",
    )
    mail_betreff = models.CharField(
        "Betreff der E-Mail", max_length=200, default="Rechnung {nummer} – {thema}"
    )
    mail_text = models.TextField(
        "Text der E-Mail",
        default="anbei erhalten Sie die Rechnung {nummer} für die Teilnahme an "
        "„{thema}“ am {termin}.\n\nDen Zugang finden Sie hier: {link}",
    )
    # In der Datenbank, damit sie mit jeder Sicherung erhalten bleibt (wie das Logo).
    beilage = models.BinaryField("Beilage", blank=True, default=b"")
    beilage_name = models.CharField("Name der Beilage", max_length=200, blank=True)
    # Vorschläge für die nächste Serie.
    preis = models.DecimalField(
        "Preis", max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    zahlungsziel = models.PositiveSmallIntegerField("Zahlungsziel in Tagen", default=14)
    # Feld → Spaltentitel der zuletzt verwendeten Liste
    zuordnung = models.JSONField(default=dict, editable=False)

    class Meta:
        verbose_name = "Vorlage für Serienrechnungen"
        verbose_name_plural = "Vorlagen für Serienrechnungen"

    def __str__(self):
        return "Vorlage für Serienrechnungen"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Liste(models.Model):
    """Eine hochgeladene Teilnehmerliste zwischen Hochladen und Anlegen der Entwürfe."""

    dateiname = models.CharField(max_length=255)
    spalten = models.JSONField()
    # [[Zeilennummer in der Datei, [Werte je Spalte]], …]
    zeilen = models.JSONField()
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    erstellt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.dateiname

    @classmethod
    def aufraeumen(cls, benutzer):
        """Alte Listen aller Benutzer und die offenen dieses Benutzers."""
        cls.objects.filter(
            Q(erstellt__lt=timezone.now() - AUFBEWAHREN) | Q(benutzer=benutzer)
        ).delete()


class Serie(models.Model):
    """Die Rechnungen zu einem Termin, angelegt aus einer Teilnehmerliste."""

    termin = models.CharField("Termin", max_length=100)
    thema = models.CharField("Thema", max_length=300)
    link = models.CharField("Link", max_length=500, blank=True)
    leistungsdatum = models.DateField("Leistungsdatum")
    datum = models.DateField("Rechnungsdatum")
    preis = models.DecimalField("Preis", max_digits=12, decimal_places=2)
    zahlungsziel = models.PositiveSmallIntegerField("Zahlungsziel in Tagen")
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Serie"
        verbose_name_plural = "Serien"
        ordering = ["-erstellt", "-pk"]

    def __str__(self):
        return f"{self.thema} am {self.termin}"


class Teilnehmer(models.Model):
    """Wer zu einer Rechnung der Serie gehört; bei Vereinen nicht die Adresse selbst.

    Mit dem Entwurf gelöscht; festgeschriebene Rechnungen lassen sich nicht löschen.
    """

    serie = models.ForeignKey(
        Serie, on_delete=models.CASCADE, related_name="teilnehmer"
    )
    rechnung = models.OneToOneField(
        Rechnung, on_delete=models.CASCADE, related_name="teilnehmer"
    )
    zeile = models.PositiveIntegerField("Zeile der Liste")
    anrede = models.CharField("Anrede", max_length=10, blank=True)
    titel = models.CharField("Titel", max_length=50, blank=True)
    vorname = models.CharField("Vorname", max_length=100, blank=True)
    nachname = models.CharField("Nachname", max_length=100)
    email = models.EmailField("E-Mail", blank=True)
    beilage = models.BooleanField("Beilage mitsenden", default=True)

    class Meta:
        verbose_name = "Teilnehmer"
        verbose_name_plural = "Teilnehmer"
        ordering = ["zeile", "pk"]

    def __str__(self):
        return self.name

    @property
    def name(self):
        return " ".join(t for t in [self.titel, self.vorname, self.nachname] if t)

    @property
    def anschriftzeile(self):
        """Zeile in der Anschrift einer Firma, z. B. „Frau Dr. Jana Beispiel“."""
        return " ".join(t for t in [self.anrede, self.name] if t)
