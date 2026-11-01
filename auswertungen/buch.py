"""Rechnungsausgangsbuch (Spezifikation M-5): alle ausgestellten Rechnungen eines Zeitraums.

Dazu gehören festgeschriebene Rechnungen, Stornorechnungen und Rechnungskorrekturen
mit Empfänger und Beträgen, wie sie auf dem Beleg stehen (`Rechnung.beleg`), und die
aus dem Altprogramm übernommenen Rechnungen, Stornos und Gutschriften. Altbelege
tragen nur den gedruckten Betrag; Netto, Umsatzsteuer und Zahlungen sind dort
unbekannt und bleiben leer.
"""

import calendar
from dataclasses import astuple, dataclass
from datetime import date
from decimal import Decimal

from django.urls import reverse

from archive.models import Altbeleg
from invoicing.beleg import MONATE
from invoicing.models import Rechnung

ZEITRAEUME = [("", "Ganzes Jahr")] + [(f"q{q}", f"{q}. Quartal") for q in range(1, 5)]
ZEITRAEUME += [(str(m), name) for m, name in enumerate(MONATE, start=1)]

STEUER = {
    Rechnung.Steuerfall.KLEINUNTERNEHMER: "§ 19 UStG",
    Rechnung.Steuerfall.REGEL: "19 %",
    Rechnung.Steuerfall.UMKEHR: "§ 13b UStG",
}
STAND = {
    "bezahlt": "bezahlt",
    "teilbezahlt": "teilbezahlt",
    "ueberfaellig": "überfällig",
    "offen": "offen",
    "ueberzahlt": "zu viel gezahlt",
    "ausgebucht": "ausgebucht",
    "erledigt": "erledigt",
    "storniert": "storniert",
}


@dataclass
class Zeile:
    datum: date
    nummer: str
    art: str
    bezug: str
    kundennummer: str
    kunde: str
    steuer: str
    netto: Decimal | None
    ust: Decimal | None
    brutto: Decimal | None
    bezahlt: Decimal | None
    bezahlt_am: date | None
    offen: Decimal | None
    stand: str
    quelle: str


# Spalten der Exporte in der Reihenfolge der Felder von Zeile.
SPALTEN = [
    ("Datum", "datum"),
    ("Nummer", "text"),
    ("Art", "text"),
    ("Zu Rechnung", "text"),
    ("Kundennummer", "text"),
    ("Kunde", "text"),
    ("Umsatzsteuer", "text"),
    ("Netto", "betrag"),
    ("USt", "betrag"),
    ("Brutto", "betrag"),
    ("Bezahlt", "betrag"),
    ("Zuletzt bezahlt am", "datum"),
    ("Offen", "betrag"),
    ("Stand", "text"),
    ("Quelle", "text"),
]
SUMMIERT = ("netto", "ust", "brutto", "bezahlt", "offen")


def zeitraum(jahr, wahl):
    """(von, bis, Name für Dateien, Text für die Anzeige) zu Jahr und Auswahl."""
    if wahl.startswith("q"):
        quartal = int(wahl[1])
        bis = 3 * quartal
        von = date(jahr, bis - 2, 1)
        return (
            von,
            date(jahr, bis, calendar.monthrange(jahr, bis)[1]),
            f"{jahr}-Q{quartal}",
            f"im {quartal}. Quartal {jahr}",
        )
    if wahl:
        monat = int(wahl)
        return (
            date(jahr, monat, 1),
            date(jahr, monat, calendar.monthrange(jahr, monat)[1]),
            f"{jahr}-{monat:02d}",
            f"im {MONATE[monat - 1]} {jahr}",
        )
    return date(jahr, 1, 1), date(jahr, 12, 31), str(jahr), f"im Jahr {jahr}"


def zeilen(von, bis):
    """Alle Zeilen des Zeitraums nach Datum und Nummer, je mit Verweis auf den Beleg."""
    ergebnis = []
    rechnungen = (
        Rechnung.objects.filter(
            status=Rechnung.Status.FESTGESCHRIEBEN, datum__range=(von, bis)
        )
        .select_related("kontakt", "storno_zu", "korrektur_zu", "stornorechnung")
        .prefetch_related("zahlungen", "korrekturen")
    )
    for r in rechnungen:
        empfaenger = r.beleg.get("empfaenger", {})
        original = r.storno_zu or r.korrektur_zu
        posten = r.ist_posten
        ergebnis.append(
            (
                Zeile(
                    datum=r.datum,
                    nummer=r.nummer,
                    art=r.bezeichnung,
                    bezug=original.nummer if original else "",
                    kundennummer=empfaenger.get("kundennummer", ""),
                    kunde=empfaenger.get("name") or str(r.kontakt or ""),
                    steuer=STEUER[r.steuerfall],
                    netto=r.netto,
                    ust=r.ust,
                    brutto=r.brutto,
                    bezahlt=r.bezahlt if posten else None,
                    bezahlt_am=max(
                        (z.datum for z in r.zahlungen.all() if not z.ist_ausbuchung),
                        default=None,
                    )
                    if posten
                    else None,
                    offen=r.offen if posten else None,
                    stand=STAND[r.zahlstand] if posten else "",
                    quelle="Kontorfreund",
                ),
                reverse("invoicing:bearbeiten", args=[r.pk]),
            )
        )
    altbelege = Altbeleg.objects.filter(
        art__in=Altbeleg.UMSATZWIRKSAM, datum__range=(von, bis)
    ).select_related("kontakt")
    for a in altbelege:
        ergebnis.append(
            (
                Zeile(
                    datum=a.datum,
                    nummer=a.nummer,
                    art=a.get_art_display(),
                    bezug=a.bezug,
                    kundennummer=a.kontakt.kundennummer if a.kontakt else "",
                    kunde=str(a.kontakt) if a.kontakt else a.empfaenger.split("\n")[0],
                    steuer="",
                    netto=None,
                    ust=None,
                    brutto=a.betrag,
                    bezahlt=None,
                    bezahlt_am=None,
                    offen=None,
                    stand="",
                    quelle="Altprogramm",
                ),
                reverse("archive:datei", args=[a.pk]),
            )
        )
    return sorted(ergebnis, key=lambda e: (e[0].datum, e[0].nummer))


def summen(zeilen):
    return {
        feld: sum(
            (w for z in zeilen if (w := getattr(z, feld)) is not None),
            Decimal("0.00"),
        )
        for feld in SUMMIERT
    }


def tabelle(zeilen):
    """Zeilen für den Export, mit einer Summenzeile am Ende."""
    s = summen(zeilen)
    summe = [None, "Summe"] + [""] * 5
    summe += [s["netto"], s["ust"], s["brutto"], s["bezahlt"], None, s["offen"], "", ""]
    return [list(astuple(z)) for z in zeilen] + [summe]
