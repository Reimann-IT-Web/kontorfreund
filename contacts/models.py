import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max


def ust_id_pruefen(wert):
    """Format einer USt-IdNr.: Ländercode plus Kennung, für Deutschland DE und 9 Ziffern."""
    wert = wert.replace(" ", "").upper()
    if wert.startswith("DE"):
        if not re.fullmatch(r"DE\d{9}", wert):
            raise ValidationError(
                "Eine deutsche USt-IdNr. besteht aus „DE“ und 9 Ziffern, z. B. DE123456789."
            )
    elif not re.fullmatch(r"[A-Z]{2}[0-9A-Z+*]{2,12}", wert):
        raise ValidationError("Bitte mit dem Ländercode beginnen, z. B. DE123456789.")


class Kontakt(models.Model):
    """Eine Adresse: Firma (mit optionalem Ansprechpartner) oder Person."""

    class Art(models.TextChoices):
        FIRMA = "firma", "Firma"
        PERSON = "person", "Person"

    class Kategorie(models.TextChoices):
        KUNDE = "kunde", "Kunde"
        INTERESSENT = "interessent", "Interessent"
        LIEFERANT = "lieferant", "Lieferant"

    nummer = models.PositiveIntegerField("Nummer", unique=True, editable=False)
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.FIRMA)
    kategorie = models.CharField(
        "Kategorie", max_length=12, choices=Kategorie.choices, default=Kategorie.KUNDE
    )
    firmenname = models.CharField("Firmenname", max_length=200, blank=True)
    zusatz = models.CharField("Namenszusatz", max_length=200, blank=True)
    anrede = models.CharField(
        "Anrede",
        max_length=10,
        blank=True,
        choices=[("", "keine"), ("Frau", "Frau"), ("Herr", "Herr")],
    )
    titel = models.CharField("Titel", max_length=50, blank=True)
    vorname = models.CharField("Vorname", max_length=100, blank=True)
    nachname = models.CharField("Nachname", max_length=100, blank=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    land = models.CharField("Land", max_length=100, blank=True, default="Deutschland")
    email = models.EmailField("E-Mail", blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    website = models.CharField("Website", max_length=200, blank=True)
    ust_id = models.CharField(
        "USt-IdNr.", max_length=20, blank=True, validators=[ust_id_pruefen]
    )
    notiz = models.TextField("Notiz", blank=True)
    archiviert = models.BooleanField(default=False)
    # Gespeicherter Anzeigename, damit Listen ohne Umrechnen sortieren und suchen können.
    anzeigename = models.CharField(max_length=300, editable=False, db_index=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["anzeigename"]
        verbose_name = "Adresse"
        verbose_name_plural = "Adressen"

    def __str__(self):
        return self.anzeigename

    def save(self, *args, **kwargs):
        self.ust_id = self.ust_id.replace(" ", "").upper()
        self.anzeigename = self.name_berechnen()
        if self.nummer is None:
            hoechste = Kontakt.objects.aggregate(m=Max("nummer"))["m"] or 0
            self.nummer = hoechste + 1
        super().save(*args, **kwargs)

    def clean(self):
        if self.art == self.Art.FIRMA and not self.firmenname.strip():
            raise ValidationError({"firmenname": "Bitte geben Sie den Firmennamen an."})
        if self.art == self.Art.PERSON and not self.nachname.strip():
            raise ValidationError({"nachname": "Bitte geben Sie den Nachnamen an."})

    def name_berechnen(self):
        if self.art == self.Art.FIRMA:
            return self.firmenname.strip()
        return " ".join(t for t in [self.vorname.strip(), self.nachname.strip()] if t)

    @property
    def kundennummer(self):
        return f"K-{self.nummer:04d}"

    @property
    def ansprechpartner(self):
        """Bei Firmen die Person dahinter, z. B. „Dr. Lea Sommer“."""
        if self.art != self.Art.FIRMA:
            return ""
        return " ".join(t for t in [self.titel, self.vorname, self.nachname] if t)

    @property
    def anschrift_vollstaendig(self):
        return bool(self.strasse and self.plz and self.ort)

    def anschrift_zeilen(self):
        """Anschrift für Belege, Zeile für Zeile."""
        zeilen = [self.anzeigename]
        if self.art == self.Art.FIRMA and self.zusatz:
            zeilen.append(self.zusatz)
        if self.art == self.Art.FIRMA and self.ansprechpartner:
            zeilen.append(" ".join(t for t in [self.anrede, self.ansprechpartner] if t))
        if self.strasse:
            zeilen.append(self.strasse)
        if self.plz or self.ort:
            zeilen.append(f"{self.plz} {self.ort}".strip())
        if self.land and self.land != "Deutschland":
            zeilen.append(self.land)
        return zeilen
