"""DATEV-Export als Buchungsstapel (Spezifikation M-4)."""

import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse

from archive.models import Altbeleg
from auswertungen import datev
from auswertungen.models import Datev
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from konten.models import Benutzer

pytestmark = pytest.mark.django_db

# Eine Stornorechnung trägt immer das heutige Datum; alle Belege richten sich danach.
HEUTE = date.today()
JAHR = HEUTE.year


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


@pytest.fixture
def eingestellt():
    e = Datev.laden()
    e.beraternummer = 1001
    e.mandantennummer = 7
    e.save()
    return e


def schreiben(client, kunde, steuerfall="kleinunternehmer"):
    """Festgeschriebene Rechnung von heute über 1.000 € netto (12,5 Std. × 80 €)."""
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": HEUTE.isoformat(),
            "leistung_von": HEUTE.isoformat(),
            "zahlungsziel": "14",
            "steuerfall": steuerfall,
            "kopftext": "Sehr geehrte Damen und Herren,",
            "fusstext": "Mit freundlichen Grüßen",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["12,5"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    return Rechnung.objects.latest("pk")


@pytest.fixture
def belege(client, firma, kunde):
    """Kleinunternehmer-Rechnung samt Storno und eine Rechnung mit 19 %."""
    klein = schreiben(client, kunde)
    client.post(reverse("invoicing:stornieren", args=[klein.pk]))
    storno = Rechnung.objects.get(storno_zu=klein)
    regel = schreiben(client, kunde, "regel")
    return klein, storno, regel


def test_felder_nach_formatversion_13():
    assert len(datev.FELDER) == 125
    assert len(set(datev.FELDER)) == 125
    assert datev.FELDER[:2] == ["Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen"]
    assert datev.FELDER[6:11] == [
        "Konto",
        "Gegenkonto (ohne BU-Schlüssel)",
        "BU-Schlüssel",
        "Belegdatum",
        "Belegfeld 1",
    ]
    assert datev.FELDER[13] == "Buchungstext"
    assert datev.FELDER[113:115] == ["Festschreibung", "Leistungsdatum"]
    assert datev.FELDER[-1] == "Abw. Skontokonto"


def test_datei(belege, eingestellt):
    klein, storno, regel = belege
    buchungen = datev.buchungen(date(JAHR, 1, 1), date(JAHR, 12, 31), eingestellt)
    inhalt = datev.datei(
        eingestellt,
        date(JAHR, 1, 1),
        date(JAHR, 12, 31),
        f"Rechnungsausgang {JAHR}",
        buchungen,
        datetime(JAHR, 3, 4, 5, 6, 7, 890000),
    )
    assert "Bäckerei".encode("cp1252") in inhalt
    assert inhalt.endswith(b"\r\n")
    kopf, namen, *zeilen = inhalt.decode("cp1252").split("\r\n")[:-1]

    kopf = kopf.split(";")
    assert len(kopf) == 31
    assert kopf[:6] == [
        '"EXTF"',
        "700",
        "21",
        '"Buchungsstapel"',
        "13",
        f"{JAHR}0304050607890",
    ]
    assert kopf[10:16] == [
        "1001",
        "7",
        f"{JAHR}0101",
        "4",
        f"{JAHR}0101",
        f"{JAHR}1231",
    ]
    assert kopf[16] == f'"Rechnungsausgang {JAHR}"'
    assert (kopf[20], kopf[21], kopf[26]) == ("0", '"EUR"', '"03"')
    assert namen.split(";") == datev.FELDER

    zeilen = [z.split(";") for z in zeilen]
    assert all(len(z) == 125 for z in zeilen)
    tag = f"{HEUTE:%d%m}"
    leistung = f"{HEUTE:%d%m%Y}"
    assert [(z[0], z[1], z[6], z[7], z[9], z[10], z[13], z[114]) for z in zeilen] == [
        (
            "1000,00",
            '"S"',
            "10001",
            "8195",
            tag,
            f'"{klein.nummer}"',
            '"Bäckerei Korn"',
            leistung,
        ),
        (
            "1000,00",
            '"H"',
            "10001",
            "8195",
            tag,
            f'"{storno.nummer}"',
            '"Stornorechnung Bäckerei Korn"',
            leistung,
        ),
        (
            "1190,00",
            '"S"',
            "10001",
            "8400",
            tag,
            f'"{regel.nummer}"',
            '"Bäckerei Korn"',
            leistung,
        ),
    ]


def test_skr04_sammelkonto_und_eigene_erloeskonten(belege, eingestellt):
    eingestellt.kontenrahmen = Datev.Kontenrahmen.SKR04
    eingestellt.debitoren = Datev.Debitoren.SAMMELKONTO
    eingestellt.sammelkonto = 12000
    eingestellt.erloes_regel = 4401
    eingestellt.save()
    buchungen = datev.buchungen(date(JAHR, 1, 1), date(JAHR, 12, 31), eingestellt)
    assert [(b.konto, b.gegenkonto) for b in buchungen] == [
        (12000, 4185),
        (12000, 4185),
        (12000, 4401),
    ]
    assert eingestellt.erloeskonto(Rechnung.Steuerfall.UMKEHR) == 4337


def test_seite_ohne_beraternummer(client, belege):
    url = reverse("auswertungen:datev")
    seite = client.get(url, {"jahr": str(JAHR)}).content.decode()
    for text in [
        "fehlen noch Berater- und Mandantennummer",
        reverse("auswertungen:datev_einstellungen"),
        "Stornorechnung",
        "Haben",
        "1.190,00 €",
        "3 Buchungen",
        "SKR 03",
    ]:
        assert text in seite, text
    assert "format=csv" not in seite
    antwort = client.get(url, {"jahr": str(JAHR), "format": "csv"})
    assert antwort["Content-Type"].startswith("text/html")


def test_herunterladen(client, belege, eingestellt):
    url = reverse("auswertungen:datev")
    seite = client.get(url, {"jahr": str(JAHR)}).content.decode()
    assert "format=csv" in seite and "format=zip" in seite

    csv = client.get(url, {"jahr": str(JAHR), "format": "csv"})
    assert csv["Content-Type"] == "text/csv; charset=windows-1252"
    assert csv["Content-Disposition"] == (
        f'attachment; filename="EXTF_Buchungsstapel_{JAHR}.csv"'
    )
    assert csv.content.startswith(b'"EXTF";700;21;')

    antwort = client.get(url, {"jahr": str(JAHR), "format": "zip"})
    archiv = zipfile.ZipFile(BytesIO(antwort.content))
    klein = belege[0]
    assert archiv.namelist()[0] == f"EXTF_Buchungsstapel_{JAHR}.csv"
    assert f"Rechnungen/Rechnung-{klein.nummer}.pdf" in archiv.namelist()
    assert len(archiv.namelist()) == 4
    assert archiv.read(f"Rechnungen/Rechnung-{klein.nummer}.pdf").startswith(b"%PDF")


def test_altbelege_fehlen(client, firma, kunde, eingestellt):
    Altbeleg.objects.create(
        art="rechnung",
        nummer=f"{JAHR}-007",
        datum=date(JAHR, 1, 1),
        kontakt=kunde,
        betrag=Decimal("99.00"),
        datei=f"archiv/altbelege/{JAHR}-007.pdf",
        sha256="0" * 64,
        originalname="alt.pdf",
    )
    schreiben(client, kunde)
    seite = client.get(
        reverse("auswertungen:datev"), {"jahr": str(JAHR)}
    ).content.decode()
    assert "1 Buchung ·" in seite
    assert "1 Beleg aus Ihrem bisherigen Programm fehlt" in seite


def test_einstellungen(client):
    url = reverse("auswertungen:datev_einstellungen")
    falsch = client.post(url, {"beraternummer": "12", "kontenrahmen": "03"})
    assert falsch.status_code == 200
    assert not Datev.laden().bereit

    client.post(
        url,
        {
            "beraternummer": "29098",
            "mandantennummer": "55003",
            "kontenrahmen": "04",
            "debitoren": "kunde",
            "sammelkonto": "10000",
            "erloes_kleinunternehmer": "",
            "erloes_regel": "",
            "erloes_13b": "",
        },
    )
    e = Datev.laden()
    assert (e.beraternummer, e.mandantennummer, e.kontenrahmen) == (29098, 55003, "04")
    assert e.bereit


def test_nur_fuer_den_inhaber(client):
    anna = Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    client.force_login(anna)
    assert client.get(reverse("auswertungen:datev_einstellungen")).status_code == 403
    seite = client.get(reverse("auswertungen:datev")).content.decode()
    assert "der Inhaber trägt sie ein" in seite
