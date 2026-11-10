from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Max

from invoicing.beleg import EINHEIT_CODE


class Artikel(models.Model):
    """Ware oder Leistung, die sich als Position in eine Rechnung einfügen lässt.

    Die Rechnung übernimmt die Angaben als Kopie; spätere Preisänderungen
    berühren bestehende Rechnungen nicht.
    """

    nummer = models.PositiveIntegerField("Nummer", unique=True, editable=False)
    bezeichnung = models.CharField("Bezeichnung", max_length=200)
    beschreibung = models.TextField("Beschreibung", blank=True)
    # Ohne Einheit zeigt der Beleg nur die Menge.
    einheit = models.CharField(
        "Einheit",
        max_length=20,
        choices=[(e, e) for e in EINHEIT_CODE] + [("", "ohne Einheit")],
        default="Stück",
        blank=True,
    )
    preis = models.DecimalField(
        "Einzelpreis",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    aktiv = models.BooleanField(default=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bezeichnung"]
        verbose_name = "Artikel"
        verbose_name_plural = "Artikel"

    def __str__(self):
        return self.bezeichnung

    def save(self, *args, **kwargs):
        if self.nummer is None:
            hoechste = Artikel.objects.aggregate(m=Max("nummer"))["m"] or 0
            self.nummer = hoechste + 1
        super().save(*args, **kwargs)

    @property
    def artikelnummer(self):
        return f"A-{self.nummer:04d}"
