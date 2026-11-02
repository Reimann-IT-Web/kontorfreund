"""Benutzer mit Anmeldung per E-Mail, Rolle und Zwei-Faktor-Anmeldung (Spezifikation K-5)."""

from datetime import date, timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.crypto import salted_hmac

FEHLVERSUCHE = 5
SPERRE = timedelta(minutes=15)


class BenutzerManager(BaseUserManager):
    def create_user(self, email, password=None, **felder):
        benutzer = self.model(email=email, **felder)
        benutzer.set_password(password)
        benutzer.save(using=self._db)
        return benutzer

    def create_superuser(self, email, password=None, **felder):
        """Für `manage.py createsuperuser`: legt einen Inhaber an."""
        return self.create_user(email, password, rolle=Benutzer.Rolle.INHABER, **felder)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class Benutzer(AbstractBaseUser):
    class Rolle(models.TextChoices):
        INHABER = "inhaber", "Inhaber"
        MITARBEITER = "mitarbeiter", "Mitarbeiter"
        # Betriebsprüfer des Finanzamts: liest nur, nur den Prüfungszeitraum, nur bis
        # `zugang_bis` (Datenzugriff nach § 147 Abs. 6 AO, Spezifikation D-6).
        PRUEFER = "pruefer", "Prüfer"

    email = models.EmailField("E-Mail-Adresse", unique=True)
    name = models.CharField("Name", max_length=100)
    rolle = models.CharField(
        "Rolle", max_length=20, choices=Rolle.choices, default=Rolle.MITARBEITER
    )
    is_active = models.BooleanField("Aktiv", default=True)
    # Zwei-Faktor-Anmeldung (TOTP): Geheimnis in Base32 und der zuletzt genutzte
    # Zeitschritt, damit derselbe Code nicht zweimal gilt.
    totp_geheimnis = models.CharField(max_length=64, blank=True, editable=False)
    totp_schritt = models.BigIntegerField(default=0, editable=False)
    fehlversuche = models.PositiveSmallIntegerField(default=0, editable=False)
    gesperrt_bis = models.DateTimeField(null=True, blank=True, editable=False)
    # Das Kennwort hat der Inhaber vergeben; nach der Anmeldung wählt man ein eigenes.
    kennwort_vorlaeufig = models.BooleanField(default=False, editable=False)
    erstellt = models.DateTimeField(auto_now_add=True)
    zugang_bis = models.DateField("Zugang bis", null=True, blank=True)
    pruefung_von = models.PositiveSmallIntegerField(
        "Prüfungszeitraum von", null=True, blank=True
    )
    pruefung_bis = models.PositiveSmallIntegerField(
        "Prüfungszeitraum bis", null=True, blank=True
    )

    objects = BenutzerManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"
        ordering = ["name"]

    def __str__(self):
        return self.name or self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def _get_session_auth_hash(self, secret=None):
        """Wie bei Django aus dem Kennwort, dazu aus dem Geheimnis der Zwei-Faktor-
        Anmeldung: Wer eins davon ändert, beendet alle übrigen Sitzungen (ASVS 7.4.3)."""
        return salted_hmac(
            "django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash",
            self.password + self.totp_geheimnis,
            secret=secret,
            algorithm="sha256",
        ).hexdigest()

    @property
    def ist_inhaber(self):
        return self.rolle == self.Rolle.INHABER

    @property
    def ist_pruefer(self):
        return self.rolle == self.Rolle.PRUEFER

    @property
    def zugang_offen(self):
        """Ein Prüfer meldet sich bis einschließlich `zugang_bis` an, danach nicht mehr."""
        return not self.ist_pruefer or bool(
            self.zugang_bis and timezone.localdate() <= self.zugang_bis
        )

    @property
    def zeitraum(self):
        """Erster und letzter Tag des Prüfungszeitraums."""
        return date(self.pruefung_von, 1, 1), date(self.pruefung_bis, 12, 31)

    @property
    def zwei_faktor(self):
        return bool(self.totp_geheimnis)

    @property
    def initialen(self):
        teile = self.name.split()
        return "".join(t[0] for t in teile[:2]).upper() or self.email[:1].upper()

    @property
    def gesperrt(self):
        return self.gesperrt_bis is not None and self.gesperrt_bis > timezone.now()

    def fehlversuch(self):
        """Fehlversuch zählen; nach dem fünften ist das Konto 15 Minuten gesperrt."""
        self.fehlversuche += 1
        if self.fehlversuche >= FEHLVERSUCHE:
            self.fehlversuche = 0
            self.gesperrt_bis = timezone.now() + SPERRE
        self.save(update_fields=["fehlversuche", "gesperrt_bis"])

    def entsperren(self):
        self.fehlversuche = 0
        self.gesperrt_bis = None
        self.save(update_fields=["fehlversuche", "gesperrt_bis"])
