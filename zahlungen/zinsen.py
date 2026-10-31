"""Verzug und Verzugszinsen nach §§ 286, 288 BGB (Spezifikation M-3).

Bewusst vorsichtig gerechnet, damit keine Forderung zu hoch ausfällt:

- Eine Mahnung mit Zahlungsfrist setzt den Kunden erst mit Ablauf der Frist in
  Verzug, also ab dem Tag nach der Frist der ersten Mahnung.
- Unternehmen kommen spätestens 30 Tage nach Fälligkeit und Zugang der Rechnung
  in Verzug (§ 286 Abs. 3 BGB). Als Zugang gilt der Versand per E-Mail, sonst
  drei Tage nach dem Rechnungsdatum. Verbraucher ebenso, wenn die Rechnung den
  Hinweis nach § 286 Abs. 3 BGB enthält (`beleg["verzugshinweis"]`), sonst nur
  nach Mahnung.
- Zinsen laufen vom ersten Verzugstag bis zum Vortag des Stichtags, auf den
  jeweils offenen Betrag, mit dem jeweils gültigen Basiszinssatz, 365 Tage im Jahr.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from invoicing.models import runden

from .models import Basiszins

AUFSCHLAG_VERBRAUCHER = Decimal("5")
AUFSCHLAG_UNTERNEHMEN = Decimal("9")
PAUSCHALE = Decimal("40.00")  # § 288 Abs. 5 BGB, nur gegenüber Unternehmen


class BasiszinsFehlt(Exception):
    """Für einen Teil des Zeitraums ist kein Basiszinssatz eingetragen."""


def aufschlag(kontakt):
    return AUFSCHLAG_VERBRAUCHER if kontakt.ist_verbraucher else AUFSCHLAG_UNTERNEHMEN


def verzug_ab(rechnung, mahnungen):
    """Erster Tag des Verzugs nach den bisherigen `mahnungen`, oder None."""
    tage = []
    if mahnungen:
        tage.append(min(m.frist for m in mahnungen) + timedelta(days=1))
    if rechnung.kontakt and (
        not rechnung.kontakt.ist_verbraucher or rechnung.beleg.get("verzugshinweis")
    ):
        zugang = (
            timezone.localdate(rechnung.versendet_am)
            if rechnung.versendet_am
            else rechnung.datum + timedelta(days=3)
        )
        tage.append(max(zugang, rechnung.faellig) + timedelta(days=31))
    if not tage:
        return None
    return max(min(tage), rechnung.faellig + timedelta(days=1))


def verzugszinsen(rechnung, von, bis):
    """Zinsen auf den offenen Betrag vom Tag `von` bis vor dem Tag `bis`.

    Liefert (Betrag, Tage, Zinssätze in Prozent); Zahlungen mindern den Betrag ab
    ihrem Datum. Wirft BasiszinsFehlt, wenn für einen Tag kein Satz bekannt ist.
    """
    if bis <= von:
        return Decimal("0.00"), 0, []
    plus = aufschlag(rechnung.kontakt)
    zahlungen = list(rechnung.zahlungen.all())
    grenzen = {von, bis}
    grenzen |= {z.datum for z in zahlungen if von < z.datum < bis}
    grenzen |= set(
        Basiszins.objects.filter(gueltig_ab__gt=von, gueltig_ab__lt=bis).values_list(
            "gueltig_ab", flat=True
        )
    )
    punkte = sorted(grenzen)
    summe = Decimal("0")
    saetze = []
    for anfang, ende in zip(punkte, punkte[1:], strict=False):
        basis = Basiszins.am(anfang)
        if basis is None:
            raise BasiszinsFehlt
        satz = basis + plus
        if satz not in saetze:
            saetze.append(satz)
        offen = rechnung.korrigierter_betrag - sum(
            (z.betrag for z in zahlungen if z.datum <= anfang), Decimal("0")
        )
        if offen > 0:
            summe += offen * satz / 100 * (ende - anfang).days / 365
    return runden(summe), (bis - von).days, saetze
