from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from invoicing.models import Rechnung

# Mahnstufen (Spezifikation M-3)
STUFEN = {1: "Zahlungserinnerung", 2: "1. Mahnung", 3: "2. Mahnung"}
DATEINAME = {1: "Zahlungserinnerung", 2: "Mahnung-1", 3: "Mahnung-2"}


class Zahlung(models.Model):
    """Zahlungseingang zu einer Rechnung oder ein ausgebuchter Rest (Spezifikation M-2).

    `betrag` mindert den offenen Rechnungsbetrag, `nebenkosten` sind gezahlte
    Mahngebühren, Verzugszinsen und Pauschale; sie gehören nicht zur Rechnung.
    """

    class Art(models.TextChoices):
        UEBERWEISUNG = "ueberweisung", "Überweisung"
        BAR = "bar", "Bar"
        LASTSCHRIFT = "lastschrift", "Lastschrift"
        SONSTIGE = "sonstige", "Sonstige"
        AUSBUCHUNG = "ausbuchung", "Ausgebucht"
        SKONTO = "skonto", "Skonto"

    rechnung = models.ForeignKey(
        Rechnung, on_delete=models.PROTECT, related_name="zahlungen"
    )
    datum = models.DateField("Datum", default=date.today)
    betrag = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    nebenkosten = models.DecimalField(
        "davon Mahnkosten und Zinsen", max_digits=12, decimal_places=2, default=0
    )
    art = models.CharField(
        "Art", max_length=12, choices=Art.choices, default=Art.UEBERWEISUNG
    )
    notiz = models.CharField("Notiz", max_length=200, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Zahlung"
        verbose_name_plural = "Zahlungen"
        ordering = ["datum", "pk"]

    def __str__(self):
        return f"{self.get_art_display()} {self.betrag} € zu {self.rechnung}"

    @property
    def ist_ausbuchung(self):
        """Kein Geldeingang: ausgebuchter Rest oder abgezogenes Skonto."""
        return self.art in (self.Art.AUSBUCHUNG, self.Art.SKONTO)

    @property
    def ist_skonto(self):
        return self.art == self.Art.SKONTO

    @property
    def eingang(self):
        return self.betrag + self.nebenkosten


class Gesperrt(ValidationError):
    def __init__(self):
        super().__init__(
            "Die Mahnung ist erstellt und kann nicht mehr geändert werden."
        )


class Mahnung(models.Model):
    """Zahlungserinnerung oder Mahnung, beim Erstellen als PDF abgelegt."""

    NACHTRAEGLICH = {"versendet_am", "versendet_an"}

    rechnung = models.ForeignKey(
        Rechnung, on_delete=models.PROTECT, related_name="mahnungen"
    )
    stufe = models.PositiveSmallIntegerField("Stufe", choices=list(STUFEN.items()))
    datum = models.DateField("Datum", default=date.today)
    frist = models.DateField("Zahlen bis")
    offen = models.DecimalField(max_digits=12, decimal_places=2)
    gebuehr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zinsen = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pauschale = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Mahngebühren bis hierher, Zinsen bis zum Mahntag und Pauschale, vor Abzug gezahlter Nebenkosten
    nebenkosten = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gesamt = models.DecimalField(max_digits=12, decimal_places=2)
    beleg = models.JSONField(default=dict)
    datei = models.CharField(max_length=300)
    sha256 = models.CharField(max_length=64)
    versendet_am = models.DateTimeField(null=True, blank=True)
    versendet_an = models.CharField(max_length=300, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mahnung"
        verbose_name_plural = "Mahnungen"
        ordering = ["datum", "stufe", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["rechnung", "stufe"], name="eine_mahnung_je_stufe"
            )
        ]

    def __str__(self):
        return f"{self.bezeichnung} zu Rechnung {self.rechnung.nummer}"

    def save(self, *args, **kwargs):
        if self.pk:
            felder = set(kwargs.get("update_fields") or ())
            if not felder or not felder <= self.NACHTRAEGLICH:
                raise Gesperrt
        super().save(*args, **kwargs)

    @property
    def bezeichnung(self):
        return STUFEN[self.stufe]

    @property
    def dateiname(self):
        return f"{DATEINAME[self.stufe]}-{self.rechnung.nummer}.pdf"

    @property
    def anhaenge(self):
        return [(self.dateiname, self.datei, "application/pdf")]


class Mahnstufe(models.Model):
    """Einstellungen je Stufe: wann sie fällig ist, Frist, Gebühr und Text."""

    VORGABEN = {
        1: {
            "abstand": 7,
            "frist": 10,
            "zinsen": False,
            "text": "meine Rechnung {nummer} vom {datum} ist noch offen. Sie war am "
            "{faellig} fällig; vielleicht ist sie bei Ihnen untergegangen.\n\n"
            "Haben Sie inzwischen bezahlt, ist dieses Schreiben für Sie erledigt.",
        },
        2: {
            "abstand": 7,
            "frist": 10,
            "zinsen": True,
            "text": "auch nach meiner Zahlungserinnerung ist die Rechnung {nummer} vom "
            "{datum} noch offen. Bitte begleichen Sie jetzt den unten "
            "aufgeführten Betrag.\n\n"
            "Haben Sie inzwischen bezahlt, ist dieses Schreiben für Sie erledigt.",
        },
        3: {
            "abstand": 7,
            "frist": 7,
            "zinsen": True,
            "text": "die Rechnung {nummer} vom {datum} ist trotz Erinnerung und Mahnung "
            "weiterhin offen. Dies ist meine letzte Mahnung. Geht bis zum Ende der "
            "unten genannten Frist keine Zahlung ein, behalte ich mir vor, ohne "
            "weitere Ankündigung einen gerichtlichen Mahnbescheid zu beantragen.",
        },
    }
    PLATZHALTER = ("nummer", "datum", "faellig")

    stufe = models.PositiveSmallIntegerField(
        primary_key=True, choices=list(STUFEN.items())
    )
    abstand = models.PositiveSmallIntegerField(
        "Fällig nach Tagen",
        help_text="Tage nach Ablauf der vorigen Frist (bei der Zahlungserinnerung: "
        "nach Fälligkeit der Rechnung).",
    )
    frist = models.PositiveSmallIntegerField(
        "Neue Zahlungsfrist in Tagen", help_text="Ab dem Datum des Schreibens."
    )
    gebuehr = models.DecimalField(
        "Mahngebühr", max_digits=12, decimal_places=2, default=0
    )
    zinsen = models.BooleanField("Verzugszinsen berechnen", default=True)
    text = models.TextField(
        "Text",
        help_text="Steht nach der Anrede. Platzhalter: {nummer}, {datum} und "
        "{faellig} der Rechnung. Betrag, Frist und Bankverbindung druckt "
        "Kontorfreund selbst darunter.",
    )

    class Meta:
        ordering = ["stufe"]
        verbose_name = "Mahnstufe"
        verbose_name_plural = "Mahnstufen"

    def __str__(self):
        return STUFEN[self.stufe]

    @classmethod
    def alle(cls):
        """Die drei Stufen; fehlende werden mit den Vorgaben angelegt."""
        return {
            stufe: cls.objects.get_or_create(stufe=stufe, defaults=vorgabe)[0]
            for stufe, vorgabe in cls.VORGABEN.items()
        }

    def text_fuer(self, rechnung):
        """Text mit den Angaben der Rechnung; nur die bekannten Platzhalter."""
        werte = {
            "nummer": rechnung.nummer,
            "datum": f"{rechnung.datum:%d.%m.%Y}",
            "faellig": f"{rechnung.faellig:%d.%m.%Y}",
        }
        text = self.text
        for name in self.PLATZHALTER:
            text = text.replace("{" + name + "}", werte[name])
        return text


class Basiszins(models.Model):
    """Basiszinssatz nach § 247 BGB, gilt ab dem 1. Januar bzw. 1. Juli."""

    gueltig_ab = models.DateField("Gültig ab", unique=True)
    satz = models.DecimalField(
        "Basiszinssatz in Prozent", max_digits=5, decimal_places=2
    )

    class Meta:
        ordering = ["-gueltig_ab"]
        verbose_name = "Basiszinssatz"
        verbose_name_plural = "Basiszinssätze"

    def __str__(self):
        return f"{self.satz} % ab {self.gueltig_ab:%d.%m.%Y}"

    @classmethod
    def am(cls, tag):
        eintrag = cls.objects.filter(gueltig_ab__lte=tag).first()
        return eintrag.satz if eintrag else None

    @classmethod
    def veraltet(cls, heute=None):
        """Ob der letzte Eintrag vor dem jüngsten Stichtag (1.1. oder 1.7.) liegt."""
        heute = heute or date.today()
        stichtag = date(heute.year, 7 if heute.month >= 7 else 1, 1)
        letzter = cls.objects.first()
        return letzter is None or letzter.gueltig_ab < stichtag
