"""Tabellen als CSV, XLSX und ODS (Spezifikation M-5).

Eine Tabelle sind Spalten (Titel, Art) mit der Art „text“, „datum“ oder „betrag“
und Zeilen mit passenden Werten (str, date, Decimal oder None für leer). CSV ist
so geschrieben, wie Excel und LibreOffice es in Deutschland öffnen: UTF-8 mit
BOM, Semikolon, Dezimalkomma. XLSX und ODS tragen echte Zahlen und Daten, mit
denen sich weiterrechnen lässt.
"""

import csv as csvmodul
import zipfile
from io import BytesIO, StringIO
from xml.sax.saxutils import escape, quoteattr

from openpyxl import Workbook
from openpyxl.styles import Font

from core.templatetags.kf import zahl

TYPEN = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
}


def _text(wert, art):
    if wert is None:
        return ""
    if art == "datum":
        return wert.strftime("%d.%m.%Y")
    if art == "betrag":
        return zahl(wert, 2)
    return str(wert)


def csv(spalten, zeilen):
    ausgabe = StringIO()
    schreiber = csvmodul.writer(ausgabe, delimiter=";")
    schreiber.writerow([titel for titel, _ in spalten])
    for zeile in zeilen:
        schreiber.writerow(
            [_text(wert, art) for wert, (_, art) in zip(zeile, spalten, strict=True)]
        )
    return ausgabe.getvalue().encode("utf-8-sig")


def xlsx(spalten, zeilen, name):
    mappe = Workbook()
    blatt = mappe.active
    blatt.title = name[:31]
    blatt.append([titel for titel, _ in spalten])
    for zelle in blatt[1]:
        zelle.font = Font(bold=True)
    for zeile in zeilen:
        blatt.append(zeile)
    formate = {"datum": "DD.MM.YYYY", "betrag": "#,##0.00"}
    for nr, (titel, art) in enumerate(spalten, start=1):
        buchstabe = blatt.cell(row=1, column=nr).column_letter
        blatt.column_dimensions[buchstabe].width = max(len(titel) + 2, 12)
        if art in formate:
            for (zelle,) in blatt.iter_rows(min_row=2, min_col=nr, max_col=nr):
                zelle.number_format = formate[art]
    blatt.freeze_panes = "A2"
    ausgabe = BytesIO()
    mappe.save(ausgabe)
    return ausgabe.getvalue()


ODS_KOPF = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:number="urn:oasis:names:tc:opendocument:xmlns:datastyle:1.0"
 xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 office:version="1.2">
<office:automatic-styles>
<number:date-style style:name="N1"><number:day number:style="long"/><number:text>.</number:text><number:month number:style="long"/><number:text>.</number:text><number:year number:style="long"/></number:date-style>
<number:number-style style:name="N2"><number:number number:decimal-places="2" number:min-decimal-places="2" number:min-integer-digits="1" number:grouping="true"/></number:number-style>
<style:style style:name="kopf" style:family="table-cell"><style:text-properties fo:font-weight="bold"/></style:style>
<style:style style:name="datum" style:family="table-cell" style:data-style-name="N1"/>
<style:style style:name="betrag" style:family="table-cell" style:data-style-name="N2"/>
</office:automatic-styles>
<office:body><office:spreadsheet>
"""
ODS_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
<manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>
<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""


def _ods_zelle(wert, art):
    if wert is None:
        return "<table:table-cell/>"
    text = f"<text:p>{escape(_text(wert, art))}</text:p>"
    if art == "datum":
        return (
            '<table:table-cell table:style-name="datum" office:value-type="date" '
            f'office:date-value="{wert.isoformat()}">{text}</table:table-cell>'
        )
    if art == "betrag":
        return (
            '<table:table-cell table:style-name="betrag" office:value-type="float" '
            f'office:value="{wert}">{text}</table:table-cell>'
        )
    return f'<table:table-cell office:value-type="string">{text}</table:table-cell>'


def ods(spalten, zeilen, name):
    teile = [ODS_KOPF, f"<table:table table:name={quoteattr(name)}>"]
    teile.append(
        "<table:table-row>"
        + "".join(
            '<table:table-cell table:style-name="kopf" office:value-type="string">'
            f"<text:p>{escape(titel)}</text:p></table:table-cell>"
            for titel, _ in spalten
        )
        + "</table:table-row>"
    )
    for zeile in zeilen:
        teile.append(
            "<table:table-row>"
            + "".join(
                _ods_zelle(wert, art)
                for wert, (_, art) in zip(zeile, spalten, strict=True)
            )
            + "</table:table-row>"
        )
    teile.append(
        "</table:table></office:spreadsheet></office:body></office:document-content>"
    )
    ausgabe = BytesIO()
    with zipfile.ZipFile(ausgabe, "w", zipfile.ZIP_DEFLATED) as archiv:
        # Der Typ steht als erste Datei unkomprimiert vorn (ODF 1.2, Abschnitt 3.3).
        archiv.writestr("mimetype", TYPEN["ods"], compress_type=zipfile.ZIP_STORED)
        archiv.writestr("META-INF/manifest.xml", ODS_MANIFEST)
        archiv.writestr("content.xml", "".join(teile))
    return ausgabe.getvalue()
