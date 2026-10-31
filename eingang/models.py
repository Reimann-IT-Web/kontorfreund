import hashlib
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils.text import get_valid_filename

from contacts.models import Kontakt

from . import lesen


class Aufbewahrt(ValidationError):
    """Empfangene E-Rechnungen bleiben, wie sie sind (GoBD); nur die Adresse ist änderbar."""

    def __init__(self):
        super().__init__(
            "Eine empfangene E-Rechnung wird unverändert aufbewahrt. "
            "Ändern lässt sich nur die Zuordnung zur Adresse."
        )


class Doppelt(lesen.Unlesbar):
    """Dieselbe Datei ist schon abgelegt."""

    def __init__(self, vorhanden):
        super().__init__(
            f"Diese Datei ist schon abgelegt: {vorhanden} von {vorhanden.lieferant}."
        )
        self.vorhanden = vorhanden


class Eingangsrechnung(models.Model):
    """Empfangene E-Rechnung. Die Originaldatei bleibt unverändert erhalten (GoBD).

    Die Felder hier sind Kopfdaten für Liste und Suche; angezeigt wird immer, was
    in der Originaldatei steht (`lesen.auswerten`).
    """

    class Format(models.TextChoices):
        XML = "xml", "XML-Datei"
        PDF = "pdf", "PDF mit eingebetteter XML"

    format = models.CharField("Format", max_length=3, choices=Format.choices)
    syntax = models.CharField("Syntax", max_length=3)
    art = models.CharField("Rechnungsart", max_length=3)
    nummer = models.CharField("Rechnungsnummer", max_length=100)
    datum = models.DateField("Rechnungsdatum")
    faellig = models.DateField("fällig am", null=True, blank=True)
    lieferant = models.CharField("Lieferant laut Rechnung", max_length=300)
    ust_id = models.CharField("USt-IdNr. des Lieferanten", max_length=30, blank=True)
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="eingangsrechnungen",
    )
    waehrung = models.CharField("Währung", max_length=3)
    brutto = models.DecimalField("Gesamtbetrag", max_digits=14, decimal_places=2)
    zahlbetrag = models.DecimalField("Zahlbetrag", max_digits=14, decimal_places=2)
    datei = models.CharField("Datei", max_length=300)
    sha256 = models.CharField("SHA-256", max_length=64, unique=True)
    originalname = models.CharField("Originaldatei", max_length=300)
    hochgeladen = models.DateTimeField("hochgeladen am", auto_now_add=True)

    class Meta:
        ordering = ["-datum", "-pk"]
        verbose_name = "Eingangsrechnung"
        verbose_name_plural = "Eingangsrechnungen"

    def __str__(self):
        return f"{lesen.ARTEN.get(self.art, 'Rechnung')} {self.nummer}"

    def save(self, *args, **kwargs):
        if self.pk and set(kwargs.get("update_fields") or ["alle"]) - {"kontakt"}:
            raise Aufbewahrt
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise Aufbewahrt

    @property
    def pfad(self):
        return Path(settings.DATA_DIR) / self.datei

    def lesen(self):
        """(Inhalt der Originaldatei, Angaben daraus); die Prüfsumme ist vorher geprüft."""
        inhalt = self.pfad.read_bytes()
        if hashlib.sha256(inhalt).hexdigest() != self.sha256:
            raise lesen.Unlesbar(
                "Die Datei im Archiv stimmt nicht mehr mit der Prüfsumme überein. "
                "Spielen Sie bitte eine Datensicherung zurück."
            )
        return inhalt, lesen.auswerten(lesen.einlesen(inhalt)[1])

    @classmethod
    def ablegen(cls, originalname, inhalt):
        """Datei lesen, unverändert ins Archiv legen und den Eintrag anlegen."""
        sha256 = hashlib.sha256(inhalt).hexdigest()
        if vorhanden := cls.objects.filter(sha256=sha256).first():
            raise Doppelt(vorhanden)
        art, xml = lesen.einlesen(inhalt)
        d = lesen.auswerten(xml)
        verkaeufer = d["verkaeufer"]
        relativ = (
            Path("archiv")
            / "eingang"
            / str(d["datum"].year)
            / f"{sha256[:12]}-{get_valid_filename(Path(originalname).name)}"
        )
        with transaction.atomic():
            rechnung = cls.objects.create(
                format=art,
                syntax=d["syntax"],
                art=d["art"][:3],
                nummer=d["nummer"][:100],
                datum=d["datum"],
                faellig=d["faellig"],
                lieferant=verkaeufer["name"][:300],
                ust_id=verkaeufer["ust_id"].replace(" ", "").upper()[:30],
                kontakt=lieferant_finden(verkaeufer),
                waehrung=d["waehrung"][:3],
                brutto=d["summen"]["brutto"],
                zahlbetrag=d["summen"]["zahlbetrag"],
                datei=relativ.as_posix(),
                sha256=sha256,
                originalname=originalname[:300],
            )
            ziel = Path(settings.DATA_DIR) / relativ
            ziel.parent.mkdir(parents=True, exist_ok=True)
            with ziel.open("xb") as datei:  # niemals überschreiben
                datei.write(inhalt)
        return rechnung


def lieferant_finden(verkaeufer):
    """Die eine Adresse mit derselben USt-IdNr. oder demselben Namen, sonst None."""
    adressen = Kontakt.objects.filter(archiviert=False)
    if ust_id := verkaeufer["ust_id"].replace(" ", "").upper():
        treffer = list(adressen.filter(ust_id=ust_id)[:2])
        if len(treffer) == 1:
            return treffer[0]
    namen = Q()
    for name in {verkaeufer["name"], verkaeufer["handelsname"]} - {""}:
        namen |= Q(anzeigename__iexact=name)
    treffer = list(adressen.filter(namen)[:2]) if namen else []
    return treffer[0] if len(treffer) == 1 else None
