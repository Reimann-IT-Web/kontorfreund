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


class Kategorie(models.Model):
    """Kategorie von Adressen, frei anzulegen, mehrere je Adresse (Spezifikation K-1).

    Kunde, Interessent und Lieferant gibt es von Anfang an. Das Programm findet sie
    über `kennung` (Lieferanten etwa bei Eingangsrechnungen); deshalb lassen sie sich
    umbenennen, aber nicht löschen.
    """

    class Kennung(models.TextChoices):
        KUNDE = "kunde", "Kunde"
        INTERESSENT = "interessent", "Interessent"
        LIEFERANT = "lieferant", "Lieferant"

    name = models.CharField("Name", max_length=50, unique=True)
    kennung = models.CharField(
        max_length=12, choices=Kennung.choices, blank=True, editable=False
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["kennung"],
                condition=~models.Q(kennung=""),
                name="kategorie_kennung_eindeutig",
            )
        ]
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"

    def __str__(self):
        return self.name

    @classmethod
    def vorgabe(cls, kennung):
        return cls.objects.get_or_create(
            kennung=kennung, defaults={"name": cls.Kennung(kennung).label}
        )[0]


class Kontakt(models.Model):
    """Eine Adresse: Firma (mit optionalem Ansprechpartner) oder Person."""

    class Art(models.TextChoices):
        FIRMA = "firma", "Firma"
        PERSON = "person", "Person"

    nummer = models.PositiveIntegerField("Nummer", unique=True, editable=False)
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.FIRMA)
    kategorien = models.ManyToManyField(
        Kategorie, verbose_name="Kategorien", blank=True, related_name="kontakte"
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
    position = models.CharField("Position", max_length=100, blank=True)
    # Nur bei Personen: die Firma, bei der sie Ansprechpartner sind (Spezifikation K-1).
    firma = models.ForeignKey(
        "self",
        verbose_name="Ansprechpartner bei",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="personen",
        limit_choices_to={"art": "firma"},
    )
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
    # Auf Verlangen der Person, solange Belege aufbewahrt werden müssen (contacts/datenschutz.py).
    gesperrt_am = models.DateTimeField(
        "Gesperrt nach Art. 18 DSGVO", null=True, blank=True
    )
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
        if self.art == self.Art.FIRMA:
            self.firma = None
        if self.nummer is None:
            hoechste = Kontakt.objects.aggregate(m=Max("nummer"))["m"] or 0
            self.nummer = hoechste + 1
        super().save(*args, **kwargs)

    def clean(self):
        if self.art == self.Art.FIRMA and not self.firmenname.strip():
            raise ValidationError({"firmenname": "Bitte geben Sie den Firmennamen an."})
        if self.art == self.Art.PERSON and not self.nachname.strip():
            raise ValidationError({"nachname": "Bitte geben Sie den Nachnamen an."})
        if self.art == self.Art.PERSON and self.pk and self.personen.exists():
            raise ValidationError(
                {
                    "art": "Diese Firma hat Ansprechpartner. Ordnen Sie sie zuerst einer "
                    "anderen Firma zu, bevor Sie daraus eine Person machen."
                }
            )
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
    def auswahlname(self):
        """Für die Empfängerauswahl, z. B. „Betreuung – Lena Brandt, Alzey (K-0012)“.

        Ansprechpartner und Ort unterscheiden Firmen, die gleich heißen.
        """
        zusatz = ", ".join(t for t in [self.ansprechpartner, self.ort] if t)
        name = f"{self.anzeigename} – {zusatz}" if zusatz else self.anzeigename
        return f"{name} ({self.kundennummer})"

    @property
    def kategorien_text(self):
        return ", ".join(k.name for k in self.kategorien.all())

    @property
    def weitere_telefon(self):
        return [w for w in self.kontaktwege.all() if w.art == Kontaktweg.Art.TELEFON]

    @property
    def weitere_email(self):
        return [w for w in self.kontaktwege.all() if w.art == Kontaktweg.Art.EMAIL]

    @property
    def kontaktwege_text(self):
        """Weitere Telefonnummern und E-Mail-Adressen, je eine Zeile."""
        return "\n".join(str(w) for w in self.kontaktwege.all())

    @property
    def anschrift_vollstaendig(self):
        return bool(self.strasse and self.plz and self.ort)

    @property
    def anschriften_text(self):
        """Weitere Anschriften, je eine Zeile."""
        return "\n".join(str(a) for a in self.anschriften.all())

    def anschrift_fuer(self, art):
        """Die erste weitere Anschrift dieser Art, sonst None."""
        return next((a for a in self.anschriften.all() if a.art == art), None)

    @property
    def ist_verbraucher(self):
        """Personen gelten beim Verzug als Verbraucher (§ 288 Abs. 1 und 2 BGB)."""
        return self.art == self.Art.PERSON

    def anschrift_zeilen(self, anschrift=None):
        """Anschrift für Belege, Zeile für Zeile; ohne `anschrift` die Standardanschrift.

        Die Zusatzzeile einer weiteren Anschrift steht anstelle des Ansprechpartners.
        """
        quelle = anschrift or self
        zeilen = [self.anzeigename]
        if self.art == self.Art.FIRMA and self.zusatz:
            zeilen.append(self.zusatz)
        if anschrift and anschrift.zusatz:
            zeilen.append(anschrift.zusatz)
        elif self.art == self.Art.FIRMA and self.ansprechpartner:
            zeilen.append(" ".join(t for t in [self.anrede, self.ansprechpartner] if t))
        if quelle.strasse:
            zeilen.append(quelle.strasse)
        if quelle.plz or quelle.ort:
            zeilen.append(f"{quelle.plz} {quelle.ort}".strip())
        if quelle.land and quelle.land != "Deutschland":
            zeilen.append(quelle.land)
        return zeilen


class Anschrift(models.Model):
    """Weitere Anschrift einer Adresse, z. B. für Rechnungen oder Lieferungen (K-1).

    Die Standardanschrift steht in `Kontakt` selbst. Belege wählen eine weitere über
    `anschrift` (Empfänger) und `lieferanschrift`; auf festgeschriebenen und fertigen
    Belegen bleibt sie erhalten (`contacts.forms.anschriften_lesen`).
    """

    class Art(models.TextChoices):
        RECHNUNG = "rechnung", "Rechnung"
        LIEFERUNG = "lieferung", "Lieferung"
        SONSTIGE = "sonstige", "Sonstige"

    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        on_delete=models.CASCADE,
        related_name="anschriften",
    )
    art = models.CharField("Art", max_length=10, choices=Art.choices)
    zusatz = models.CharField("Zusatz", max_length=200, blank=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=200)
    plz = models.CharField("PLZ", max_length=10)
    ort = models.CharField("Ort", max_length=100)
    land = models.CharField("Land", max_length=100, blank=True, default="Deutschland")

    class Meta:
        ordering = ["pk"]
        verbose_name = "Anschrift"
        verbose_name_plural = "Anschriften"

    def __str__(self):
        teile = [self.zusatz, self.strasse, f"{self.plz} {self.ort}".strip()]
        if self.land and self.land != "Deutschland":
            teile.append(self.land)
        return f"{self.get_art_display()}: {', '.join(t for t in teile if t)}"

    @property
    def bezeichnung(self):
        """Überschrift in der Anzeige, z. B. „Lieferanschrift“."""
        return {
            self.Art.RECHNUNG: "Rechnungsanschrift",
            self.Art.LIEFERUNG: "Lieferanschrift",
        }.get(self.art, "Weitere Anschrift")

    @property
    def anschrift_vollstaendig(self):
        return bool(self.strasse and self.plz and self.ort)


class Kontaktweg(models.Model):
    """Weitere Telefonnummer oder E-Mail-Adresse einer Adresse, z. B. „Mobil“ (K-1).

    Die erste steht in `Kontakt.telefon` bzw. `Kontakt.email`; an diese E-Mail-Adresse
    gehen Rechnungen.
    """

    class Art(models.TextChoices):
        TELEFON = "telefon", "Telefon"
        EMAIL = "email", "E-Mail"

    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        on_delete=models.CASCADE,
        related_name="kontaktwege",
    )
    art = models.CharField("Art", max_length=10, choices=Art.choices)
    bezeichnung = models.CharField("Bezeichnung", max_length=50, blank=True)
    wert = models.CharField("Nummer oder Adresse", max_length=254)

    class Meta:
        ordering = ["pk"]
        verbose_name = "Telefonnummer oder E-Mail-Adresse"
        verbose_name_plural = "Telefonnummern und E-Mail-Adressen"

    def __str__(self):
        return f"{self.bezeichnung}: {self.wert}" if self.bezeichnung else self.wert
