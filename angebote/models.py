import re
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from archive.models import Altbeleg
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
    """Ein fertiggestelltes Angebot bleibt, wie es an den Kunden ging.

    Eine geänderte Fassung entsteht als Kopie mit neuer Nummer.
    """

    def __init__(self):
        super().__init__(
            "Das Angebot ist fertiggestellt und kann nicht mehr geändert werden."
        )


class Angebot(models.Model):
    """Angebot (Spezifikation B-2): Entwurf → fertiggestellt → angenommen oder abgelehnt.

    Aus einem angenommenen Angebot entsteht per Klick ein Rechnungsentwurf
    mit denselben Positionen (`beleg.rechnung_erstellen`).
    """

    class Status(models.TextChoices):
        ENTWURF = "entwurf", "Entwurf"
        FERTIG = "fertig", "Fertiggestellt"

    class Antwort(models.TextChoices):
        ANGENOMMEN = "angenommen", "Angenommen"
        ABGELEHNT = "abgelehnt", "Abgelehnt"

    # Nach dem Fertigstellen dürfen sich nur noch diese Felder ändern.
    NACHTRAEGLICH = {
        "versendet_am",
        "versendet_an",
        "antwort",
        "antwort_am",
        "rechnung",
        "geaendert",
    }
    # Angaben, die eine Kopie vom Original übernimmt.
    KOPIERT = (
        "kontakt",
        "anschrift",
        "lieferanschrift",
        "bindefrist",
        "steuerfall",
        "rabatt_prozent",
        "betreff",
        "kopftext",
        "fusstext",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ENTWURF
    )
    nummer = models.CharField("Angebotsnummer", max_length=20, blank=True)
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Empfänger",
        on_delete=models.PROTECT,
        related_name="angebote",
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
    datum = models.DateField("Angebotsdatum", default=date.today)
    bindefrist = models.PositiveSmallIntegerField("Gültig für Tage", default=30)
    steuerfall = models.CharField(
        max_length=20,
        choices=Rechnung.Steuerfall.choices,
        default=Rechnung.Steuerfall.KLEINUNTERNEHMER,
    )
    rabatt_prozent = models.DecimalField(
        "Rabatt in Prozent", max_digits=5, decimal_places=2, default=0
    )
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    kopftext = models.TextField("Text vor den Positionen", blank=True)
    fusstext = models.TextField("Text nach den Positionen", blank=True)

    # Beim Fertigstellen eingefroren: genau die Angaben, aus denen das PDF entstand.
    beleg = models.JSONField(default=dict, editable=False)
    netto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ust = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    brutto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    datei = models.CharField(max_length=300, blank=True, editable=False)
    sha256 = models.CharField(max_length=64, blank=True, editable=False)
    fertiggestellt_am = models.DateTimeField(null=True, blank=True, editable=False)

    antwort = models.CharField(
        "Antwort des Kunden", max_length=12, choices=Antwort.choices, blank=True
    )
    antwort_am = models.DateField("Antwort am", null=True, blank=True)
    rechnung = models.OneToOneField(
        Rechnung,
        verbose_name="Rechnung zum Angebot",
        on_delete=models.SET_NULL,
        related_name="angebot",
        null=True,
        blank=True,
        editable=False,
    )
    versendet_am = models.DateTimeField(null=True, blank=True)
    versendet_an = models.CharField(max_length=300, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Angebot"
        verbose_name_plural = "Angebote"
        ordering = ["-datum", "-nummer", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["nummer"],
                condition=~Q(nummer=""),
                name="angebotsnummer_eindeutig",
            )
        ]

    bezeichnung = "Angebot"

    def __str__(self):
        return f"Angebot {self.nummer}" if self.nummer else "Angebotsentwurf"

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
        return Angebot.objects.filter(pk=self.pk, status=self.Status.FERTIG).exists()

    @property
    def ist_entwurf(self):
        return self.status == self.Status.ENTWURF

    @property
    def gueltig_bis(self):
        return self.datum + timedelta(days=self.bindefrist)

    @property
    def abgelaufen(self):
        """Fertiggestellt, ohne Antwort und die Bindefrist ist vorbei."""
        return (
            not self.ist_entwurf
            and not self.antwort
            and self.gueltig_bis < date.today()
        )

    @property
    def stand(self):
        """Stand für Liste und Anzeige: entwurf, angenommen, abgelehnt, abgelaufen,
        versendet oder offen."""
        if self.ist_entwurf:
            return "entwurf"
        if self.antwort:
            return self.antwort
        if self.abgelaufen:
            return "abgelaufen"
        return "versendet" if self.versendet_am else "offen"

    @property
    def anhaenge(self):
        """Dateien für den Versand: (Dateiname, Pfad im Datenordner, MIME-Typ)."""
        return [(f"Angebot-{self.nummer}.pdf", self.datei, "application/pdf")]

    def summen(self):
        return summen(self.positionen.all(), self.steuerfall, self.rabatt_prozent)

    def fehlende_angaben(self, firma):
        """Was dem Angebot für ein ordentliches PDF noch fehlt."""
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
            fehlt.append("Angebotsbetrag")
        if hinweis_fehlt(self.steuerfall, firma):
            fehlt.append(HINWEIS_FEHLT)
        return fehlt

    def kopieren(self):
        """Neuer Entwurf mit denselben Angaben und Positionen, datiert auf heute."""
        kopie = Angebot.objects.create(**{f: getattr(self, f) for f in self.KOPIERT})
        Position.objects.bulk_create(
            Position(angebot=kopie, **positionsfelder(p)) for p in self.positionen.all()
        )
        return kopie

    @staticmethod
    def naechste_nummer(datum):
        """Jahr zweistellig + vierstelliger Zähler (260001), wie die Angebote im Altprogramm.

        Eigener Nummernkreis neben den Rechnungen (Spezifikation B-3).
        """
        praefix = f"{datum.year % 100:02d}"
        vorhanden = [
            *Angebot.objects.filter(nummer__startswith=praefix).values_list(
                "nummer", flat=True
            ),
            *Altbeleg.objects.filter(
                art=Altbeleg.Art.ANGEBOT, nummer__startswith=praefix
            ).values_list("nummer", flat=True),
        ]
        zaehler = max(
            (int(n[2:]) for n in vorhanden if re.fullmatch(r"\d{6}", n)), default=0
        )
        return f"{praefix}{zaehler + 1:04d}"


class Position(models.Model):
    angebot = models.ForeignKey(
        Angebot, on_delete=models.CASCADE, related_name="positionen"
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
        if self.angebot._war_fertig():
            raise Fertiggestellt
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.angebot._war_fertig():
            raise Fertiggestellt
        return super().delete(*args, **kwargs)

    @property
    def gesamt(self):
        return runden(self.menge * self.preis)
