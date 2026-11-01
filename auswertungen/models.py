from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from invoicing.models import Rechnung

# Übliche Erlöskonten je Steuerfall; die Vorbelegung bestätigt der Steuerberater.
ERLOESKONTEN = {
    "03": {
        Rechnung.Steuerfall.KLEINUNTERNEHMER: 8195,
        Rechnung.Steuerfall.REGEL: 8400,
        Rechnung.Steuerfall.UMKEHR: 8337,
    },
    "04": {
        Rechnung.Steuerfall.KLEINUNTERNEHMER: 4185,
        Rechnung.Steuerfall.REGEL: 4400,
        Rechnung.Steuerfall.UMKEHR: 4337,
    },
}
# Personenkonten bei vierstelligen Sachkonten.
DEBITOREN = (10000, 69999)


def _erloeskonto(name, steuerfall):
    standard = " oder ".join(
        f"SKR {skr}: {konten[steuerfall]}" for skr, konten in ERLOESKONTEN.items()
    )
    return models.PositiveIntegerField(
        name,
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
        help_text=f"Leer lassen für das übliche Konto ({standard}).",
    )


class Datev(models.Model):
    """Einstellungen für den DATEV-Export (Spezifikation M-4); es gibt genau einen Datensatz."""

    class Kontenrahmen(models.TextChoices):
        SKR03 = "03", "SKR 03"
        SKR04 = "04", "SKR 04"

    class Debitoren(models.TextChoices):
        JE_KUNDE = "kunde", "Ein Konto je Kunde"
        SAMMELKONTO = "sammel", "Ein Sammelkonto für alle Kunden"

    beraternummer = models.PositiveIntegerField(
        "Beraternummer",
        null=True,
        blank=True,
        validators=[MinValueValidator(1001), MaxValueValidator(9999999)],
    )
    mandantennummer = models.PositiveIntegerField(
        "Mandantennummer",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99999)],
    )
    kontenrahmen = models.CharField(
        "Kontenrahmen",
        max_length=2,
        choices=Kontenrahmen.choices,
        default=Kontenrahmen.SKR03,
    )
    debitoren = models.CharField(
        "Debitorenkonten",
        max_length=10,
        choices=Debitoren.choices,
        default=Debitoren.JE_KUNDE,
        help_text="Je Kunde: 10000 plus Kundennummer, K-0007 bucht also auf 10007.",
    )
    sammelkonto = models.PositiveIntegerField(
        "Sammelkonto",
        default=10000,
        validators=[MinValueValidator(DEBITOREN[0]), MaxValueValidator(DEBITOREN[1])],
        help_text="Nur bei einem Sammelkonto; ein Debitor zwischen 10000 und 69999.",
    )
    erloes_kleinunternehmer = _erloeskonto(
        "Erlöskonto § 19 UStG", Rechnung.Steuerfall.KLEINUNTERNEHMER
    )
    erloes_regel = _erloeskonto("Erlöskonto 19 % USt", Rechnung.Steuerfall.REGEL)
    erloes_13b = _erloeskonto("Erlöskonto § 13b UStG", Rechnung.Steuerfall.UMKEHR)

    class Meta:
        verbose_name = "DATEV-Einstellungen"
        verbose_name_plural = "DATEV-Einstellungen"

    def __str__(self):
        return "DATEV-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def bereit(self):
        """Ohne Berater- und Mandantennummer liest DATEV die Datei nicht ein."""
        return bool(self.beraternummer and self.mandantennummer)

    def erloeskonto(self, steuerfall):
        eigenes = {
            Rechnung.Steuerfall.KLEINUNTERNEHMER: self.erloes_kleinunternehmer,
            Rechnung.Steuerfall.REGEL: self.erloes_regel,
            Rechnung.Steuerfall.UMKEHR: self.erloes_13b,
        }[steuerfall]
        return eigenes or ERLOESKONTEN[self.kontenrahmen][steuerfall]

    def debitor(self, kontakt):
        if self.debitoren == self.Debitoren.SAMMELKONTO:
            return self.sammelkonto
        return DEBITOREN[0] + kontakt.nummer
