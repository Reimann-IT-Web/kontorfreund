import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from archive.models import Altbeleg
from contacts.models import Kontakt

CENT = Decimal("0.01")
UST_SATZ = Decimal("19")


def runden(wert):
    return wert.quantize(CENT, rounding=ROUND_HALF_UP)


class Festgeschrieben(ValidationError):
    """Festgeschriebene Rechnungen sind unveränderbar (GoBD); Korrektur nur per Storno."""

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

    STEUERHINWEIS = {
        Steuerfall.KLEINUNTERNEHMER: "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
        Steuerfall.REGEL: "",
        Steuerfall.UMKEHR: "Steuerschuldnerschaft des Leistungsempfängers.",
    }

    # Nach dem Festschreiben dürfen sich nur noch diese Felder ändern.
    NACHTRAEGLICH = {"versendet_am", "versendet_an"}

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
    datum = models.DateField("Rechnungsdatum", default=date.today)
    leistung_von = models.DateField("Leistung von", null=True, blank=True)
    leistung_bis = models.DateField("Leistung bis", null=True, blank=True)
    zahlungsziel = models.PositiveSmallIntegerField("Zahlungsziel in Tagen", default=14)
    steuerfall = models.CharField(
        max_length=20, choices=Steuerfall.choices, default=Steuerfall.KLEINUNTERNEHMER
    )
    referenz = models.CharField("Käuferreferenz", max_length=100, blank=True)
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    kopftext = models.TextField("Text vor den Positionen", blank=True)
    fusstext = models.TextField("Text nach den Positionen", blank=True)
    girocode = models.BooleanField("GiroCode drucken", default=True)

    # Beim Festschreiben eingefroren: genau die Angaben, aus denen PDF und XML entstanden.
    beleg = models.JSONField(default=dict, editable=False)
    netto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ust = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    brutto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    datei = models.CharField(max_length=300, blank=True, editable=False)
    sha256 = models.CharField(max_length=64, blank=True, editable=False)
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
        return f"Rechnung {self.nummer}" if self.nummer else "Rechnungsentwurf"

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
    def faellig(self):
        return self.datum + timedelta(days=self.zahlungsziel)

    @property
    def steuerhinweis(self):
        return self.STEUERHINWEIS[self.steuerfall]

    def summen(self):
        """(netto, ust, brutto) aus den Positionen, kaufmännisch gerundet."""
        netto = sum((p.gesamt for p in self.positionen.all()), Decimal("0.00"))
        ust = (
            runden(netto * UST_SATZ / 100)
            if self.steuerfall == self.Steuerfall.REGEL
            else Decimal("0.00")
        )
        return netto, ust, netto + ust

    def fehlende_angaben(self, firma):
        """Pflichtangaben nach § 14 Abs. 4 UStG, die noch fehlen."""
        fehlt = []
        if not (self.kontakt and self.kontakt.anschrift_vollstaendig):
            fehlt.append("Empfänger mit Anschrift")
        if not firma.vollstaendig:
            fehlt.append("Ihre Firmendaten")
        positionen = list(self.positionen.all())
        if not positionen or any(not p.bezeichnung or p.menge <= 0 for p in positionen):
            fehlt.append("Menge und Art der Leistung")
        if not self.leistung_von or (
            self.leistung_bis and self.leistung_bis < self.leistung_von
        ):
            fehlt.append("Leistungszeitraum")
        if self.summen()[2] <= 0:
            fehlt.append("Rechnungsbetrag")
        return fehlt

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
