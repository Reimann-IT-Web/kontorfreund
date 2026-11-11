"""Umsatzgrenzen der Kleinunternehmerregelung (§ 19 Abs. 1 UStG seit 2025, Spezifikation B-4).

- Vorjahr höchstens 25.000 €, sonst gilt § 19 im laufenden Jahr nicht.
- Laufendes Jahr höchstens 100.000 €. Schon der Umsatz, mit dem die Grenze
  überschritten wird, unterliegt der Regelbesteuerung.
- Ab 80 % einer Grenze warnt das Programm.

Umsatz eines Jahres: übernommene Altbelege (Betrag wie gedruckt, als Kleinunternehmer
ohne Umsatzsteuer) plus festgeschriebene Rechnungen netto; Stornos und Korrekturen
sind negativ und mindern. Steuerfreie Rechnungen zählen nicht: § 19 Abs. 2 Nr. 1
UStG zieht die Umsätze nach § 4 Nr. 8 Buchst. i, Nr. 9 Buchst. b und Nr. 11 bis 29
vom Gesamtumsatz ab. Die übrigen Befreiungen (§ 4 Nr. 8 Buchst. a bis h, Nr. 9
Buchst. a, Nr. 10) zählen mit, außer bei Hilfsumsätzen; das nennt die Hilfe.
"""

from decimal import Decimal

from django.db.models import Sum

from archive.models import Altbeleg
from core.templatetags.kf import euro
from invoicing.models import Rechnung

VORJAHR = Decimal("25000.00")
LAUFEND = Decimal("100000.00")
WARNEN_AB = Decimal("0.8")


def umsatz(jahr):
    alt = Altbeleg.objects.filter(
        art__in=Altbeleg.UMSATZWIRKSAM, datum__year=jahr
    ).aggregate(s=Sum("betrag"))["s"]
    neu = (
        Rechnung.objects.filter(
            status=Rechnung.Status.FESTGESCHRIEBEN, datum__year=jahr
        )
        .exclude(steuerfall=Rechnung.Steuerfall.STEUERFREI)
        .aggregate(s=Sum("netto"))["s"]
    )
    return (alt or Decimal("0.00")) + (neu or Decimal("0.00"))


def _prozent(teil, ganz):
    return f"{round(teil / ganz * 100)} %"


def ueber_laufender_grenze(jahr, dazu):
    """Ob eine Rechnung über `dazu` den Umsatz des Jahres über 100.000 € brächte."""
    return umsatz(jahr) + dazu > LAUFEND


def hinweise(jahr, dazu=Decimal("0.00")):
    """Warnungen zum Jahr; `dazu` ist der Nettobetrag einer Rechnung, die noch kommt."""
    vorjahr, jetzt = umsatz(jahr - 1), umsatz(jahr) + dazu
    if dazu:
        erreicht = f"Mit dieser Rechnung erreicht Ihr Umsatz {jahr}"
    else:
        erreicht = f"Ihr Umsatz {jahr} erreicht"
    texte = []
    if vorjahr > VORJAHR:
        texte.append(
            f"Ihr Umsatz {jahr - 1} lag mit {euro(vorjahr)} über {euro(VORJAHR)}. "
            f"Damit gilt die Kleinunternehmerregelung {jahr} nicht, Sie müssen "
            "Umsatzsteuer ausweisen."
        )
    if jetzt > LAUFEND:
        texte.append(
            f"{erreicht} {euro(jetzt)} und liegt damit über {euro(LAUFEND)}. Schon "
            "dieser Umsatz unterliegt der Regelbesteuerung: Weisen Sie Umsatzsteuer aus."
        )
    elif jetzt >= LAUFEND * WARNEN_AB:
        texte.append(
            f"{erreicht} {euro(jetzt)}, {_prozent(jetzt, LAUFEND)} von {euro(LAUFEND)}. "
            "Ab dieser Grenze müssen Sie sofort Umsatzsteuer ausweisen."
        )
    elif jetzt > VORJAHR:
        texte.append(
            f"{erreicht} {euro(jetzt)} und liegt damit über {euro(VORJAHR)}. "
            f"Ab {jahr + 1} gilt die Kleinunternehmerregelung deshalb nicht mehr."
        )
    elif jetzt >= VORJAHR * WARNEN_AB:
        texte.append(
            f"{erreicht} {euro(jetzt)}, {_prozent(jetzt, VORJAHR)} von {euro(VORJAHR)}. "
            f"Liegt er am Jahresende darüber, gilt die Kleinunternehmerregelung ab "
            f"{jahr + 1} nicht mehr."
        )
    return texte
