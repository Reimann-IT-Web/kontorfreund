import re
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from angebote.models import Angebot
from contacts.models import Anschrift, Kontakt
from invoicing.models import (
    HINWEIS_FEHLT,
    Rechnung,
    hinweis_fehlt,
    positionsfelder,
    runden,
    steuersatzfeld,
    summen,
)


class Fertiggestellt(ValidationError):
    """Eine fertiggestellte Auftragsbestätigung bleibt, wie sie an den Kunden ging.

    Eine geänderte Fassung entsteht als Kopie mit neuer Nummer.
    """

    def __init__(self):
        super().__init__(
            "Die Auftragsbestätigung ist fertiggestellt und kann nicht mehr geändert werden."
        )


class Auftragsbestaetigung(models.Model):
    """Auftragsbestätigung (Spezifikation B-2): Entwurf → fertiggestellt → berechnet.

    Entsteht leer, aus einem Angebot (`beleg.aus_angebot`) oder als Kopie; daraus
    per Klick ein Rechnungsentwurf mit denselben Positionen (`beleg.rechnung_erstellen`).
    """

    class Status(models.TextChoices):
        ENTWURF = "entwurf", "Entwurf"
        FERTIG = "fertig", "Fertiggestellt"

    # Nach dem Fertigstellen dürfen sich nur noch diese Felder ändern.
    NACHTRAEGLICH = {"versendet_am", "versendet_an", "rechnung", "geaendert"}
    # Angaben, die eine Kopie vom Original übernimmt.
    KOPIERT = (
        "kontakt",
        "anschrift",
        "lieferanschrift",
        "steuerfall",
        "rabatt_prozent",
        "leistung_von",
        "leistung_bis",
        "betreff",
        "kopftext",
        "fusstext",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ENTWURF
    )
    nummer = models.CharField("Auftragsnummer", max_length=20, blank=True)
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Empfänger",
        on_delete=models.PROTECT,
        related_name="auftraege",
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
    datum = models.DateField("Datum", default=date.today)
    steuerfall = models.CharField(
        max_length=20,
        choices=Rechnung.Steuerfall.choices,
        default=Rechnung.Steuerfall.KLEINUNTERNEHMER,
    )
    rabatt_prozent = models.DecimalField(
        "Rabatt in Prozent", max_digits=5, decimal_places=2, default=0
    )
    leistung_von = models.DateField("Ausführung von", null=True, blank=True)
    leistung_bis = models.DateField("Ausführung bis", null=True, blank=True)
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    kopftext = models.TextField("Text vor den Positionen", blank=True)
    fusstext = models.TextField("Text nach den Positionen", blank=True)
    angebot = models.OneToOneField(
        Angebot,
        verbose_name="Angebot",
        on_delete=models.PROTECT,
        related_name="auftrag",
        null=True,
        blank=True,
        editable=False,
    )

    # Beim Fertigstellen eingefroren: genau die Angaben, aus denen das PDF entstand.
    beleg = models.JSONField(default=dict, editable=False)
    netto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ust = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    brutto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    datei = models.CharField(max_length=300, blank=True, editable=False)
    sha256 = models.CharField(max_length=64, blank=True, editable=False)
    fertiggestellt_am = models.DateTimeField(null=True, blank=True, editable=False)

    rechnung = models.OneToOneField(
        Rechnung,
        verbose_name="Rechnung zum Auftrag",
        on_delete=models.SET_NULL,
        related_name="auftrag",
        null=True,
        blank=True,
        editable=False,
    )
    versendet_am = models.DateTimeField(null=True, blank=True)
    versendet_an = models.CharField(max_length=300, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Auftragsbestätigung"
        verbose_name_plural = "Auftragsbestätigungen"
        ordering = ["-datum", "-nummer", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["nummer"],
                condition=~Q(nummer=""),
                name="auftragsnummer_eindeutig",
            )
        ]

    bezeichnung = "Auftragsbestätigung"

    def __str__(self):
        return (
            f"Auftragsbestätigung {self.nummer}"
            if self.nummer
            else "Entwurf einer Auftragsbestätigung"
        )

    def save(self, *args, **kwargs):
        if self.pk and self._war_fertig():
            felder = set(kwargs.get("update_fields") or ())
            if not felder or not felder <= self.NACHTRAEGLICH:
                raise Fertiggestellt
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._war_fertig():
            raise Fertiggestellt
        return super().delete(*args, **kwargs)

    def _war_fertig(self):
        return Auftragsbestaetigung.objects.filter(
            pk=self.pk, status=self.Status.FERTIG
        ).exists()

    @property
    def ist_entwurf(self):
        return self.status == self.Status.ENTWURF

    @property
    def stand(self):
        """Stand für Liste und Anzeige: entwurf, berechnet, versendet oder offen."""
        if self.ist_entwurf:
            return "entwurf"
        if self.rechnung_id:
            return "berechnet"
        return "versendet" if self.versendet_am else "offen"

    @property
    def anhaenge(self):
        """Dateien für den Versand: (Dateiname, Pfad im Datenordner, MIME-Typ)."""
        return [
            (f"Auftragsbestaetigung-{self.nummer}.pdf", self.datei, "application/pdf")
        ]

    def summen(self):
        return summen(self.positionen.all(), self.steuerfall, self.rabatt_prozent)

    def fehlende_angaben(self, firma):
        """Was der Auftragsbestätigung für ein ordentliches PDF noch fehlt."""
        fehlt = []
        if not (
            self.kontakt and (self.anschrift or self.kontakt).anschrift_vollstaendig
        ):
            fehlt.append("Empfänger mit Anschrift")
        if not firma.vollstaendig:
            fehlt.append("Ihre Firmendaten")
        positionen = list(self.positionen.all())
        if not positionen or any(not p.bezeichnung or p.menge <= 0 for p in positionen):
            fehlt.append("Menge und Art der Leistung")
        if self.summen()[2] <= 0:
            fehlt.append("Auftragssumme")
        if hinweis_fehlt(self.steuerfall, firma):
            fehlt.append(HINWEIS_FEHLT)
        # Die Ausführung ist freiwillig, aber wenn, dann ein gültiger Zeitraum.
        if self.leistung_bis and (
            not self.leistung_von or self.leistung_bis < self.leistung_von
        ):
            fehlt.append("Ausführungszeitraum")
        return fehlt

    def kopieren(self):
        """Neuer Entwurf mit denselben Angaben und Positionen, datiert auf heute."""
        kopie = Auftragsbestaetigung.objects.create(
            **{f: getattr(self, f) for f in self.KOPIERT}
        )
        Position.objects.bulk_create(
            Position(auftrag=kopie, **positionsfelder(p)) for p in self.positionen.all()
        )
        return kopie

    @staticmethod
    def naechste_nummer(datum):
        """Jahr zweistellig + vierstelliger Zähler (260001) wie Rechnung und Angebot.

        Eigener Nummernkreis (Spezifikation B-3); im Altprogramm gab es keine.
        """
        praefix = f"{datum.year % 100:02d}"
        vorhanden = Auftragsbestaetigung.objects.filter(
            nummer__startswith=praefix
        ).values_list("nummer", flat=True)
        zaehler = max(
            (int(n[2:]) for n in vorhanden if re.fullmatch(r"\d{6}", n)), default=0
        )
        return f"{praefix}{zaehler + 1:04d}"


class Position(models.Model):
    auftrag = models.ForeignKey(
        Auftragsbestaetigung, on_delete=models.CASCADE, related_name="positionen"
    )
    nr = models.PositiveSmallIntegerField()
    bezeichnung = models.CharField(max_length=200, blank=True)
    beschreibung = models.TextField(blank=True)
    menge = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    einheit = models.CharField(max_length=20, blank=True)
    preis = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    steuersatz = steuersatzfeld()

    class Meta:
        ordering = ["nr"]

    def __str__(self):
        return f"{self.nr}. {self.bezeichnung}"

    def save(self, *args, **kwargs):
        if self.auftrag._war_fertig():
            raise Fertiggestellt
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.auftrag._war_fertig():
            raise Fertiggestellt
        return super().delete(*args, **kwargs)

    @property
    def gesamt(self):
        return runden(self.menge * self.preis)
