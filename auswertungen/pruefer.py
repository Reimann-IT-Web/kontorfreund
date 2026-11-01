"""Datenträgerüberlassung für die Betriebsprüfung (§ 147 Abs. 6 AO, Spezifikation D-6).

Ein ZIP nach dem „Beschreibungsstandard für die Datenträgerüberlassung“ der
Finanzverwaltung: index.xml, daneben die DTD (`daten/gdpdu-01-08-2002.dtd`, Version 1.1,
unverändert, wie der Standard verlangt; spätere Versionen erweitern sie nur, und
index.xml nutzt nichts davon), die Tabellen als CSV und alle Belege des Zeitraums unter
ihrem Pfad im Archiv. Welche Tabellen und Felder geliefert werden, gibt die
Finanzverwaltung nicht vor.

CSV: UTF-8 ohne BOM (<UTF8/>), Semikolon, CR/LF, eine Kopfzeile (<Range> ab Satz 2),
Dezimalkomma ohne Tausenderpunkt, Datum TT.MM.JJJJ. Zeilenumbrüche in Texten werden zu
Leerzeichen, weil ein Prüfprogramm sie als Satzende läse. Primärschlüssel stehen vorn,
weil die DTD sie vor den übrigen Spalten verlangt; Fremdschlüssel heißen wie der
Schlüssel der Tabelle, auf die sie verweisen. Spaltennamen ohne Umlaute, damit jedes
Prüfprogramm sie annimmt; die deutschen Erläuterungen stehen in <Description>.
"""

import csv
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone

from archive.models import Altbeleg
from core.models import Firmendaten
from core.templatetags.kf import zahl
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from zahlungen.models import Mahnung, Zahlung

from .buch import STEUER

DTD = Path(__file__).parent / "daten" / "gdpdu-01-08-2002.dtd"
DTD_SHA256 = "e93a716e8e022b8624b02f12b805f67c25e3fdd40fe422036f2abbea464e0b76"

TEXT, DATUM, BETRAG, MENGE, GANZ = "text", "datum", "betrag", "menge", "ganz"
STELLEN = {BETRAG: 2, MENGE: 3, GANZ: 0}
TYP = {
    TEXT: "<AlphaNumeric/>",
    DATUM: "<Date><Format>DD.MM.YYYY</Format></Date>",
    BETRAG: "<Numeric><Accuracy>2</Accuracy></Numeric>",
    MENGE: "<Numeric><Accuracy>3</Accuracy></Numeric>",
    GANZ: "<Numeric/>",
}


@dataclass
class Tabelle:
    datei: str
    name: str
    beschreibung: str
    # (Name, Art, Erläuterung); die ersten `schluessel` bilden den Primärschlüssel.
    spalten: list
    zeilen: list = field(default_factory=list)
    schluessel: int = 0
    # (Spalte, Name der Tabelle mit diesem Schlüssel)
    verweise: list = field(default_factory=list)
    # Bewegungsdaten gelten für den Zeitraum, Stammdaten sind der Stand von heute.
    zeitraum: bool = True


def _datum(text):
    return date.fromisoformat(text) if text else None


def _wert(wert, art):
    if wert is None or wert == "":
        return ""
    if art == DATUM:
        if isinstance(wert, datetime):
            wert = timezone.localdate(wert)
        return f"{wert:%d.%m.%Y}"
    if art in STELLEN:
        return zahl(wert, STELLEN[art])
    return re.sub(r"\s*[\r\n]+\s*", " ", str(wert)).strip()


def csv_inhalt(tabelle):
    aus = StringIO()
    schreiber = csv.writer(aus, delimiter=";", quotechar='"', lineterminator="\r\n")
    schreiber.writerow([name for name, _, _ in tabelle.spalten])
    for zeile in tabelle.zeilen:
        schreiber.writerow(
            [
                _wert(w, art)
                for w, (_, art, _) in zip(zeile, tabelle.spalten, strict=True)
            ]
        )
    return aus.getvalue().encode("utf-8")


def tabellen(von, bis):
    """Die Tabellen des Zeitraums und die Pfade der Belegdateien im Datenordner."""
    rechnungen = list(
        Rechnung.objects.filter(
            status=Rechnung.Status.FESTGESCHRIEBEN, datum__range=(von, bis)
        )
        .select_related("kontakt", "storno_zu", "korrektur_zu")
        .order_by("datum", "nummer")
    )
    zahlungen = Zahlung.objects.filter(datum__range=(von, bis)).select_related(
        "rechnung"
    )
    mahnungen = Mahnung.objects.filter(datum__range=(von, bis)).select_related(
        "rechnung"
    )
    eingang = Eingangsrechnung.objects.filter(datum__range=(von, bis)).select_related(
        "kontakt"
    )
    altbelege = Altbeleg.objects.filter(
        art__in=Altbeleg.UMSATZWIRKSAM, datum__range=(von, bis)
    ).select_related("kontakt")

    ausgang = Tabelle(
        "rechnungen.csv",
        "Rechnungsausgang",
        "Ausgestellte Rechnungen, Stornorechnungen und Rechnungskorrekturen mit den "
        "Angaben wie auf dem Beleg",
        [
            ("Rechnungsnummer", TEXT, ""),
            ("Rechnungsdatum", DATUM, ""),
            ("Art", TEXT, "Rechnung, Stornorechnung oder Rechnungskorrektur"),
            (
                "Zu Rechnung",
                TEXT,
                "Bei Storno und Korrektur die ursprüngliche Rechnung",
            ),
            ("Kundennummer", TEXT, ""),
            ("Kunde", TEXT, "Empfänger wie auf der Rechnung"),
            ("Leistung von", DATUM, "Leistungsdatum oder Beginn des Zeitraums"),
            ("Leistung bis", DATUM, "Ende des Leistungszeitraums"),
            ("Umsatzsteuer", TEXT, "§ 19 UStG, 19 % oder § 13b UStG"),
            ("Netto", BETRAG, ""),
            ("USt", BETRAG, "Umsatzsteuer"),
            ("Brutto", BETRAG, ""),
            ("Faellig am", DATUM, "Fälligkeit nach dem Zahlungsziel"),
            ("Festgeschrieben am", DATUM, "Seitdem ist der Beleg unveränderbar"),
            ("PDF", TEXT, "Pfad der Rechnung in diesem Datenpaket"),
            ("PDF SHA-256", TEXT, "Prüfsumme der Datei seit dem Festschreiben"),
            ("XML", TEXT, "Pfad der XRechnung, falls ausgestellt"),
            ("XML SHA-256", TEXT, "Prüfsumme der XRechnung"),
        ],
        schluessel=1,
        verweise=[("Kundennummer", "Adressen")],
    )
    positionen = Tabelle(
        "positionen.csv",
        "Rechnungspositionen",
        "Positionen der Rechnungen im Rechnungsausgang, wie auf dem Beleg",
        [
            ("Rechnungsnummer", TEXT, ""),
            ("Position", GANZ, ""),
            ("Bezeichnung", TEXT, ""),
            ("Beschreibung", TEXT, ""),
            ("Menge", MENGE, ""),
            ("Einheit", TEXT, ""),
            ("Einzelpreis", BETRAG, ""),
            ("Gesamt", BETRAG, "Menge mal Einzelpreis, kaufmännisch gerundet"),
        ],
        verweise=[("Rechnungsnummer", "Rechnungsausgang")],
    )
    belege = []
    for r in rechnungen:
        b = r.beleg
        original = r.storno_zu or r.korrektur_zu
        empfaenger = b.get("empfaenger", {})
        ausgang.zeilen.append(
            [
                r.nummer,
                r.datum,
                r.bezeichnung,
                original.nummer if original else "",
                empfaenger.get("kundennummer", ""),
                empfaenger.get("name", ""),
                _datum(b.get("leistung_von")),
                _datum(b.get("leistung_bis")),
                STEUER[r.steuerfall],
                r.netto,
                r.ust,
                r.brutto,
                _datum(b.get("faellig")),
                r.festgeschrieben_am,
                r.datei,
                r.sha256,
                r.xml_datei,
                r.xml_sha256,
            ]
        )
        for p in b.get("positionen", []):
            positionen.zeilen.append(
                [
                    r.nummer,
                    p["nr"],
                    p["bezeichnung"],
                    p["beschreibung"],
                    Decimal(p["menge"]),
                    p["einheit"],
                    Decimal(p["preis"]),
                    Decimal(p["gesamt"]),
                ]
            )
        belege += [d for d in (r.datei, r.xml_datei) if d]

    zahlungstabelle = Tabelle(
        "zahlungen.csv",
        "Zahlungen",
        "Zahlungseingänge, Ausbuchungen und Skonto mit Datum im Zeitraum; Rechnungen "
        "aus früheren Zeiträumen stehen in deren Datenpaket",
        [
            ("Rechnungsnummer", TEXT, ""),
            ("Datum", DATUM, ""),
            (
                "Art",
                TEXT,
                "Überweisung, Bar, Lastschrift, Sonstige, Ausgebucht, Skonto",
            ),
            ("Betrag", BETRAG, "Mindert die offene Rechnung"),
            ("Nebenkosten", BETRAG, "Gezahlte Mahngebühren und Zinsen"),
            ("Notiz", TEXT, ""),
        ],
        [
            [z.rechnung.nummer, z.datum, z.get_art_display(), z.betrag]
            + [z.nebenkosten, z.notiz]
            for z in zahlungen.order_by("datum", "pk")
        ],
        verweise=[("Rechnungsnummer", "Rechnungsausgang")],
    )
    mahntabelle = Tabelle(
        "mahnungen.csv",
        "Mahnungen",
        "Zahlungserinnerungen und Mahnungen mit Datum im Zeitraum",
        [
            ("Rechnungsnummer", TEXT, ""),
            ("Stufe", TEXT, ""),
            ("Datum", DATUM, ""),
            ("Zahlen bis", DATUM, ""),
            ("Offen", BETRAG, "Offener Rechnungsbetrag am Mahntag"),
            ("Mahngebuehr", BETRAG, "Mahngebühr"),
            ("Zinsen", BETRAG, "Verzugszinsen"),
            ("Pauschale", BETRAG, "Verzugspauschale nach § 288 Abs. 5 BGB"),
            ("Gesamt", BETRAG, "Geforderter Betrag"),
            ("PDF", TEXT, "Pfad des Schreibens in diesem Datenpaket"),
            ("PDF SHA-256", TEXT, "Prüfsumme der Datei"),
        ],
        verweise=[("Rechnungsnummer", "Rechnungsausgang")],
    )
    for m in mahnungen.order_by("datum", "pk"):
        mahntabelle.zeilen.append(
            [m.rechnung.nummer, m.bezeichnung, m.datum, m.frist, m.offen]
            + [m.gebuehr, m.zinsen, m.pauschale, m.gesamt, m.datei, m.sha256]
        )
        belege.append(m.datei)

    eingangstabelle = Tabelle(
        "eingangsrechnungen.csv",
        "Eingangsrechnungen",
        "Empfangene E-Rechnungen mit Rechnungsdatum im Zeitraum, im Original",
        [
            ("Rechnungsnummer", TEXT, "Nummer des Lieferanten"),
            ("Rechnungsdatum", DATUM, ""),
            ("Faellig am", DATUM, "Fälligkeit laut Rechnung"),
            ("Lieferant", TEXT, "Name laut Rechnung"),
            ("USt-IdNr", TEXT, "USt-IdNr. des Lieferanten laut Rechnung"),
            ("Kundennummer", TEXT, "Adresse des Lieferanten in Kontorfreund"),
            ("Waehrung", TEXT, "Währung"),
            ("Brutto", BETRAG, "Gesamtbetrag"),
            ("Zahlbetrag", BETRAG, ""),
            ("Format", TEXT, "XML-Datei (XRechnung) oder PDF mit eingebetteter XML"),
            ("Datei", TEXT, "Pfad des Originals in diesem Datenpaket"),
            ("SHA-256", TEXT, "Prüfsumme des Originals seit dem Empfang"),
        ],
        verweise=[("Kundennummer", "Adressen")],
    )
    for e in eingang.order_by("datum", "pk"):
        eingangstabelle.zeilen.append(
            [e.nummer, e.datum, e.faellig, e.lieferant, e.ust_id]
            + [e.kontakt.kundennummer if e.kontakt else "", e.waehrung, e.brutto]
            + [e.zahlbetrag, e.get_format_display(), e.datei, e.sha256]
        )
        belege.append(e.datei)

    alttabelle = Tabelle(
        "altbelege.csv",
        "Altbelege",
        "Rechnungen, Stornos und Gutschriften aus dem früheren Programm, als "
        "unverändertes PDF übernommen; Netto und Umsatzsteuer sind nicht erfasst",
        [
            ("Belegnummer", TEXT, ""),
            ("Datum", DATUM, ""),
            ("Art", TEXT, "Rechnung, Stornorechnung oder Gutschrift"),
            ("Zu Rechnung", TEXT, ""),
            ("Kundennummer", TEXT, ""),
            ("Empfaenger", TEXT, "Empfänger wie gedruckt, erste Zeile"),
            ("Brutto", BETRAG, "Gedruckter Gesamtbetrag"),
            ("Quelle", TEXT, "Früheres Programm"),
            ("Originaldatei", TEXT, "Dateiname im früheren Programm"),
            ("PDF", TEXT, "Pfad des Belegs in diesem Datenpaket"),
            ("PDF SHA-256", TEXT, "Prüfsumme seit der Übernahme"),
        ],
        verweise=[("Kundennummer", "Adressen")],
    )
    for a in altbelege.order_by("datum", "nummer"):
        alttabelle.zeilen.append(
            [a.nummer, a.datum, a.get_art_display(), a.bezug]
            + [a.kontakt.kundennummer if a.kontakt else ""]
            + [a.empfaenger.split("\n")[0], a.betrag, a.quelle, a.originalname]
            + [a.datei, a.sha256]
        )
        belege.append(a.datei)

    kontakte = {r.kontakt for r in rechnungen if r.kontakt}
    kontakte |= {e.kontakt for e in eingang if e.kontakt}
    kontakte |= {a.kontakt for a in altbelege if a.kontakt}
    adressen = Tabelle(
        "adressen.csv",
        "Adressen",
        "Kunden und Lieferanten, die in den übrigen Tabellen vorkommen, Stand heute",
        [
            ("Kundennummer", TEXT, ""),
            ("Name", TEXT, ""),
            ("Namenszusatz", TEXT, ""),
            ("Strasse", TEXT, "Straße und Hausnummer"),
            ("PLZ", TEXT, ""),
            ("Ort", TEXT, ""),
            ("Land", TEXT, ""),
            ("USt-IdNr", TEXT, "USt-IdNr."),
            ("Kategorie", TEXT, "Kunde, Interessent oder Lieferant"),
        ],
        [
            [k.kundennummer, k.anzeigename, k.zusatz, k.strasse, k.plz, k.ort]
            + [k.land, k.ust_id, k.get_kategorie_display()]
            for k in sorted(kontakte, key=lambda k: k.nummer)
        ],
        schluessel=1,
        zeitraum=False,
    )
    return [
        ausgang,
        positionen,
        zahlungstabelle,
        mahntabelle,
        eingangstabelle,
        alttabelle,
        adressen,
    ], belege


def _x(text):
    return escape(str(text))


def index_xml(alle, von, bis, jetzt):
    """Beschreibung des Datenpakets; Elemente in der Reihenfolge der DTD."""
    firma = Firmendaten.laden()
    kommentar = (
        f"Datenträgerüberlassung nach § 147 Abs. 6 AO für {von:%d.%m.%Y} bis "
        f"{bis:%d.%m.%Y}, erstellt am {jetzt:%d.%m.%Y um %H:%M} Uhr mit Kontorfreund "
        f"{settings.VERSION}"
        + (f". Steuernummer {firma.steuernummer}" if firma.steuernummer else "")
    )
    z = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<!DOCTYPE DataSet SYSTEM "{DTD.name}">',
        "<DataSet>",
        "  <Version>1.0</Version>",
        "  <DataSupplier>",
        f"    <Name>{_x(firma.name)}</Name>",
        f"    <Location>{_x(f'{firma.plz} {firma.ort}'.strip())}</Location>",
        f"    <Comment>{_x(kommentar)}</Comment>",
        "  </DataSupplier>",
        "  <Media>",
        "    <Name>Datenpaket 1</Name>",
    ]
    for t in alle:
        z += [
            "    <Table>",
            f"      <URL>{t.datei}</URL>",
            f"      <Name>{t.name}</Name>",
            f"      <Description>{_x(t.beschreibung)}</Description>",
        ]
        if t.zeitraum:
            z += [
                "      <Validity>",
                "        <Range>",
                f"          <From>{von:%d.%m.%Y}</From>",
                f"          <To>{bis:%d.%m.%Y}</To>",
                "        </Range>",
                "        <Format>DD.MM.YYYY</Format>",
                "      </Validity>",
            ]
        z += [
            "      <UTF8/>",
            "      <DecimalSymbol>,</DecimalSymbol>",
            "      <DigitGroupingSymbol>.</DigitGroupingSymbol>",
            # Die erste Zeile trägt die Spaltennamen.
            "      <Range>",
            "        <From>2</From>",
            "      </Range>",
            "      <VariableLength>",
            "        <ColumnDelimiter>;</ColumnDelimiter>",
            "        <RecordDelimiter>&#13;&#10;</RecordDelimiter>",
            "        <TextEncapsulator>&quot;</TextEncapsulator>",
        ]
        for nr, (name, art, erlaeuterung) in enumerate(t.spalten):
            element = "VariablePrimaryKey" if nr < t.schluessel else "VariableColumn"
            z += [f"        <{element}>", f"          <Name>{_x(name)}</Name>"]
            if erlaeuterung:
                z.append(f"          <Description>{_x(erlaeuterung)}</Description>")
            z += [f"          {TYP[art]}", f"        </{element}>"]
        for spalte, ziel in t.verweise:
            z += [
                "        <ForeignKey>",
                f"          <Name>{_x(spalte)}</Name>",
                f"          <References>{_x(ziel)}</References>",
                "        </ForeignKey>",
            ]
        z += ["      </VariableLength>", "    </Table>"]
    z += ["  </Media>", "</DataSet>", ""]
    return "\n".join(z).encode("utf-8")


def paket(von, bis, jetzt):
    """Das Datenpaket als temporäre Datei, zurückgespult; fehlende Belege fehlen darin."""
    alle, belege = tabellen(von, bis)
    datei = tempfile.TemporaryFile()
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.xml", index_xml(alle, von, bis, jetzt))
        z.write(DTD, DTD.name)
        for t in alle:
            z.writestr(t.datei, csv_inhalt(t))
        for pfad in belege:
            quelle = Path(settings.DATA_DIR) / pfad
            if quelle.is_file():
                z.write(quelle, pfad)
    datei.seek(0)
    return datei
