"""Tabellen aus CSV, XLSX und ODS lesen (Spezifikation M-6).

Ergebnis sind die Spaltentitel aus der ersten nicht leeren Zeile und die
übrigen Zeilen als Text, jede mit ihrer Nummer in der Datei, damit der Bericht
dieselbe Zeile nennt wie Excel oder LibreOffice. Leere Zeilen fallen weg,
leere Spalten am Ende auch. Zahlen aus Excel und LibreOffice kommen in
deutscher Schreibweise wie in Kontorfreunds eigenen Exporten („12,5“), Daten als
TT.MM.JJJJ. CSV liest UTF-8 (mit oder ohne BOM), UTF-16 und sonst
Windows-1252; Trennzeichen ist, was in der ersten Zeile am häufigsten
vorkommt: Semikolon, Tabulator oder Komma. Das Hochkomma, mit dem Kontorfreund
im CSV Formeln entschärft, fällt beim Lesen wieder weg.

XLSX und ODS sind ZIP-Archive mit XML. Vor dem Lesen begrenzt das Programm die
entpackte Größe und lehnt XML mit Dokumenttyp-Definition ab; ohne sie gibt es
keine Entitäten, mit denen eine Datei den Rechner lahmlegen könnte.
"""

import csv
import warnings
import zipfile
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from xml.etree import ElementTree
from xml.parsers import expat

from openpyxl import load_workbook

from auswertungen.tabelle import FORMEL

GROESSTE_DATEI = 10 * 1024 * 1024
ENTPACKT = 100 * 1024 * 1024
ZEILEN = 10_000
SPALTEN = 100

ODS_TYP = b"application/vnd.oasis.opendocument.spreadsheet"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class Unlesbar(Exception):
    """Die Datei lässt sich nicht als Tabelle lesen; der Text ist für den Nutzer."""


def lesen(inhalt):
    """(Spaltentitel, [[Zeilennummer, Werte], …]) aus einer CSV-, XLSX- oder ODS-Datei."""
    if inhalt.startswith(b"PK"):
        return _aufbereiten(_zip(inhalt))
    if inhalt.startswith(b"\xd0\xcf\x11\xe0"):
        raise Unlesbar(
            "Das alte Excel-Format (.xls) kann Kontorfreund nicht lesen. Bitte speichern "
            "Sie die Datei in Excel unter „Speichern unter“ als Excel-Arbeitsmappe (.xlsx)."
        )
    return _aufbereiten(_csv(inhalt))


def _aufbereiten(zeilen):
    kopf, daten = None, []
    for nr, werte in zeilen:
        werte = [w.replace("\r\n", "\n").strip() for w in werte]
        if not any(werte):
            continue
        if kopf is None:
            kopf = werte
            continue
        if len(daten) == ZEILEN:
            raise Unlesbar(
                f"Die Datei hat mehr als {ZEILEN:,} Zeilen. Bitte teilen Sie sie auf.".replace(
                    ",", "."
                )
            )
        daten.append([nr, werte])
    if kopf is None:
        raise Unlesbar("Die Datei ist leer.")
    if not daten:
        raise Unlesbar("Unter den Spaltenüberschriften stehen keine Zeilen.")
    breite = 0
    for werte in [kopf] + [w for _, w in daten]:
        breite = max(breite, max((i + 1 for i, w in enumerate(werte) if w), default=0))
    if breite > SPALTEN:
        raise Unlesbar(f"Die Tabelle hat mehr als {SPALTEN} Spalten.")
    spalten = _titel((kopf + [""] * breite)[:breite])
    return spalten, [[nr, (w + [""] * breite)[:breite]] for nr, w in daten]


def _titel(kopf):
    """Eindeutige Spaltentitel; leere heißen „Spalte 3“."""
    titel = []
    for i, name in enumerate(kopf, start=1):
        name = " ".join(name.split())[:100] or f"Spalte {i}"
        basis, n = name, 2
        while name in titel:
            name, n = f"{basis} ({n})", n + 1
        titel.append(name)
    return titel


def _zahl(wert):
    text = format(wert, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _datum(wert):
    if isinstance(wert, datetime) and wert.time() != time():
        return f"{wert:%d.%m.%Y %H:%M}"
    return f"{wert:%d.%m.%Y}"


# ---------- CSV ----------


def _csv(inhalt):
    try:
        if inhalt.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = inhalt.decode("utf-16")
        else:
            text = inhalt.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = inhalt.decode("cp1252", errors="replace")
    if "\x00" in text:
        raise Unlesbar(
            "Die Datei ist weder eine CSV-Datei noch eine Tabelle aus Excel oder LibreOffice."
        )
    erste = next((z for z in text.splitlines() if z.strip()), "")
    # Bei Gleichstand gewinnt das Semikolon, wie bei Excel in Deutschland.
    trenner = max(";\t,", key=erste.count)
    try:
        for nr, zeile in enumerate(
            csv.reader(StringIO(text, newline=""), delimiter=trenner), start=1
        ):
            yield nr, [_ohne_schutz(w) for w in zeile]
    except csv.Error as fehler:
        raise Unlesbar(f"Die CSV-Datei lässt sich nicht lesen ({fehler}).") from fehler


def _ohne_schutz(wert):
    return wert[1:] if wert.startswith("'") and wert[1:].startswith(FORMEL) else wert


# ---------- XLSX und ODS ----------


class _Fertig(Exception):
    pass


def _dtd(*_):
    raise Unlesbar(
        "Die Datei enthält eine Dokumenttyp-Definition und wird nicht gelesen."
    )


def _ende(*_):
    raise _Fertig


def _ohne_dtd(xml):
    """Eine Dokumenttyp-Definition steht vor dem ersten Element; danach endet die Prüfung."""
    pruefer = expat.ParserCreate()
    pruefer.StartDoctypeDeclHandler = _dtd
    pruefer.EntityDeclHandler = _dtd
    pruefer.StartElementHandler = _ende
    try:
        pruefer.Parse(xml, True)
    except _Fertig:
        return
    except expat.ExpatError as fehler:
        raise Unlesbar("Die Datei ist beschädigt.") from fehler


def _zip(inhalt):
    try:
        archiv = zipfile.ZipFile(BytesIO(inhalt))
        teile = archiv.infolist()
        if sum(t.file_size for t in teile) > ENTPACKT:
            raise Unlesbar("Die Datei ist entpackt größer als 100 MB.")
        namen = {t.filename for t in teile}
        if "mimetype" in namen and archiv.read("mimetype").strip() == ODS_TYP:
            xml = archiv.read("content.xml")
            _ohne_dtd(xml)
            return _ods(xml)
        if "xl/workbook.xml" in namen:
            for teil in teile:
                if teil.filename.endswith((".xml", ".rels")):
                    _ohne_dtd(archiv.read(teil))
            return _xlsx(inhalt)
    except (zipfile.BadZipFile, KeyError, OSError) as fehler:
        raise Unlesbar("Die Datei ist beschädigt.") from fehler
    raise Unlesbar("Die Datei ist weder eine Tabelle aus Excel noch aus LibreOffice.")


def _xlsx(inhalt):
    try:
        with warnings.catch_warnings():
            # openpyxl warnt bei Dateien anderer Programme etwa vor fehlenden Formaten.
            warnings.simplefilter("ignore")
            mappe = load_workbook(BytesIO(inhalt), read_only=True, data_only=True)
        blatt = mappe.worksheets[0]
        # Manche Programme tragen einen falschen Bereich ein; dann fehlten Zellen.
        blatt.reset_dimensions()
        for nr, werte in enumerate(blatt.iter_rows(values_only=True), start=1):
            yield nr, [_text(w) for w in werte]
    # openpyxl meldet beschädigte Dateien mit ganz unterschiedlichen Fehlern.
    except Exception as fehler:
        raise Unlesbar("Die Excel-Datei lässt sich nicht öffnen.") from fehler


def _text(wert):
    if wert is None:
        return ""
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, int | float):
        # repr ist bei float die kürzeste Schreibweise, die genau diesen Wert ergibt.
        return _zahl(Decimal(repr(wert)))
    if isinstance(wert, date):
        return _datum(wert)
    if isinstance(wert, time):
        return f"{wert:%H:%M}"
    return str(wert)


def _ods(xml):
    try:
        wurzel = ElementTree.fromstring(xml)  # noqa: S314 – ohne DTD, siehe _ohne_dtd
        tabelle = wurzel.find(f".//{TABLE}table")
        if tabelle is None:
            raise Unlesbar("Die Datei enthält keine Tabelle.")
        zeilen, nr = [], 0
        for zeile in tabelle.iter(f"{TABLE}table-row"):
            anzahl = int(zeile.get(f"{TABLE}number-rows-repeated", "1"))
            werte = _ods_zeile(zeile)
            if not any(werte):
                # LibreOffice schreibt die leeren Zeilen bis zum Ende des Blatts als eine.
                nr += anzahl
                continue
            for _ in range(min(anzahl, ZEILEN + 2)):
                nr += 1
                zeilen.append((nr, werte))
    except (ElementTree.ParseError, ValueError) as fehler:
        raise Unlesbar("Die LibreOffice-Datei ist beschädigt.") from fehler
    return zeilen


def _ods_zeile(zeile):
    werte, leer = [], 0
    for zelle in zeile:
        if zelle.tag not in (f"{TABLE}table-cell", f"{TABLE}covered-table-cell"):
            continue
        anzahl = int(zelle.get(f"{TABLE}number-columns-repeated", "1"))
        wert = _ods_wert(zelle)
        if not wert:
            leer += anzahl
            continue
        if len(werte) + leer + anzahl > SPALTEN:
            raise Unlesbar(f"Die Tabelle hat mehr als {SPALTEN} Spalten.")
        werte += [""] * leer + [wert] * anzahl
        leer = 0
    return werte


def _ods_wert(zelle):
    art = zelle.get(f"{OFFICE}value-type")
    try:
        if art in ("float", "percentage", "currency"):
            return _zahl(Decimal(zelle.get(f"{OFFICE}value")))
        if art == "date":
            return _datum(datetime.fromisoformat(zelle.get(f"{OFFICE}date-value")))
        if art == "boolean":
            return "ja" if zelle.get(f"{OFFICE}boolean-value") == "true" else "nein"
    except (TypeError, ValueError, InvalidOperation):
        pass
    # Nur die Absätze der Zelle selbst, nicht die eines Kommentars darin.
    return "\n".join(_ods_text(p) for p in zelle.findall(f"{TEXT}p"))


def _ods_text(element):
    teile = [element.text or ""]
    for kind in element:
        name = kind.tag.rpartition("}")[2]
        if name == "s":
            teile.append(" " * min(int(kind.get(f"{TEXT}c", "1")), 100))
        elif name == "tab":
            teile.append("\t")
        elif name == "line-break":
            teile.append("\n")
        elif name != "annotation":
            teile.append(_ods_text(kind))
        teile.append(kind.tail or "")
    return "".join(teile)
