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


# Grobadressierung, optionale Feinadressierung, zwei Prüfziffern, z. B. 991-01234-38.
LEITWEG_ID = re.compile(r"\d{2,12}(-[0-9A-Z]{1,30})?-\d{2}")


def ist_leitweg_id(wert):
    return bool(LEITWEG_ID.fullmatch(wert.strip().upper()))


def kaeuferreferenz_pruefen(wert):
    """Sieht der Wert wie eine Leitweg-ID aus, muss ihre Prüfziffer stimmen (ISO 7064, MOD 97-10)."""
    if not ist_leitweg_id(wert):
        return
    ziffern = "".join(str(int(z, 36)) for z in wert.strip().upper().replace("-", ""))
    if int(ziffern) % 97 != 1:
        raise ValidationError(
            "Die Prüfziffer der Leitweg-ID stimmt nicht. Bitte auf Tippfehler prüfen."
        )


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
    kaeuferreferenz = models.CharField(
        "Käuferreferenz oder Leitweg-ID",
        max_length=100,
        blank=True,
        validators=[kaeuferreferenz_pruefen],
    )
    xrechnung = models.BooleanField(
        "Rechnungen zusätzlich als XRechnung", default=False
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
        self.kaeuferreferenz = self.kaeuferreferenz.strip()
        if ist_leitweg_id(self.kaeuferreferenz):
            self.kaeuferreferenz = self.kaeuferreferenz.upper()
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
        if self.xrechnung and not self.kaeuferreferenz.strip():
            raise ValidationError(
                {
                    "kaeuferreferenz": "Für die XRechnung braucht es eine Käuferreferenz, bei Behörden die Leitweg-ID."
                }
            )
        # Elektronische Adresse des Käufers (BT-49): Leitweg-ID oder E-Mail.
        if self.xrechnung and not (ist_leitweg_id(self.kaeuferreferenz) or self.email):
            raise ValidationError(
                {
                    "email": "Für die XRechnung braucht es eine E-Mail-Adresse, wenn die Käuferreferenz keine Leitweg-ID ist."
                }
            )

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

    @property
    def ist_verbraucher(self):
        """Personen gelten beim Verzug als Verbraucher (§ 288 Abs. 1 und 2 BGB)."""
        return self.art == self.Art.PERSON

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
