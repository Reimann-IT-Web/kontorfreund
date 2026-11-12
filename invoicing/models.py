import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from archive.models import Altbeleg
from contacts.models import Anschrift, Kontakt, ist_leitweg_id
from core.templatetags.kf import euro

CENT = Decimal("0.01")
UST_SATZ = Decimal("19")


def runden(wert):
    return wert.quantize(CENT, rounding=ROUND_HALF_UP)


def rabatt_betrag(zwischensumme, prozent):
    """Rabatt auf die Summe der Positionen, kaufmännisch gerundet (bei Storno negativ)."""
    return runden(zwischensumme * prozent / 100)


def summen(positionen, steuerfall, rabatt=Decimal("0")):
    """(netto, ust, brutto) aus den Positionen eines Belegs nach Abzug des Rabatts in
    Prozent, kaufmännisch gerundet."""
    zwischensumme = sum((p.gesamt for p in positionen), Decimal("0.00"))
    netto = zwischensumme - rabatt_betrag(zwischensumme, rabatt)
    ust = (
        runden(netto * UST_SATZ / 100)
        if steuerfall == Rechnung.Steuerfall.REGEL
        else Decimal("0.00")
    )
    return netto, ust, netto + ust


def steuerhinweis(steuerfall, firma):
    """Pflichthinweis zur Umsatzsteuer; bei steuerfreien Leistungen aus den Firmendaten."""
    if steuerfall == Rechnung.Steuerfall.STEUERFREI:
        return firma.steuerfrei_hinweis.strip()
    return Rechnung.STEUERHINWEIS[steuerfall]


def hinweis_fehlt(steuerfall, firma):
    """Ohne Hinweis auf die Befreiung fehlt eine Pflichtangabe (§ 14 Abs. 4 S. 1 Nr. 8 UStG)."""
    return steuerfall == Rechnung.Steuerfall.STEUERFREI and not steuerhinweis(
        steuerfall, firma
    )


HINWEIS_FEHLT = "Hinweis auf die Steuerbefreiung"


class Festgeschrieben(ValidationError):
    """Festgeschriebene Rechnungen sind unveränderbar (GoBD).

    Korrigiert wird nur per Stornorechnung oder Rechnungskorrektur.
    """

    def __init__(self):
        super().__init__(
            "Die Rechnung ist festgeschrieben und kann nicht mehr geändert werden."
        )


class Rechnung(models.Model):
    class Status(models.TextChoices):
        ENTWURF = "entwurf", "Entwurf"
        FESTGESCHRIEBEN = "festgeschrieben", "Festgeschrieben"

    class Steuerfall(models.TextChoices):
        KLEINUNTERNEHMER = "kleinunternehmer", "§ 19 – Kleinunternehmer, keine USt"
        REGEL = "regel", "19 % Umsatzsteuer ausweisen"
        UMKEHR = "13b", "§ 13b – Kunde schuldet die Steuer"
        STEUERFREI = "steuerfrei", "§ 4 – steuerfreie Leistung, keine USt"

    # Steuerfreie Leistungen: Wortlaut aus Firmendaten.steuerfrei_hinweis (steuerhinweis()).
    STEUERHINWEIS = {
        Steuerfall.KLEINUNTERNEHMER: "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        Steuerfall.REGEL: "",
        Steuerfall.UMKEHR: "Steuerschuldnerschaft des Leistungsempfängers.",
    }

    # Nach dem Festschreiben dürfen sich nur noch diese Felder ändern.
    NACHTRAEGLICH = {"versendet_am", "versendet_an"}
    # Angaben, die eine Kopie oder Stornorechnung vom Original übernimmt.
    KOPIERT = (
        "kontakt",
        "anschrift",
        "lieferanschrift",
        "leistung_von",
        "leistung_bis",
        "zahlungsziel",
        "skonto_prozent",
        "skonto_tage",
        "rabatt_prozent",
        "steuerfall",
        "referenz",
        "betreff",
        "kopftext",
        "fusstext",
        "girocode",
        "verzugshinweis",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ENTWURF
    )
    nummer = models.CharField("Rechnungsnummer", max_length=20, blank=True)
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Empfänger",
        on_delete=models.PROTECT,
        related_name="rechnungen",
        null=True,
        blank=True,
    )
    # Weitere Anschriften des Empfängers (K-1); leer heißt Standardanschrift bzw. keine.
    anschrift = models.ForeignKey(
        Anschrift,
        verbose_name="Anschrift",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    lieferanschrift = models.ForeignKey(
        Anschrift,
        verbose_name="Lieferanschrift",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    datum = models.DateField("Rechnungsdatum", default=date.today)
    leistung_von = models.DateField("Leistung von", null=True, blank=True)
    leistung_bis = models.DateField("Leistung bis", null=True, blank=True)
    zahlungsziel = models.PositiveSmallIntegerField("Zahlungsziel in Tagen", default=14)
    skonto_prozent = models.DecimalField(
        "Skonto in Prozent", max_digits=4, decimal_places=2, default=0
    )
    skonto_tage = models.PositiveSmallIntegerField(
        "Skonto innerhalb von Tagen", default=0
    )
    # Auf die Summe der Positionen; Korrektur und Storno übernehmen ihn vom Original.
    rabatt_prozent = models.DecimalField(
        "Rabatt in Prozent", max_digits=5, decimal_places=2, default=0
    )
    steuerfall = models.CharField(
        max_length=20, choices=Steuerfall.choices, default=Steuerfall.KLEINUNTERNEHMER
    )
    referenz = models.CharField("Käuferreferenz", max_length=100, blank=True)
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    kopftext = models.TextField("Text vor den Positionen", blank=True)
    fusstext = models.TextField("Text nach den Positionen", blank=True)
    girocode = models.BooleanField("GiroCode drucken", default=True)
    # Wirkt nur bei Verbrauchern, siehe zahlungen/zinsen.py.
    verzugshinweis = models.BooleanField(
        "Hinweis auf Zahlungsverzug drucken", default=True
    )
    storno_zu = models.OneToOneField(
        "self",
        verbose_name="Storniert die Rechnung",
        on_delete=models.PROTECT,
        related_name="stornorechnung",
        null=True,
        blank=True,
        editable=False,
    )
    korrektur_zu = models.ForeignKey(
        "self",
        verbose_name="Korrigiert die Rechnung",
        on_delete=models.PROTECT,
        related_name="korrekturen",
        null=True,
        blank=True,
        editable=False,
    )

    # Beim Festschreiben eingefroren: genau die Angaben, aus denen PDF und XML entstanden.
    beleg = models.JSONField(default=dict, editable=False)
    netto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ust = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    brutto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    datei = models.CharField(max_length=300, blank=True, editable=False)
    sha256 = models.CharField(max_length=64, blank=True, editable=False)
    # Nur bei XRechnung: dieselbe XML wie im PDF, als eigenes maßgebliches Original.
    xml_datei = models.CharField(max_length=300, blank=True, editable=False)
    xml_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    festgeschrieben_am = models.DateTimeField(null=True, blank=True, editable=False)

    versendet_am = models.DateTimeField(null=True, blank=True)
    versendet_an = models.CharField(max_length=300, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
        ordering = ["-datum", "-nummer", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["nummer"],
                condition=~Q(nummer=""),
                name="rechnungsnummer_eindeutig",
            )
        ]

    def __str__(self):
        return (
            f"{self.bezeichnung} {self.nummer}" if self.nummer else "Rechnungsentwurf"
        )

    def save(self, *args, **kwargs):
        if self.pk and self._war_festgeschrieben():
            felder = set(kwargs.get("update_fields") or ())
            if not felder or not felder <= self.NACHTRAEGLICH | {"geaendert"}:
                raise Festgeschrieben
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._war_festgeschrieben():
            raise Festgeschrieben
        return super().delete(*args, **kwargs)

    def _war_festgeschrieben(self):
        return Rechnung.objects.filter(
            pk=self.pk, status=self.Status.FESTGESCHRIEBEN
        ).exists()

    @property
    def ist_entwurf(self):
        return self.status == self.Status.ENTWURF

    @property
    def ist_storno(self):
        return self.storno_zu_id is not None

    @property
    def storniert(self):
        return hasattr(self, "stornorechnung")

    @property
    def ist_korrektur(self):
        return self.korrektur_zu_id is not None

    @property
    def bezeichnung(self):
        if self.ist_storno:
            return "Stornorechnung"
        return "Rechnungskorrektur" if self.ist_korrektur else "Rechnung"

    @property
    def korrigierter_betrag(self):
        """Was nach Stornorechnung und festgeschriebenen Korrekturen noch zu zahlen bleibt."""
        if self.storniert:
            return Decimal("0.00")
        return self.brutto + sum(
            (k.brutto for k in self.korrekturen.all() if not k.ist_entwurf),
            Decimal("0.00"),
        )

    # ---------- Offener Posten (App zahlungen: Zahlung, Mahnung) ----------

    @property
    def ist_posten(self):
        """Festgeschriebene Rechnung, die bezahlt werden muss.

        Stornorechnungen und Korrekturen mindern nur das Original.
        """
        return not (self.ist_entwurf or self.ist_storno or self.ist_korrektur)

    @property
    def bezahlt(self):
        return sum(
            (z.betrag for z in self.zahlungen.all() if not z.ist_ausbuchung),
            Decimal("0.00"),
        )

    @property
    def ausgebucht(self):
        return sum(
            (z.betrag for z in self.zahlungen.all() if z.ist_ausbuchung),
            Decimal("0.00"),
        )

    @property
    def offen(self):
        """Noch zu zahlen; negativ, wenn der Kunde zu viel gezahlt hat."""
        if not self.ist_posten:
            return Decimal("0.00")
        return self.korrigierter_betrag - self.bezahlt - self.ausgebucht

    @property
    def ueberfaellig(self):
        return self.offen > 0 and self.faellig < date.today()

    @property
    def zahlstand(self):
        """bezahlt, teilbezahlt, ueberfaellig, offen, ueberzahlt, ausgebucht,
        erledigt (auf null korrigiert) oder storniert."""
        offen = self.offen
        if offen < 0:
            return "ueberzahlt"
        if self.storniert:
            return "storniert"
        if offen == 0:
            if self.bezahlt > 0:
                return "bezahlt"
            return "ausgebucht" if self.ausgebucht else "erledigt"
        if self.ueberfaellig:
            return "ueberfaellig"
        return "teilbezahlt" if offen < self.korrigierter_betrag else "offen"

    @property
    def korrigierbar(self):
        """Ob eine Rechnungskorrektur noch etwas mindern kann."""
        return (
            not self.ist_entwurf
            and not self.ist_storno
            and not self.ist_korrektur
            and self.korrigierter_betrag > 0
        )

    @property
    def kaeuferreferenz(self):
        """Käuferreferenz (BT-10): von der Rechnung, sonst aus der Adresse."""
        return self.referenz or (self.kontakt.kaeuferreferenz if self.kontakt else "")

    @property
    def faellig(self):
        return self.datum + timedelta(days=self.zahlungsziel)

    @property
    def skonto_bis(self):
        return self.datum + timedelta(days=self.skonto_tage)

    @property
    def skonto(self):
        """Skonto auf den zu zahlenden Betrag; 0, wenn keins vereinbart ist."""
        return runden(self.korrigierter_betrag * self.skonto_prozent / 100)

    @property
    def skonto_offen(self):
        """Ob der Kunde heute noch mit Skonto zahlen kann."""
        return (
            self.skonto_prozent > 0
            and self.offen > 0
            and date.today() <= self.skonto_bis
            and not any(z.ist_skonto for z in self.zahlungen.all())
        )

    @property
    def anhaenge(self):
        """Dateien für den Versand: (Dateiname, Pfad im Datenordner, MIME-Typ)."""
        name = f"{self.bezeichnung}-{self.nummer}"
        dateien = [(f"{name}.pdf", self.datei, "application/pdf")]
        if self.xml_datei:
            dateien.append((f"{name}.xml", self.xml_datei, "application/xml"))
        return dateien

    def summen(self):
        """(netto, ust, brutto) aus den Positionen nach Rabatt, kaufmännisch gerundet."""
        return summen(self.positionen.all(), self.steuerfall, self.rabatt_prozent)

    def fehlende_angaben(self, firma):
        """Pflichtangaben nach § 14 Abs. 4 UStG, die noch fehlen."""
        fehlt = []
        if not (
            self.kontakt and (self.anschrift or self.kontakt).anschrift_vollstaendig
        ):
            fehlt.append("Empfänger mit Anschrift")
        if not firma.vollstaendig:
            fehlt.append("Ihre Firmendaten")
        positionen = list(self.positionen.all())
        # Eine Rechnungskorrektur mindert nur: jede Position mit negativer Menge.
        if not positionen or any(
            not p.bezeichnung or (p.menge >= 0 if self.ist_korrektur else p.menge <= 0)
            for p in positionen
        ):
            fehlt.append("Menge und Art der Leistung")
        if not self.leistung_von or (
            self.leistung_bis and self.leistung_bis < self.leistung_von
        ):
            fehlt.append("Leistungszeitraum")
        brutto = self.summen()[2]
        if self.ist_korrektur:
            hoechstens = self.korrektur_zu.korrigierter_betrag
            if not 0 < -brutto <= hoechstens:
                fehlt.append(f"Korrekturbetrag (höchstens {euro(hoechstens)})")
        elif brutto <= 0:
            fehlt.append("Rechnungsbetrag")
        # Die Korrektur übernimmt den Hinweis des Originals (beleg.beleg_daten).
        if not self.ist_korrektur and hinweis_fehlt(self.steuerfall, firma):
            fehlt.append(HINWEIS_FEHLT)
        if self.kontakt and self.kontakt.xrechnung:
            fehlt += self._fehlt_fuer_xrechnung(firma)
        return fehlt

    def _fehlt_fuer_xrechnung(self, firma):
        """Was die XRechnung zusätzlich verlangt (BR-DE-1, -5 bis -7, -15, BT-34, BT-49)."""
        fehlt = []
        if not self.kaeuferreferenz:
            fehlt.append("Käuferreferenz oder Leitweg-ID")
        elif not (ist_leitweg_id(self.kaeuferreferenz) or self.kontakt.email):
            fehlt.append("E-Mail-Adresse des Empfängers")
        if not (firma.telefon and firma.email and firma.iban):
            fehlt.append("Ihre Telefonnummer, E-Mail-Adresse und IBAN")
        return fehlt

    def kopieren(self, **abweichend):
        """Neuer Entwurf mit denselben Angaben und Positionen, datiert auf heute."""
        kopie = Rechnung.objects.create(
            **{**{f: getattr(self, f) for f in self.KOPIERT}, **abweichend}
        )
        Position.objects.bulk_create(
            Position(
                rechnung=kopie,
                nr=p.nr,
                bezeichnung=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge=p.menge,
                einheit=p.einheit,
                preis=p.preis,
            )
            for p in self.positionen.all()
        )
        return kopie

    @staticmethod
    def naechste_nummer(datum):
        """Jahr zweistellig + vierstelliger Zähler (260008), lückenlos nach den Altbelegen."""
        praefix = f"{datum.year % 100:02d}"
        vorhanden = [
            *Rechnung.objects.filter(nummer__startswith=praefix).values_list(
                "nummer", flat=True
            ),
            *Altbeleg.objects.filter(
                art=Altbeleg.Art.RECHNUNG, nummer__startswith=praefix
            ).values_list("nummer", flat=True),
        ]
        zaehler = max(
            (int(n[2:]) for n in vorhanden if re.fullmatch(r"\d{6}", n)), default=0
        )
        return f"{praefix}{zaehler + 1:04d}"


class Position(models.Model):
    rechnung = models.ForeignKey(
        Rechnung, on_delete=models.CASCADE, related_name="positionen"
    )
    nr = models.PositiveSmallIntegerField()
    bezeichnung = models.CharField(max_length=200, blank=True)
    beschreibung = models.TextField(blank=True)
    menge = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    einheit = models.CharField(max_length=20, blank=True)
    preis = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["nr"]

    def __str__(self):
        return f"{self.nr}. {self.bezeichnung}"

    def save(self, *args, **kwargs):
        if self.rechnung._war_festgeschrieben():
            raise Festgeschrieben
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.rechnung._war_festgeschrieben():
            raise Festgeschrieben
        return super().delete(*args, **kwargs)

    @property
    def gesamt(self):
        return runden(self.menge * self.preis)
