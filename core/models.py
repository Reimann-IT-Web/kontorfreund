import base64
import re

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models

# Briefkopf (B-6): Grenzen, damit der Kopf über dem Infoblock und dem Anschriftfeld endet.
LOGO_MM = (6, 20)
AKZENT = "#1d5f6e"


def iban_pruefen(wert):
    """IBAN-Prüfziffer nach ISO 13616 (Modulo 97)."""
    iban = wert.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        raise ValidationError(
            "Bitte eine vollständige IBAN eingeben, z. B. DE12 3456 7890 1234 5678 90."
        )
    umgestellt = iban[4:] + iban[:4]
    if int("".join(str(int(z, 36)) for z in umgestellt)) % 97 != 1:
        raise ValidationError(
            "Die Prüfziffer der IBAN stimmt nicht. Bitte auf Tippfehler prüfen."
        )


def daten_url(daten):
    """Bild als Daten-URL für die Ansicht in den Einstellungen."""
    daten = bytes(daten)
    if not daten:
        return ""
    typ = (
        "image/png"
        if daten.startswith(b"\x89PNG")
        else "image/jpeg"
        if daten.startswith(b"\xff\xd8")
        else "image/svg+xml"
    )
    return f"data:{typ};base64,{base64.b64encode(daten).decode()}"


class Firmendaten(models.Model):
    """Angaben zum eigenen Unternehmen; es gibt genau einen Datensatz."""

    name = models.CharField("Firmenname", max_length=200, blank=True)
    marke = models.CharField("Marke oder Zusatz", max_length=100, blank=True)
    inhaber = models.CharField("Inhaber", max_length=200, blank=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    steuernummer = models.CharField("Steuernummer", max_length=30, blank=True)
    ust_id = models.CharField("USt-IdNr.", max_length=20, blank=True)

    # Die Werte sind zugleich Steuerfälle der Belege (invoicing.models.Rechnung.Steuerfall).
    class Umsatzsteuer(models.TextChoices):
        KLEINUNTERNEHMER = "kleinunternehmer", "Kleinunternehmer nach § 19 UStG"
        REGEL = "regel", "Umsatzsteuer ausweisen (19 % oder 7 %)"
        STEUERFREI = "steuerfrei", "Steuerfreie Leistungen nach § 4 UStG"

    umsatzsteuer = models.CharField(
        "Umsatzsteuer",
        max_length=20,
        choices=Umsatzsteuer.choices,
        default=Umsatzsteuer.KLEINUNTERNEHMER,
    )
    steuerfrei_hinweis = models.CharField(
        "Hinweis auf die Steuerbefreiung", max_length=200, blank=True
    )
    email = models.EmailField("E-Mail", blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    internetadresse = models.URLField("Internetadresse", blank=True)
    iban = models.CharField(
        "IBAN", max_length=42, blank=True, validators=[iban_pruefen]
    )
    bank = models.CharField("Bank", max_length=100, blank=True)
    # Leer druckt die Rechnung Zahlungsziel und Bankverbindung im eigenen Wortlaut.
    zahlungstext = models.TextField("Zahlungshinweis auf Rechnungen", blank=True)
    # In der Datenbank statt als Datei, damit es mit jeder Sicherung erhalten bleibt.
    logo = models.BinaryField("Logo", blank=True, default=b"")

    # Briefkopf auf Seite 1 jedes Belegs; die Vorgaben ergeben den bisherigen Kopf.
    class Kopfart(models.TextChoices):
        LOGO = "logo", "Logo und Angaben"
        BILD = "bild", "Eigenes Kopfbild"

    class Lage(models.TextChoices):
        LINKS = "links", "Links"
        MITTE = "mitte", "Mitte"
        RECHTS = "rechts", "Rechts"

    class Bildbreite(models.TextChoices):
        TEXT = "text", "So breit wie der Text"
        SEITE = "seite", "Ganze Seitenbreite, bis an den Rand"

    kopf_art = models.CharField(
        "Briefkopf", max_length=10, choices=Kopfart.choices, default=Kopfart.LOGO
    )
    logo_lage = models.CharField(
        "Lage", max_length=10, choices=Lage.choices, default=Lage.LINKS
    )
    logo_hoehe = models.PositiveSmallIntegerField(
        "Höhe des Logos in mm",
        default=12,
        validators=[MinValueValidator(LOGO_MM[0]), MaxValueValidator(LOGO_MM[1])],
    )
    logo_zuschneiden = models.BooleanField(
        "Weißen Rand um das Logo abschneiden", default=False
    )
    kopf_name = models.BooleanField("Firmenname und Zusatz", default=True)
    kopf_anschrift = models.BooleanField("Anschrift, Telefon und E-Mail", default=True)
    kopf_linie = models.BooleanField("Linie unter dem Kopf", default=True)
    akzentfarbe = models.CharField(
        "Farbe für Firmenname und Linie",
        max_length=7,
        default=AKZENT,
        validators=[
            RegexValidator(
                r"^#[0-9a-fA-F]{6}$",
                "Bitte eine Farbe im Format #1d5f6e angeben.",
            )
        ],
    )
    kopfbild = models.BinaryField("Kopfbild", blank=True, default=b"")
    kopfbild_breite = models.CharField(
        "Breite", max_length=10, choices=Bildbreite.choices, default=Bildbreite.TEXT
    )

    unterschrift = models.BinaryField("Unterschrift", blank=True, default=b"")
    unterschrift_text = models.TextField("Text unter der Unterschrift", blank=True)

    class Verschluesselung(models.TextChoices):
        STARTTLS = "starttls", "STARTTLS (meist Port 587)"
        SSL = "ssl", "SSL/TLS (meist Port 465)"

    mail_server = models.CharField(
        "Postausgangsserver (SMTP)", max_length=200, blank=True
    )
    mail_port = models.PositiveIntegerField("Port", default=587)
    mail_verschluesselung = models.CharField(
        "Verschlüsselung",
        max_length=10,
        choices=Verschluesselung.choices,
        default=Verschluesselung.STARTTLS,
    )
    mail_benutzer = models.CharField("Benutzername", max_length=200, blank=True)
    # Liegt wie alle Daten nur lokal im Datenordner; verschlüsselte Sicherung folgt in Phase 4.
    mail_passwort = models.CharField("Passwort", max_length=200, blank=True)

    class Meta:
        verbose_name = "Firmendaten"
        verbose_name_plural = "Firmendaten"

    def __str__(self):
        return self.name or "Firmendaten"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.iban = self.iban.replace(" ", "").upper()
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def vollstaendig(self):
        """Absenderangaben, die jede Rechnung braucht (§ 14 Abs. 4 Nr. 1 und 2 UStG)."""
        return bool(
            self.name
            and self.strasse
            and self.plz
            and self.ort
            and (self.steuernummer or self.ust_id)
        )

    @property
    def kleinunternehmer(self):
        """Nur dann gelten die Umsatzgrenzen nach § 19 UStG (Übersicht, Editor)."""
        return self.umsatzsteuer == self.Umsatzsteuer.KLEINUNTERNEHMER

    @property
    def logo_bild(self):
        return daten_url(self.logo)

    @property
    def kopfbild_bild(self):
        return daten_url(self.kopfbild)

    @property
    def unterschrift_bild(self):
        return daten_url(self.unterschrift)

    @property
    def mail_bereit(self):
        return bool(self.email and self.mail_server)

    @property
    def initialen(self):
        teile = (self.inhaber or self.name).split()
        return "".join(t[0] for t in teile[:2]).upper()
