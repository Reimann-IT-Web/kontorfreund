"""DATEV-Export (Spezifikation M-4): Buchungsstapel im DATEV-Format, Formatversion 13.

Nach der öffentlichen Formatbeschreibung von DATEV: eine Kopfzeile mit Berater, Mandant
und Zeitraum, eine Zeile mit den 125 Feldnamen, dann eine Buchung je Beleg. Jede
festgeschriebene Rechnung, Stornorechnung und Rechnungskorrektur bucht ihren
Bruttobetrag vom Debitor an das Erlöskonto ihres Steuerfalls, Stornos und Korrekturen
im Haben. Das Erlöskonto für 19 % ist ein Automatikkonto: DATEV rechnet die
Umsatzsteuer selbst heraus. Altbelege fehlen, weil ihr Steuerfall unbekannt ist.

Die Datei ist Windows-1252 kodiert, mit Semikolon und CR/LF, wie DATEV sie erwartet.
"""

import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings

from invoicing.models import Rechnung

FELDER = [
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
    "Postensperre",
    "Diverse Adressnummer",
    "Geschäftspartnerbank",
    "Sachverhalt",
    "Zinssperre",
    "Beleglink",
    *(f"Beleginfo - {teil} {n}" for n in range(1, 9) for teil in ("Art", "Inhalt")),
    "KOST1 - Kostenstelle",
    "KOST2 - Kostenstelle",
    "Kost-Menge",
    "EU-Land u. UStID (Bestimmung)",
    "EU-Steuersatz (Bestimmung)",
    "Abw. Versteuerungsart",
    "Sachverhalt L+L",
    "Funktionsergänzung L+L",
    "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer",
    "BU 49 Funktionsergänzung",
    *(
        name
        for n in range(1, 21)
        for name in (f"Zusatzinformation - Art {n}", f"Zusatzinformation- Inhalt {n}")
    ),
    "Stück",
    "Gewicht",
    "Zahlweise",
    "Forderungsart",
    "Veranlagungsjahr",
    "Zugeordnete Fälligkeit",
    "Skontotyp",
    "Auftragsnummer",
    "Buchungstyp (Anzahlungen)",
    "USt-Schlüssel (Anzahlungen)",
    "EU-Land (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen)",
    "EU-Steuersatz (Anzahlungen)",
    "Erlöskonto (Anzahlungen)",
    "Herkunft-Kz",
    "Buchungs GUID",
    "Kost-Datum",
    "SEPA-Mandatsreferenz",
    "Skontosperre",
    "Gesellschaftername",
    "Beteiligtennummer",
    "Identifikationsnummer",
    "Zeichnernummer",
    "Postensperre bis",
    "Bezeichnung SoBil-Sachverhalt",
    "Kennzeichen SoBil-Buchung",
    "Festschreibung",
    "Leistungsdatum",
    "Datum Zuord. Steuerperiode",
    "Fälligkeit",
    "Generalumkehr (GU)",
    "Steuersatz",
    "Land",
    "Abrechnungsreferenz",
    "BVV-Position",
    "EU-Land u. UStID (Ursprung)",
    "EU-Steuersatz (Ursprung)",
    "Abw. Skontokonto",
]


@dataclass
class Buchung:
    datum: date
    beleg: str
    art: str
    text: str
    betrag: Decimal
    # Bezogen auf das Debitorenkonto: S für Rechnungen, H für Stornos und Korrekturen.
    soll_haben: str
    konto: int
    gegenkonto: int
    leistungsdatum: date
    rechnung: Rechnung


def buchungen(von, bis, einstellung):
    """Eine Buchung je festgeschriebenem Beleg im Zeitraum, nach Datum und Nummer."""
    rechnungen = (
        Rechnung.objects.filter(
            status=Rechnung.Status.FESTGESCHRIEBEN, datum__range=(von, bis)
        )
        .select_related("kontakt")
        .order_by("datum", "nummer")
    )
    ergebnis = []
    for r in rechnungen:
        kunde = r.beleg.get("empfaenger", {}).get("name") or str(r.kontakt)
        ergebnis.append(
            Buchung(
                datum=r.datum,
                beleg=r.nummer,
                art=r.bezeichnung,
                text=kunde if r.ist_posten else f"{r.bezeichnung} {kunde}",
                betrag=abs(r.brutto),
                soll_haben="S" if r.brutto > 0 else "H",
                konto=einstellung.debitor(r.kontakt),
                gegenkonto=einstellung.erloeskonto(r.steuerfall),
                leistungsdatum=r.leistung_bis or r.leistung_von,
                rechnung=r,
            )
        )
    return ergebnis


def _text(wert, laenge):
    wert = " ".join(str(wert).split())[:laenge]
    return '"' + wert.replace('"', '""') + '"'


def kopf(einstellung, von, bis, bezeichnung, jetzt):
    """Die 31 Felder der Kopfzeile."""
    return [
        '"EXTF"',
        "700",
        "21",
        '"Buchungsstapel"',
        "13",
        f"{jetzt:%Y%m%d%H%M%S}{jetzt.microsecond // 1000:03d}",
        "",
        '"RE"',
        '""',
        '""',
        str(einstellung.beraternummer),
        str(einstellung.mandantennummer),
        f"{von.year}0101",
        "4",
        f"{von:%Y%m%d}",
        f"{bis:%Y%m%d}",
        _text(bezeichnung, 30),
        '""',
        "1",
        "0",
        # Nicht festschreiben, damit der Steuerberater noch korrigieren kann.
        "0",
        '"EUR"',
        "",
        '""',
        "",
        "",
        f'"{einstellung.kontenrahmen}"',
        "",
        "",
        '""',
        '""',
    ]


def zeile(b):
    werte = {
        "Umsatz (ohne Soll/Haben-Kz)": f"{b.betrag:.2f}".replace(".", ","),
        "Soll/Haben-Kennzeichen": f'"{b.soll_haben}"',
        "WKZ Umsatz": '"EUR"',
        "Konto": str(b.konto),
        "Gegenkonto (ohne BU-Schlüssel)": str(b.gegenkonto),
        "Belegdatum": f"{b.datum:%d%m}",
        "Belegfeld 1": _text(b.beleg, 36),
        "Buchungstext": _text(b.text, 60),
        "Leistungsdatum": f"{b.leistungsdatum:%d%m%Y}",
    }
    return [werte.get(feld, "") for feld in FELDER]


def datei(einstellung, von, bis, bezeichnung, eintraege, jetzt):
    zeilen = [
        kopf(einstellung, von, bis, bezeichnung, jetzt),
        FELDER,
        *(zeile(b) for b in eintraege),
    ]
    text = "".join(";".join(z) + "\r\n" for z in zeilen)
    return text.encode("cp1252", errors="replace")


def mit_rechnungen(inhalt, dateiname, eintraege):
    """ZIP mit der DATEV-Datei und den Belegen (PDF, bei XRechnung auch die XML)."""
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(dateiname, inhalt)
        for b in eintraege:
            for name, pfad, _ in b.rechnung.anhaenge:
                z.write(Path(settings.DATA_DIR) / pfad, f"Rechnungen/{name}")
    return puffer.getvalue()
