import re
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from contacts.models import Kontakt

# Im Browser ansehen lassen sich nur diese Arten; alles andere gibt es nur als Download.
VORSCHAU = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
# Woran sich diese Arten erkennen lassen; passt der Anfang nicht, gibt es die Datei nur
# als Download (ASVS 5.2.2).
KENNUNG = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}
# So lange lässt sich eine gelöschte Datei noch zurückholen.
AUFBEWAHREN = timedelta(days=30)


class Vorgang(models.Model):
    """Eintrag in der Kontakthistorie (Spezifikation K-2), von Hand erfasst.

    Belege, Zahlungen, Mahnungen und erledigte Wiedervorlagen stehen ebenfalls in
    der Zeitleiste, werden aber aus ihren eigenen Daten gelesen (`zeitleiste.py`).
    """

    class Art(models.TextChoices):
        NOTIZ = "notiz", "Notiz"
        ANRUF = "anruf", "Anruf"
        EMAIL = "email", "E-Mail"
        TERMIN = "termin", "Termin"

    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        on_delete=models.CASCADE,
        related_name="vorgaenge",
    )
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.NOTIZ)
    zeitpunkt = models.DateTimeField("Wann", default=timezone.now)
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    text = models.TextField("Text", blank=True)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Erfasst von",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vorgang"
        verbose_name_plural = "Vorgänge"
        ordering = ["-zeitpunkt", "-pk"]

    def __str__(self):
        return f"{self.get_art_display()}: {self.betreff or self.text[:60]}"


def _bereinigt(name):
    """Nur der Dateiname, ohne Pfad und Steuerzeichen, höchstens 200 Zeichen."""
    name = re.split(r"[\\/]", name)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(" .")
    stamm, punkt, endung = name.rpartition(".")
    if punkt and len(endung) <= 10:
        return f"{stamm[: 199 - len(endung)]}.{endung}"
    return name[:200] or "Datei"


def _sicher(text, ersatz):
    """Nur Zeichen, die jedes Dateisystem verträgt."""
    try:
        return get_valid_filename(text)
    except SuspiciousFileOperation:
        return ersatz


class Datei(models.Model):
    """Datei an einer Adresse oder einem Vorgang (Spezifikation K-3).

    Liegt unter <DATA_DIR>/archiv/dateien/<Kundennummer>/ und ist damit in jeder
    Datensicherung. Ändert sich die Kundennummer, bleiben ältere Dateien im Ordner
    der alten; gefunden werden sie immer über `datei`. Gelöscht wird erst nur markiert; nach AUFBEWAHREN räumt
    `aufraeumen` Datei und Eintrag weg.
    """

    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        on_delete=models.CASCADE,
        related_name="dateien",
    )
    # Wird der Vorgang gelöscht, bleibt die Datei bei der Adresse.
    vorgang = models.ForeignKey(
        Vorgang,
        verbose_name="Vorgang",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dateien",
    )
    name = models.CharField("Dateiname", max_length=200)
    datei = models.CharField(max_length=300, editable=False)
    groesse = models.PositiveBigIntegerField("Größe", editable=False)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Abgelegt von",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    erstellt = models.DateTimeField(auto_now_add=True)
    geloescht_am = models.DateTimeField("Gelöscht am", null=True, blank=True)

    class Meta:
        verbose_name = "Datei"
        verbose_name_plural = "Dateien"
        ordering = ["-erstellt", "-pk"]

    def __str__(self):
        return self.name

    @classmethod
    def ablegen(cls, kontakt, hochgeladen, benutzer=None, vorgang=None):
        """Hochgeladene Datei ablegen; vorhandene Dateien werden nie überschrieben."""
        name = _bereinigt(hochgeladen.name)
        stamm, endung = Path(name).stem, Path(name).suffix
        auf_platte = _sicher(stamm[:80], "Datei") + _sicher(endung[:11], "")
        relativ = (
            Path("archiv")
            / "dateien"
            / kontakt.kundennummer
            / f"{secrets.token_hex(6)}-{auf_platte}"
        )
        with transaction.atomic():
            datei = cls.objects.create(
                kontakt=kontakt,
                vorgang=vorgang,
                name=name,
                datei=relativ.as_posix(),
                groesse=hochgeladen.size,
                benutzer=benutzer,
            )
            ziel = datei.pfad
            ziel.parent.mkdir(parents=True, exist_ok=True)
            with ziel.open("xb") as aus:
                for stueck in hochgeladen.chunks():
                    aus.write(stueck)
        return datei

    @classmethod
    def aufraeumen(cls):
        """Länger als AUFBEWAHREN gelöschte Dateien endgültig entfernen."""
        for datei in cls.objects.filter(geloescht_am__lt=timezone.now() - AUFBEWAHREN):
            datei.pfad.unlink(missing_ok=True)
            datei.delete()

    @property
    def pfad(self):
        return Path(settings.DATA_DIR) / self.datei

    @property
    def endung(self):
        return Path(self.name).suffix.lower()

    @property
    def vorschau(self):
        return self.endung in VORSCHAU

    def inhalt_passt(self):
        """Beginnt die Datei so, wie es ihre Endung verspricht?"""
        with self.pfad.open("rb") as f:
            kopf = f.read(12)
        if self.endung == ".webp" and kopf[8:12] != b"WEBP":
            return False
        return kopf.startswith(KENNUNG.get(self.endung, ()))

    @property
    def art(self):
        """Kurz für die Liste, z. B. „PDF“, „Bild“ oder „DOCX“."""
        if self.endung == ".pdf":
            return "PDF"
        if self.vorschau:
            return "Bild"
        return self.endung.lstrip(".").upper() or "Datei"
