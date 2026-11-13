"""Verträge, aus denen sich wiederholende Rechnungen entstehen (Spezifikation B-10)."""

import calendar
from datetime import date, timedelta

from django.db import models

from contacts.models import Kontakt
from invoicing.models import Rechnung, runden, steuersatzfeld, summen


def monate_spaeter(tag, monate):
    """Derselbe Tag `monate` Monate später; gibt es ihn nicht, der letzte des Monats."""
    jahr, monat = divmod(tag.month - 1 + monate, 12)
    jahr, monat = tag.year + jahr, monat + 1
    return date(jahr, monat, min(tag.day, calendar.monthrange(jahr, monat)[1]))


class Vertrag(models.Model):
    """Rechnung, die sich in festem Rhythmus wiederholt; abgerechnet im Voraus."""

    NACHFRAGEN = [
        (0, "nicht nachfragen"),
        (14, "2 Wochen vorher"),
        (30, "4 Wochen vorher"),
        (60, "8 Wochen vorher"),
    ]

    class Rhythmus(models.IntegerChoices):
        MONATLICH = 1, "monatlich"
        VIERTELJAEHRLICH = 3, "vierteljährlich"
        HALBJAEHRLICH = 6, "halbjährlich"
        JAEHRLICH = 12, "jährlich"

    bezeichnung = models.CharField(
        "Bezeichnung",
        max_length=100,
        help_text="Nur für Sie, etwa „Wartung Server“. Sie steht auch in der "
        "Nachricht über Telegram, deshalb am besten ohne Namen des Kunden.",
    )
    kontakt = models.ForeignKey(
        Kontakt,
        verbose_name="Empfänger",
        on_delete=models.PROTECT,
        related_name="vertraege",
    )
    betreff = models.CharField("Betreff", max_length=200, blank=True)
    rhythmus = models.PositiveSmallIntegerField(
        "Rhythmus", choices=Rhythmus.choices, default=Rhythmus.HALBJAEHRLICH
    )
    beginn = models.DateField(
        "Erster Zeitraum ab",
        help_text="An diesem Tag entsteht der erste Rechnungsentwurf, danach am "
        "Anfang jedes weiteren Zeitraums.",
    )
    ende = models.DateField(
        "Endet am",
        null=True,
        blank=True,
        help_text="Leer, solange der Vertrag läuft. Für Zeiträume, die danach "
        "beginnen, entsteht kein Entwurf mehr.",
    )
    # Beginn des nächsten Zeitraums, für den noch kein Entwurf entstanden ist.
    naechster = models.DateField("Nächster Entwurf am", editable=False)
    nachfragen = models.PositiveSmallIntegerField(
        "Vor jeder Verlängerung nachfragen",
        choices=NACHFRAGEN,
        default=30,
        help_text="Legt so lange vor jedem weiteren Zeitraum eine Wiedervorlage an: "
        "Fortsetzung und Preis mit dem Kunden klären.",
    )
    # Zeitraum (Beginn), für den die Wiedervorlage schon angelegt ist.
    nachgefragt_fuer = models.DateField(null=True, blank=True, editable=False)
    zahlungsziel = models.PositiveSmallIntegerField("Zahlungsziel in Tagen", default=14)
    rabatt_prozent = models.DecimalField(
        "Rabatt in Prozent", max_digits=5, decimal_places=2, default=0
    )
    steuerfall = models.CharField(
        max_length=20,
        choices=Rechnung.Steuerfall.choices,
        default=Rechnung.Steuerfall.KLEINUNTERNEHMER,
    )
    kopftext = models.TextField("Text vor den Positionen", blank=True)
    fusstext = models.TextField("Text nach den Positionen", blank=True)
    angelegt = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["bezeichnung", "pk"]
        verbose_name = "Vertrag"
        verbose_name_plural = "Verträge"

    def __str__(self):
        return self.bezeichnung

    def save(self, *args, **kwargs):
        # Ein neuer Vertrag beginnt mit seinem ersten Zeitraum. Ist noch kein Entwurf
        # entstanden (der nächste ist noch der Beginn), verschiebt ein geänderter
        # Beginn ihn mit; danach zählt Kontorfreund ab dem letzten Zeitraum weiter.
        bisher = (
            Vertrag.objects.filter(pk=self.pk)
            .values_list("beginn", "naechster")
            .first()
            if self.pk
            else None
        )
        if bisher is None or bisher[0] == bisher[1]:
            self.naechster = self.beginn
        super().save(*args, **kwargs)

    def zeitraum(self, beginn):
        """(von, bis) des Zeitraums, der an `beginn` anfängt."""
        return beginn, monate_spaeter(beginn, self.rhythmus) - timedelta(days=1)

    @property
    def laeuft(self):
        return self.ende is None or self.naechster <= self.ende

    def summen(self):
        """(netto, ust, brutto) je Zeitraum, wie auf dem Entwurf."""
        return summen(self.positionen.all(), self.steuerfall, self.rabatt_prozent)


class Position(models.Model):
    """Feste Position, die jeder Entwurf übernimmt; Zusätzliches kommt in den Entwurf."""

    vertrag = models.ForeignKey(
        Vertrag, on_delete=models.CASCADE, related_name="positionen"
    )
    nr = models.PositiveSmallIntegerField()
    bezeichnung = models.CharField(max_length=200, blank=True)
    beschreibung = models.TextField(blank=True)
    menge = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    einheit = models.CharField(max_length=20, blank=True)
    preis = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    steuersatz = steuersatzfeld()

    class Meta:
        ordering = ["nr"]
        verbose_name = "Vertragsposition"
        verbose_name_plural = "Vertragspositionen"

    def __str__(self):
        return f"{self.nr}. {self.bezeichnung}"

    @property
    def gesamt(self):
        return runden(self.menge * self.preis)
