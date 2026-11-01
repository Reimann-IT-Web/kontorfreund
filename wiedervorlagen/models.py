import calendar
from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from angebote.models import Angebot
from contacts.models import Kontakt
from invoicing.models import Rechnung


def naechster_monat(tag):
    """Derselbe Tag im Folgemonat; den 31. gibt es nicht immer."""
    jahr, monat = (tag.year + 1, 1) if tag.month == 12 else (tag.year, tag.month + 1)
    return date(jahr, monat, min(tag.day, calendar.monthrange(jahr, monat)[1]))


# „Demnächst“ auf der Übersicht und in der Liste: so viele Tage voraus.
DEMNAECHST = 7

# Schnell verschieben, immer von heute aus (Spezifikation K-4).
VERSCHIEBEN = {
    "morgen": lambda heute: heute + timedelta(days=1),
    "woche": lambda heute: heute + timedelta(days=7),
    "monat": naechster_monat,
}


class Wiedervorlage(models.Model):
    """Erinnerung mit Fälligkeit (Spezifikation K-4), offen, bis sie erledigt ist.

    Bezug ist eine Adresse, auf Wunsch zusätzlich ein Angebot oder eine Rechnung.
    Erledigte Wiedervorlagen erscheinen in der Kontakthistorie der Adresse.
    """

    titel = models.CharField("Was ist zu tun?", max_length=200)
    faellig = models.DateField("Fällig am", default=date.today)
    uhrzeit = models.TimeField("Uhrzeit", null=True, blank=True)
    zustaendig = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Zuständig",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wiedervorlagen",
    )
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Adresse",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="wiedervorlagen",
    )
    angebot = models.ForeignKey(
        Angebot,
        verbose_name="Angebot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="wiedervorlagen",
    )
    rechnung = models.ForeignKey(
        Rechnung,
        verbose_name="Rechnung",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="wiedervorlagen",
    )
    notiz = models.TextField("Notiz", blank=True)
    erledigt_am = models.DateTimeField("Erledigt am", null=True, blank=True)
    erledigt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    ergebnis = models.TextField("Ergebnis", blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wiedervorlage"
        verbose_name_plural = "Wiedervorlagen"
        ordering = ["faellig", "uhrzeit", "pk"]

    def __str__(self):
        return self.titel

    @property
    def erledigt(self):
        return self.erledigt_am is not None

    @property
    def ueberfaellig(self):
        return not self.erledigt and self.faellig < date.today()

    @property
    def heute(self):
        return not self.erledigt and self.faellig == date.today()

    @property
    def beleg(self):
        return self.rechnung or self.angebot

    def erledigen(self, benutzer, ergebnis=""):
        self.erledigt_am = timezone.now()
        self.erledigt_von = benutzer
        self.ergebnis = ergebnis
        self.save()

    def oeffnen(self):
        self.erledigt_am = None
        self.erledigt_von = None
        self.save()

    def verschieben(self, wohin):
        self.faellig = VERSCHIEBEN[wohin](date.today())
        self.save()

    @classmethod
    def offen_fuer(cls, benutzer):
        """Offene Wiedervorlagen dieses Benutzers und die ohne Zuständigen."""
        return cls.objects.filter(erledigt_am__isnull=True).filter(
            models.Q(zustaendig=benutzer) | models.Q(zustaendig__isnull=True)
        )
