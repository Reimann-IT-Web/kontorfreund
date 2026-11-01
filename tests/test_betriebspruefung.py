"""Datenpaket für die Betriebsprüfung (Spezifikation D-6) – mit erfundenen Daten."""

import csv
import hashlib
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from lxml import etree

from archive.models import Altbeleg
from auswertungen import pruefer
from contacts.models import Kontakt
from core.models import Firmendaten
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from konten.models import Benutzer
from zahlungen.models import Mahnung, Zahlung

pytestmark = pytest.mark.django_db

HEUTE = date.today()
JAHR = HEUTE.year
# Die DTD von 2002 (Version 1.1), so wie sie die Finanzverwaltung verteilt.
DTD_SHA256 = "e93a716e8e022b8624b02f12b805f67c25e3fdd40fe422036f2abbea464e0b76"


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT & Web"
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


def schreiben(client, kunde, datum, beschreibung=""):
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
            "beschreibung": [beschreibung],
            "menge": ["12,5"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    return Rechnung.objects.latest("pk")


def ablegen(pfad, inhalt):
    ziel = Path(settings.DATA_DIR) / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return hashlib.sha256(inhalt).hexdigest()


@pytest.fixture
def daten(client, firma, kunde):
    """Im laufenden Jahr: teilbezahlte und gemahnte Rechnung, stornierte Rechnung samt
    Storno, eine Eingangsrechnung und ein Altbeleg; dazu Belege, die nicht hineingehören."""
    bezahlt = schreiben(
        client, kunde, HEUTE.isoformat(), beschreibung='Startseite;\nKontakt "neu"'
    )
    Zahlung.objects.create(rechnung=bezahlt, datum=HEUTE, betrag=Decimal("400.00"))
    Mahnung.objects.create(
        rechnung=bezahlt,
        stufe=1,
        datum=HEUTE,
        frist=HEUTE + timedelta(days=10),
        offen=Decimal("600.00"),
        gesamt=Decimal("600.00"),
        datei=f"archiv/mahnungen/{JAHR}/Zahlungserinnerung-{bezahlt.nummer}.pdf",
        sha256=ablegen(
            f"archiv/mahnungen/{JAHR}/Zahlungserinnerung-{bezahlt.nummer}.pdf",
            b"%PDF-1.4 Mahnung",
        ),
    )
    storniert = schreiben(client, kunde, HEUTE.isoformat())
    client.post(reverse("invoicing:stornieren", args=[storniert.pk]))
    storno = Rechnung.objects.get(storno_zu=storniert)
    vorjahr = schreiben(client, kunde, f"{JAHR - 1}-12-30")

    lieferant = Kontakt.objects.create(
        kategorie=Kontakt.Kategorie.LIEFERANT, firmenname="Druckerei Blatt"
    )
    Eingangsrechnung.objects.create(
        format=Eingangsrechnung.Format.XML,
        syntax="UBL",
        art="380",
        nummer="DB-77",
        datum=HEUTE,
        lieferant="Druckerei Blatt GmbH",
        ust_id="DE123456789",
        kontakt=lieferant,
        waehrung="EUR",
        brutto=Decimal("119.00"),
        zahlbetrag=Decimal("119.00"),
        datei=f"archiv/eingang/{JAHR}/abc-DB-77.xml",
        sha256=ablegen(f"archiv/eingang/{JAHR}/abc-DB-77.xml", b"<Invoice/>"),
        originalname="DB-77.xml",
    )
    for art, nummer in [("rechnung", f"{JAHR}-007"), ("angebot", f"A-{JAHR}-003")]:
        pfad = f"archiv/altbelege/{nummer}.pdf"
        Altbeleg.objects.create(
            art=art,
            nummer=nummer,
            datum=date(JAHR, 1, 1),
            kontakt=kunde,
            empfaenger="Bäckerei Korn\nMarkt 3",
            betrag=Decimal("99.00"),
            datei=pfad,
            sha256=ablegen(pfad, f"%PDF {nummer}".encode()),
            originalname=f"{nummer}.pdf",
        )
    return bezahlt, storniert, storno, vorjahr


def herunterladen(client, jahr=JAHR):
    antwort = client.get(
        reverse("auswertungen:betriebspruefung"), {"jahr": jahr, "format": "zip"}
    )
    assert antwort["Content-Type"] == "application/zip"
    return zipfile.ZipFile(BytesIO(b"".join(antwort.streaming_content)))


def lesen(paket, name):
    """Zeilen einer CSV-Datei des Pakets, die Kopfzeile zuerst."""
    roh = paket.read(name)
    assert not roh.startswith(b"\xef\xbb\xbf"), (
        "ohne BOM, sonst stimmt der erste Name nicht"
    )
    text = roh.decode("utf-8")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    return list(csv.reader(StringIO(text, newline=""), delimiter=";"))


def test_index_xml_gueltig_nach_der_dtd(client, daten, tmp_path):
    paket = herunterladen(client)
    paket.extractall(tmp_path / "paket")
    ordner = tmp_path / "paket"

    dtd = ordner / "gdpdu-01-08-2002.dtd"
    assert hashlib.sha256(dtd.read_bytes()).hexdigest() == DTD_SHA256
    baum = etree.parse(str(ordner / "index.xml"))
    assert baum.docinfo.system_url == "gdpdu-01-08-2002.dtd"
    pruefer_dtd = etree.DTD(str(dtd))
    assert pruefer_dtd.validate(baum), pruefer_dtd.error_log.filter_from_errors()

    namen = {}
    for tabelle in baum.iter("Table"):
        name = tabelle.findtext("Name")
        spalten = [
            s.findtext("Name")
            for s in tabelle.find("VariableLength")
            if s.tag in ("VariablePrimaryKey", "VariableColumn")
        ]
        schluessel = [s.findtext("Name") for s in tabelle.iter("VariablePrimaryKey")]
        namen[name] = (spalten, schluessel, tabelle)
        zeilen = lesen(paket, tabelle.findtext("URL"))
        assert zeilen[0] == spalten, name
        assert all(len(z) == len(spalten) for z in zeilen), name
        assert tabelle.findtext("Range/From") == "2"
        assert tabelle.find("UTF8") is not None
    assert list(namen) == [
        "Rechnungsausgang",
        "Rechnungspositionen",
        "Zahlungen",
        "Mahnungen",
        "Eingangsrechnungen",
        "Altbelege",
        "Adressen",
    ]
    # Fremdschlüssel heißen wie der Schlüssel der Tabelle, auf die sie verweisen.
    for name, (spalten, _, tabelle) in namen.items():
        for fk in tabelle.iter("ForeignKey"):
            assert fk.findtext("Name") in spalten, name
            assert namen[fk.findtext("References")][1] == [fk.findtext("Name")], name
    assert "Muster IT &amp; Web" in (ordner / "index.xml").read_text(encoding="utf-8")


def test_inhalt_des_pakets(client, daten):
    bezahlt, storniert, storno, vorjahr = daten
    paket = herunterladen(client)

    def tabelle(name):
        kopf, *zeilen = lesen(paket, name)
        return [dict(zip(kopf, z, strict=True)) for z in zeilen]

    ausgang = {z["Rechnungsnummer"]: z for z in tabelle("rechnungen.csv")}
    assert list(ausgang) == [bezahlt.nummer, storniert.nummer, storno.nummer]
    assert vorjahr.nummer not in ausgang
    r = ausgang[bezahlt.nummer]
    assert r["Rechnungsdatum"] == f"{HEUTE:%d.%m.%Y}"
    assert (r["Art"], r["Kundennummer"], r["Kunde"]) == (
        "Rechnung",
        "K-0001",
        "Bäckerei Korn",
    )
    assert (r["Umsatzsteuer"], r["Netto"], r["USt"], r["Brutto"]) == (
        "§ 19 UStG",
        "1000,00",
        "0,00",
        "1000,00",
    )
    assert r["Faellig am"] == f"{HEUTE + timedelta(days=14):%d.%m.%Y}"
    s = ausgang[storno.nummer]
    assert (s["Art"], s["Zu Rechnung"], s["Brutto"]) == (
        "Stornorechnung",
        storniert.nummer,
        "-1000,00",
    )
    # Die Belege liegen im Paket, unverändert seit dem Festschreiben
    assert hashlib.sha256(paket.read(r["PDF"])).hexdigest() == r["PDF SHA-256"]

    (position,) = [
        p for p in tabelle("positionen.csv") if p["Rechnungsnummer"] == bezahlt.nummer
    ]
    assert position["Beschreibung"] == 'Startseite; Kontakt "neu"'
    assert (position["Menge"], position["Einzelpreis"], position["Gesamt"]) == (
        "12,500",
        "80,00",
        "1000,00",
    )

    (zahlung,) = tabelle("zahlungen.csv")
    assert (zahlung["Rechnungsnummer"], zahlung["Art"], zahlung["Betrag"]) == (
        bezahlt.nummer,
        "Überweisung",
        "400,00",
    )
    (mahnung,) = tabelle("mahnungen.csv")
    assert (mahnung["Stufe"], mahnung["Offen"]) == ("Zahlungserinnerung", "600,00")
    assert paket.read(mahnung["PDF"]) == b"%PDF-1.4 Mahnung"

    (eingang,) = tabelle("eingangsrechnungen.csv")
    assert (eingang["Lieferant"], eingang["Kundennummer"], eingang["Brutto"]) == (
        "Druckerei Blatt GmbH",
        "K-0002",
        "119,00",
    )
    assert paket.read(eingang["Datei"]) == b"<Invoice/>"

    # Nur umsatzwirksame Altbelege, das Angebot nicht
    (alt,) = tabelle("altbelege.csv")
    assert (alt["Belegnummer"], alt["Empfaenger"], alt["Brutto"]) == (
        f"{JAHR}-007",
        "Bäckerei Korn",
        "99,00",
    )
    assert f"archiv/altbelege/A-{JAHR}-003.pdf" not in paket.namelist()

    adressen = tabelle("adressen.csv")
    assert [(a["Kundennummer"], a["Name"]) for a in adressen] == [
        ("K-0001", "Bäckerei Korn"),
        ("K-0002", "Druckerei Blatt"),
    ]


def test_seite(client, daten):
    seite = client.get(reverse("auswertungen:betriebspruefung"), {"jahr": JAHR}).text
    assert "Datenpaket herunterladen" in seite
    assert "Rechnungsausgang" in seite
    assert "gdpdu-01-08-2002.dtd" in seite
    assert "fehlt" not in seite

    altbeleg = Altbeleg.objects.get(art="rechnung")
    (Path(settings.DATA_DIR) / altbeleg.datei).unlink()
    seite = client.get(reverse("auswertungen:betriebspruefung"), {"jahr": JAHR}).text
    assert "1 Belegdatei fehlt in der Ablage und ist deshalb nicht im Paket" in seite
    assert altbeleg.datei not in herunterladen(client).namelist()


def test_leeres_jahr(client, firma):
    seite = client.get(reverse("auswertungen:betriebspruefung"), {"jahr": 2001}).text
    assert "Keine Daten im Jahr 2001" in seite
    assert "Datenpaket herunterladen" not in seite


def test_nur_fuer_den_inhaber(anonym, client):
    mitarbeiter = Benutzer.objects.create_user(
        "team@muster.test", name="Team", rolle=Benutzer.Rolle.MITARBEITER
    )
    anonym.force_login(mitarbeiter)
    assert anonym.get(reverse("auswertungen:betriebspruefung")).status_code == 403
    buch = anonym.get(reverse("auswertungen:rechnungsausgangsbuch")).text
    assert reverse("auswertungen:betriebspruefung") not in buch
    buch = client.get(reverse("auswertungen:rechnungsausgangsbuch")).text
    assert reverse("auswertungen:betriebspruefung") in buch


def test_dtd_unveraendert_im_programm():
    """Der Standard verlangt die DTD unverändert; Git darf die Zeilenenden nicht ändern."""
    roh = pruefer.DTD.read_bytes()
    assert hashlib.sha256(roh).hexdigest() == DTD_SHA256
    assert b"\r\n" in roh
