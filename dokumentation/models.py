from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Angaben(models.Model):
    """Was nur der Inhaber über seinen Betrieb weiß; es gibt genau einen Datensatz.

    Alles andere in den Dokumenten liest `inhalt.py` aus dem Programm und den Einstellungen.
    """

    taetigkeit = models.TextField(
        "Was bietet Ihr Unternehmen an, und seit wann?",
        blank=True,
        help_text="Zum Beispiel: IT-Service, Webdesign und Wartungsverträge für Privat- und Geschäftskunden, seit 2013.",
    )
    gewinnermittlung = models.TextField(
        "Wie ermitteln Sie den Gewinn, und wer macht die Steuererklärungen?",
        blank=True,
        help_text="Zum Beispiel: Einnahmenüberschussrechnung, die ich selbst über ELSTER abgebe.",
    )
    zahlungsverkehr = models.TextField(
        "Über welche Konten laufen die Zahlungen, und wie bewahren Sie die Kontoauszüge auf?",
        blank=True,
        help_text="Zum Beispiel: Geschäftskonto bei der Musterbank, Kontoauszüge als PDF aus dem Online-Banking, einmal im Monat im Ordner „Kontoauszüge“ gespeichert. Bargeld nehme ich nicht an.",
    )
    belege = models.TextField(
        "Wie bewahren Sie Belege auf, die nicht in Kontorfreund liegen?",
        blank=True,
        help_text="Etwa Rechnungen von Lieferanten auf Papier oder als PDF, Quittungen und Verträge. Zum Beispiel: Papier im Ordner je Jahr im Büro, PDF-Rechnungen im Ordner „Belege“ auf dem Rechner. Vernichten Sie Papier nach dem Scannen nur, wenn das Scannen eigens beschrieben ist.",
    )
    email = models.TextField(
        "Wie bewahren Sie E-Mails mit Rechnungen, Aufträgen und anderer Geschäftspost auf?",
        blank=True,
        help_text="Zum Beispiel: im Postfach bei meinem Anbieter, Geschäftspost lösche ich nicht.",
    )
    rechner = models.TextField(
        "Auf welchem Rechner arbeiten Sie mit Kontorfreund, und wo steht er?",
        blank=True,
        help_text="Zum Beispiel: PC im Büro in meiner Wohnung, nur ich habe Zugang.",
    )
    altprogramm = models.TextField(
        "Was ist mit Ihrem bisherigen Programm und dessen Daten geschehen?",
        blank=True,
        help_text="Die Belege daraus liegen in Kontorfreund. Zum Beispiel: Das Programm und seine Datenbank bleiben bis Ende 2034 auf dem alten Rechner erhalten.",
    )

    datenschutzbeauftragter = models.TextField(
        "Datenschutzbeauftragter",
        blank=True,
        help_text="Nur wenn Sie einen benannt haben: Name und Kontakt. Vorgeschrieben ist das meist erst, wenn mindestens 20 Personen ständig mit personenbezogenen Daten arbeiten.",
    )
    weitere_verarbeitungen = models.TextField(
        "Welche personenbezogenen Daten verarbeiten Sie außerhalb von Kontorfreund?",
        blank=True,
        help_text="Eine Zeile je Verarbeitung. Zum Beispiel: Website mit Kontaktformular bei Anbieter X, E-Mail-Postfach bei Anbieter Y, Fernwartung bei Kunden mit Programm Z.",
    )
    tom_verschluesselt = models.BooleanField(
        "Die Festplatte des Rechners ist verschlüsselt, zum Beispiel mit BitLocker, FileVault oder LUKS.",
        default=False,
    )
    tom_bildschirmsperre = models.BooleanField(
        "Der Rechner sperrt sich nach kurzer Zeit und verlangt dann ein Kennwort.",
        default=False,
    )
    tom_aktuell = models.BooleanField(
        "Betriebssystem, Browser und Virenschutz werden automatisch aktualisiert.",
        default=False,
    )
    tom_zutritt = models.BooleanField(
        "Fremde kommen nicht unbeaufsichtigt an den Rechner und an die Akten.",
        default=False,
    )
    tom_akten = models.BooleanField(
        "Akten mit Kundendaten liegen verschlossen und werden datenschutzgerecht vernichtet.",
        default=False,
    )
    tom_weitere = models.TextField(
        "Weitere Maßnahmen",
        blank=True,
        help_text="Eine Zeile je Maßnahme. Zum Beispiel: Kennwort-Manager für alle Zugänge.",
    )

    class Meta:
        verbose_name = "Angaben zum Betrieb"
        verbose_name_plural = "Angaben zum Betrieb"

    def __str__(self):
        return "Angaben zum Betrieb"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Abgelegt(ValidationError):
    """Abgelegte Fassungen bleiben, wie sie sind; eine Änderung ergibt eine neue Fassung."""

    def __init__(self):
        super().__init__(
            "Eine abgelegte Fassung bleibt unverändert. Ändert sich etwas, entsteht beim "
            "nächsten Herunterladen eine neue Fassung."
        )


class Fassung(models.Model):
    """Abgelegte Fassung eines Dokuments; frühere Fassungen bleiben nachvollziehbar (GoBD Rz. 154)."""

    class Art(models.TextChoices):
        VERFAHREN = "verfahren", "Verfahrensdokumentation"
        DATENSCHUTZ = "datenschutz", "Verzeichnis von Verarbeitungstätigkeiten"

    art = models.CharField("Dokument", max_length=12, choices=Art.choices)
    nummer = models.PositiveIntegerField("Fassung")
    erstellt = models.DateTimeField("Erstellt am", default=timezone.now)
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Erstellt von",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    version = models.CharField("Programmversion", max_length=20)
    # Abschnitte ohne Nummern, Stand und Änderungsverlauf: daran erkennt `inhalt.py`,
    # ob sich etwas geändert hat und was.
    inhalt = models.JSONField(default=list, editable=False)
    aenderungen = models.JSONField("Geändert", default=list, editable=False)
    datei = models.CharField("Datei", max_length=300)
    sha256 = models.CharField("SHA-256", max_length=64)

    class Meta:
        ordering = ["art", "-nummer"]
        verbose_name = "Fassung der Dokumentation"
        verbose_name_plural = "Fassungen der Dokumentation"
        constraints = [
            models.UniqueConstraint(fields=["art", "nummer"], name="fassung_eindeutig")
        ]

    def __str__(self):
        return f"{self.get_art_display()}, Fassung {self.nummer}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise Abgelegt
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise Abgelegt

    @property
    def dateiname(self):
        return f"{self.get_art_display()} Fassung {self.nummer}.pdf"
