"""Rechnungsausgangsbuch mit Export als CSV, XLSX und ODS (Spezifikation M-5)."""

import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from archive.models import Altbeleg
from auswertungen import buch, tabelle
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from zahlungen.models import Zahlung

pytestmark = pytest.mark.django_db

# Eine Stornorechnung trägt immer das heutige Datum; alle Belege richten sich danach.
HEUTE = date.today()
JAHR = HEUTE.year

ODS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.iban = "DE02120300000000202051"
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )


def schreiben(client, kunde, datum, aktion="festschreiben"):
    """Rechnung über 1.000 € (12,5 Std. × 80 €) als Kleinunternehmer."""
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": datum,
            "leistung_von": datum,
            "zahlungsziel": "14",
            "steuerfall": "kleinunternehmer",
            "kopftext": "Sehr geehrte Damen und Herren,",
            "fusstext": "Mit freundlichen Grüßen",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["12,5"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": aktion,
        },
    )
    return Rechnung.objects.latest("pk")


@pytest.fixture
def belege(client, firma, kunde):
    """Heute: teilbezahlte Rechnung, stornierte Rechnung samt Storno; dazu ein
    Entwurf, eine Rechnung vom Vorjahr und zwei Altbelege vom 1. Januar."""
    teilbezahlt = schreiben(client, kunde, HEUTE.isoformat())
    Zahlung.objects.create(rechnung=teilbezahlt, datum=HEUTE, betrag=Decimal("400.00"))
    storniert = schreiben(client, kunde, HEUTE.isoformat())
    client.post(reverse("invoicing:stornieren", args=[storniert.pk]))
    storno = Rechnung.objects.get(storno_zu=storniert)
    schreiben(client, kunde, HEUTE.isoformat(), aktion="speichern")
    schreiben(client, kunde, f"{JAHR - 1}-12-30")
    for art, nummer in [("rechnung", f"{JAHR}-007"), ("angebot", f"A-{JAHR}-003")]:
        Altbeleg.objects.create(
            art=art,
            nummer=nummer,
            datum=date(JAHR, 1, 1),
            kontakt=kunde,
            betrag=Decimal("99.00"),
            datei=f"archiv/altbelege/{nummer}.pdf",
            sha256=nummer.ljust(64, "0"),
            originalname=f"{nummer}.pdf",
        )
    return teilbezahlt, storniert, storno


def test_buch_eines_jahres(belege):
    teilbezahlt, storniert, storno = belege
    von, bis, name, text = buch.zeitraum(JAHR, "")
    assert (von, bis, name, text) == (
        date(JAHR, 1, 1),
        date(JAHR, 12, 31),
        str(JAHR),
        f"im Jahr {JAHR}",
    )
    zeilen = [z for z, _ in buch.zeilen(von, bis)]
    assert [(z.nummer, z.art) for z in zeilen] == [
        (f"{JAHR}-007", "Rechnung"),
        (teilbezahlt.nummer, "Rechnung"),
        (storniert.nummer, "Rechnung"),
        (storno.nummer, "Stornorechnung"),
    ]
    alt, offen, original, gegen = zeilen
    assert (alt.quelle, alt.brutto, alt.netto, alt.stand) == (
        "Altprogramm",
        Decimal("99.00"),
        None,
        "",
    )
    assert (offen.kunde, offen.kundennummer, offen.steuer) == (
        "Bäckerei Korn",
        "K-0001",
        "§ 19 UStG",
    )
    assert (offen.bezahlt, offen.bezahlt_am, offen.offen, offen.stand) == (
        Decimal("400.00"),
        HEUTE,
        Decimal("600.00"),
        "teilbezahlt",
    )
    assert original.stand == "storniert"
    assert (gegen.bezug, gegen.brutto, gegen.offen) == (
        storniert.nummer,
        Decimal("-1000.00"),
        None,
    )
    assert buch.summen(zeilen) == {
        "netto": Decimal("1000.00"),
        "ust": Decimal("0.00"),
        "brutto": Decimal("1099.00"),
        "bezahlt": Decimal("400.00"),
        "offen": Decimal("600.00"),
    }


@pytest.mark.parametrize(
    ("jahr", "wahl", "von", "bis"),
    [
        (2026, "", date(2026, 1, 1), date(2026, 12, 31)),
        (2026, "q3", date(2026, 7, 1), date(2026, 9, 30)),
        (2028, "2", date(2028, 2, 1), date(2028, 2, 29)),
    ],
)
def test_zeitraeume(jahr, wahl, von, bis):
    assert buch.zeitraum(jahr, wahl)[:2] == (von, bis)
    assert buch.zeitraum(2026, "10")[2:] == ("2026-10", "im Oktober 2026")
    assert buch.zeitraum(2026, "q3")[2:] == ("2026-Q3", "im 3. Quartal 2026")


def test_seite(client, belege):
    teilbezahlt = belege[0]
    seite = client.get(
        reverse("auswertungen:rechnungsausgangsbuch"), {"jahr": str(JAHR)}
    ).content.decode()
    for text in [
        f"Alle Rechnungen, Stornos und Korrekturen im Jahr {JAHR}",
        reverse("invoicing:bearbeiten", args=[teilbezahlt.pk]),
        "Stornorechnung zu",
        "teilbezahlt",
        f"zuletzt {HEUTE:%d.%m.%Y}",
        "1.099,00 €",
        "4 Belege",
        "mit dem gedruckten Betrag",
        "format=xlsx",
    ]:
        assert text in seite, text
    leer = client.get(
        reverse("auswertungen:rechnungsausgangsbuch"), {"jahr": str(JAHR - 3)}
    ).content.decode()
    assert f"Keine Rechnungen im Jahr {JAHR - 3}" in leer


def _laden(client, endung):
    antwort = client.get(
        reverse("auswertungen:rechnungsausgangsbuch"),
        {"jahr": str(JAHR), "format": endung},
    )
    assert antwort["Content-Disposition"] == (
        f'attachment; filename="Rechnungsausgangsbuch {JAHR}.{endung}"'
    )
    return antwort.content


def test_csv(client, belege):
    inhalt = _laden(client, "csv")
    assert inhalt.startswith(b"\xef\xbb\xbf")
    zeilen = inhalt.decode("utf-8-sig").splitlines()
    assert zeilen[0].startswith("Datum;Nummer;Art;Zu Rechnung;Kundennummer;Kunde;")
    assert zeilen[2].startswith(
        f"{HEUTE:%d.%m.%Y};{belege[0].nummer};Rechnung;;K-0001;Bäckerei Korn;"
        f"§ 19 UStG;1000,00;0,00;1000,00;400,00;{HEUTE:%d.%m.%Y};600,00;teilbezahlt;"
        "Kontorfreund"
    )
    assert zeilen[-1] == ";Summe;;;;;;1000,00;0,00;1099,00;400,00;;600,00;;"


def test_xlsx(client, belege):
    blatt = load_workbook(BytesIO(_laden(client, "xlsx"))).active
    assert blatt.title == f"Rechnungsausgangsbuch {JAHR}"
    assert blatt["A1"].value == "Datum"
    assert blatt["A3"].value == datetime(JAHR, HEUTE.month, HEUTE.day)
    assert blatt["A3"].number_format == "DD.MM.YYYY"
    assert blatt["J3"].value == 1000
    assert blatt["J3"].number_format == "#,##0.00"
    assert blatt["B6"].value == "Summe"
    assert blatt["J6"].value == 1099


def test_ods(client, belege):
    archiv = zipfile.ZipFile(BytesIO(_laden(client, "ods")))
    erste = archiv.infolist()[0]
    assert (erste.filename, erste.compress_type) == ("mimetype", zipfile.ZIP_STORED)
    assert archiv.read("mimetype") == b"application/vnd.oasis.opendocument.spreadsheet"
    inhalt = ElementTree.fromstring(archiv.read("content.xml"))  # noqa: S314 – selbst erzeugt
    zeilen = inhalt.findall(".//table:table-row", ODS)
    assert len(zeilen) == 6
    zellen = zeilen[2].findall("table:table-cell", ODS)
    datum = f"{{{ODS['office']}}}date-value"
    wert = f"{{{ODS['office']}}}value"
    assert zellen[0].get(datum) == HEUTE.isoformat()
    assert zellen[9].get(wert) == "1000.00"
    assert zeilen[-1].findall("table:table-cell", ODS)[9].get(wert) == "1099.00"


def test_text_wird_keine_formel(client, firma):
    """Ein Name wie aus einer präparierten E-Rechnung bleibt in Excel reiner Text."""
    name = '=HYPERLINK("https://example.com","Klick")'
    kunde = Kontakt.objects.create(
        firmenname=name, strasse="Markt 3", plz="55116", ort="Mainz"
    )
    schreiben(client, kunde, HEUTE.isoformat())

    blatt = load_workbook(BytesIO(_laden(client, "xlsx"))).active
    assert (blatt["F2"].value, blatt["F2"].data_type) == (name, "s")
    zeile = _laden(client, "csv").decode("utf-8-sig").splitlines()[1]
    assert ';"\'=HYPERLINK(""https://example.com"",""Klick"")";' in zeile


def test_telefonnummer_bleibt_im_csv_wie_sie_ist():
    """Nur Ziffern und Rechenzeichen rufen nichts auf und brauchen kein Hochkomma."""
    werte = ["+49 6131 12345", "-", "+49 HYPERLINK", "-2+3+cmd|' /C calc'!A0"]
    inhalt = tabelle.csv([("Telefon", "text")], [[w] for w in werte])
    assert inhalt.decode("utf-8-sig").splitlines()[1:] == [
        "+49 6131 12345",
        "-",
        "'+49 HYPERLINK",
        "'-2+3+cmd|' /C calc'!A0",
    ]


def test_in_der_seitenleiste(client):
    seite = client.get(reverse("core:start")).content.decode()
    assert reverse("auswertungen:rechnungsausgangsbuch") in seite
