from django.db import models

from contacts.models import Kontakt


class Altbeleg(models.Model):
    """Beleg aus dem Altprogramm. Das Original-PDF bleibt unverändert erhalten (GoBD)."""

    class Art(models.TextChoices):
        RECHNUNG = "rechnung", "Rechnung"
        STORNO = "storno", "Stornorechnung"
        GUTSCHRIFT = "gutschrift", "Gutschrift"
        ANGEBOT = "angebot", "Angebot"

    UMSATZWIRKSAM = (Art.RECHNUNG, Art.STORNO, Art.GUTSCHRIFT)

    art = models.CharField("Art", max_length=12, choices=Art.choices)
    nummer = models.CharField("Nummer", max_length=30)
    datum = models.DateField("Datum")
    absender = models.CharField("Absender", max_length=200, blank=True)
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="altbelege",
    )
    empfaenger = models.TextField("Empfänger wie gedruckt", blank=True)
    # Brutto wie auf dem Beleg; Stornos und Gutschriften negativ.
    betrag = models.DecimalField("Betrag", max_digits=12, decimal_places=2, null=True)
    bezug = models.CharField("zu Rechnung", max_length=30, blank=True)
    datei = models.CharField("Datei", max_length=300)
    sha256 = models.CharField("SHA-256", max_length=64, unique=True)
    originalname = models.CharField("Originaldatei", max_length=300)
    quelle = models.CharField("Quelle", max_length=50, default="SuccessControl")
    importiert = models.DateTimeField("übernommen am", auto_now_add=True)

    class Meta:
        ordering = ["-datum", "-nummer"]
        verbose_name = "Altbeleg"
        verbose_name_plural = "Altbelege"
        constraints = [
            models.UniqueConstraint(
                fields=["absender", "art", "nummer"], name="altbeleg_eindeutig"
            )
        ]

    def __str__(self):
        return f"{self.get_art_display()} {self.nummer}"
