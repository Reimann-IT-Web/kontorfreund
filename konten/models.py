"""Benutzer mit Anmeldung per E-Mail, Rolle und Zwei-Faktor-Anmeldung (Spezifikation K-5)."""

from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

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
    erstellt = models.DateTimeField(auto_now_add=True)

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

    @property
    def ist_inhaber(self):
        return self.rolle == self.Rolle.INHABER

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
