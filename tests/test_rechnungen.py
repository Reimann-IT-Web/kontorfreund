"""Rechnung schreiben, festschreiben und versenden – mit erfundenen Daten."""

import hashlib
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail.backends import locmem
from django.urls import reverse
from pypdf import PdfReader

from archive.models import Altbeleg
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import versand
from invoicing.beleg import leistungszeit
from invoicing.forms import dezimal
from invoicing.models import Position, Rechnung

pytestmark = pytest.mark.django_db


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.email = "post@muster.test"
    f.iban = "DE02120300000000202051"
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Muster Bäckerei GmbH",
        strasse="Lindenweg 4",
        plz="55116",
        ort="Mainz",
        email="buchhaltung@baeckerei.test",
    )


@pytest.fixture
def daten(tmp_path, settings):
    settings.DATA_DIR = tmp_path
    return tmp_path


def formular(kunde, aktion="festschreiben", **mehr):
    return {
        "kontakt": kunde.pk,
        "datum": "2026-10-29",
        "leistung_von": "2026-10-01",
        "leistung_bis": "2026-10-31",
        "zahlungsziel": "14",
        "steuerfall": "kleinunternehmer",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Mit freundlichen Grüßen",
        "girocode": "on",
        "bezeichnung": ["Webdesign", ""],
        "beschreibung": ["- Startseite\n- Galerie", ""],
        "menge": ["29,5", "1"],
        "einheit": ["Std.", "Stück"],
        "preis": ["80,00", ""],
        "aktion": aktion,
        **mehr,
    }


def test_nummer_schliesst_an_altbelege_an():
    for nummer in (
        "260006",
        "260007",
        "2600099",
    ):  # siebenstellig: anderer Nummernkreis
        Altbeleg.objects.create(
            art=Altbeleg.Art.RECHNUNG,
            nummer=nummer,
            datum=date(2026, 8, 15),
            absender="Muster IT",
            sha256=nummer.ljust(64, "0"),
        )

    assert Rechnung.naechste_nummer(date(2026, 10, 29)) == "260008"
    assert Rechnung.naechste_nummer(date(2027, 1, 2)) == "270001"


@pytest.mark.parametrize(
    ("text", "wert"), [("29,5", "29.5"), ("1.234,50", "1234.50"), ("", "0")]
)
def test_dezimal_deutsch(text, wert):
    assert dezimal(text) == Decimal(wert)


@pytest.mark.parametrize(
    ("von", "bis", "erwartet"),
    [
        ("2026-10-01", "2026-10-31", ("Leistungszeitraum", "Oktober 2026")),
        ("2026-10-05", "", ("Leistungsdatum", "05.10.2026")),
        ("2026-10-05", "2026-10-09", ("Leistungszeitraum", "05.10.2026 – 09.10.2026")),
    ],
)
def test_leistungszeit(von, bis, erwartet):
    assert leistungszeit(von, bis) == erwartet


def test_festschreiben_legt_zugferd_pdf_ab(client, firma, kunde, daten):
    antwort = client.post(reverse("invoicing:neu"), formular(kunde))

    rechnung = Rechnung.objects.get()
    assert antwort.status_code == 302
    assert rechnung.status == Rechnung.Status.FESTGESCHRIEBEN
    assert rechnung.nummer == "260001"
    assert rechnung.brutto == Decimal("2360.00")
    assert rechnung.positionen.count() == 1  # leere Zeile fällt weg
    inhalt = (daten / rechnung.datei).read_bytes()
    assert hashlib.sha256(inhalt).hexdigest() == rechnung.sha256
    pdf = PdfReader(BytesIO(inhalt))
    assert list(pdf.attachments) == ["factur-x.xml"]
    xml = pdf.attachments["factur-x.xml"][0].decode()
    assert "<ram:CategoryCode>E</ram:CategoryCode>" in xml
    assert "Kleinunternehmer gemäß § 19 UStG" in xml
    assert "Rechnung 260001" in pdf.pages[0].extract_text()
    ansicht = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk]))
    assert 'src="data:image/png;base64,' in ansicht.content.decode()


def test_festgeschriebene_rechnung_ist_unveraenderbar(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get()

    rechnung.betreff = "nachträglich"
    with pytest.raises(ValidationError):
        rechnung.save()
    with pytest.raises(ValidationError):
        rechnung.delete()
    with pytest.raises(ValidationError):
        Position(rechnung=rechnung, nr=2, bezeichnung="x").save()
    # Bearbeiten zeigt nur noch die Ansicht; ein POST ändert nichts am Beleg.
    client.post(
        reverse("invoicing:bearbeiten", args=[rechnung.pk]),
        formular(kunde, betreff="geändert"),
    )
    assert Rechnung.objects.get().betreff == ""


def test_stornieren_mit_kopie_zum_korrigieren(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    original = Rechnung.objects.get()
    ansicht = client.get(reverse("invoicing:bearbeiten", args=[original.pk]))
    assert 'id="storno-dialog"' in ansicht.content.decode()

    antwort = client.post(
        reverse("invoicing:stornieren", args=[original.pk]), {"kopie": "on"}
    )

    storno = Rechnung.objects.get(storno_zu=original)
    kopie = Rechnung.objects.get(status=Rechnung.Status.ENTWURF)
    assert antwort.url == reverse("invoicing:bearbeiten", args=[kopie.pk])
    assert Rechnung.objects.get(pk=original.pk).storniert
    assert storno.datum == date.today()
    assert storno.nummer not in ("", original.nummer)
    assert storno.brutto == Decimal("-2360.00")
    assert storno.beleg["storno_zu"] == {"nummer": "260001", "datum": "2026-10-29"}
    assert storno.datei.endswith(f"Stornorechnung-{storno.nummer}.pdf")
    inhalt = (daten / storno.datei).read_bytes()
    assert hashlib.sha256(inhalt).hexdigest() == storno.sha256
    pdf = PdfReader(BytesIO(inhalt))
    text = pdf.pages[0].extract_text()
    assert f"Stornorechnung {storno.nummer}" in text
    assert "260001 vom 29.10.2026" in text
    assert "-2.360,00" in text
    assert "GiroCode" not in text
    xml = pdf.attachments["factur-x.xml"][0].decode()
    assert "<ram:InvoiceReferencedDocument>" in xml
    assert "<ram:IssuerAssignedID>260001</ram:IssuerAssignedID>" in xml
    assert 'unitCode="HUR">-29.5' in xml
    assert "<ram:SpecifiedTradeSettlementPaymentMeans>" not in xml
    # Die Kopie ist ein normaler Entwurf mit denselben Positionen.
    assert kopie.kontakt == kunde and kopie.storno_zu is None
    assert [(p.bezeichnung, p.menge) for p in kopie.positionen.all()] == [
        ("Webdesign", Decimal("29.500"))
    ]

    # Kein zweites Storno, und eine Stornorechnung selbst lässt sich nicht stornieren.
    for pk in (original.pk, storno.pk):
        antwort = client.post(reverse("invoicing:stornieren", args=[pk]))
        assert antwort.status_code == 404
    assert Rechnung.objects.filter(storno_zu__isnull=False).count() == 1
    liste = client.get(reverse("invoicing:liste")).content.decode()
    assert "Storniert" in liste and f"Storno zu {original.nummer}" in liste


def test_stornieren_ohne_kopie_zeigt_stornorechnung(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    original = Rechnung.objects.get()

    antwort = client.post(reverse("invoicing:stornieren", args=[original.pk]))

    storno = Rechnung.objects.get(storno_zu=original)
    assert antwort.url == reverse("invoicing:bearbeiten", args=[storno.pk])
    assert not Rechnung.objects.filter(status=Rechnung.Status.ENTWURF).exists()
    ansicht = client.get(antwort.url).content.decode()
    assert "Storniert die" in ansicht and 'id="storno-dialog"' not in ansicht


def test_kopieren_legt_entwurf_an(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    original = Rechnung.objects.get()

    antwort = client.post(reverse("invoicing:kopieren", args=[original.pk]))

    kopie = Rechnung.objects.get(status=Rechnung.Status.ENTWURF)
    assert antwort.url == reverse("invoicing:bearbeiten", args=[kopie.pk])
    assert kopie.nummer == "" and kopie.datum == date.today()
    assert kopie.positionen.get().preis == Decimal("80.00")
    assert not Rechnung.objects.get(pk=original.pk).storniert


def test_unvollstaendig_bleibt_entwurf(client, kunde, daten):
    antwort = client.post(reverse("invoicing:neu"), formular(kunde), follow=True)

    rechnung = Rechnung.objects.get()
    assert rechnung.ist_entwurf
    assert rechnung.nummer == ""
    assert "Ihre Firmendaten" in antwort.content.decode()


def test_entwurf_vorschau_und_loeschen(client, firma, kunde, daten):
    antwort = client.post(reverse("invoicing:neu"), formular(kunde, aktion="vorschau"))
    rechnung = Rechnung.objects.get()
    assert antwort.url.endswith("?vorschau=1")

    # Seitenbilder statt eingebettetem PDF: kein PDF-Betrachter im Browser nötig.
    seite = client.get(antwort.url)
    assert seite.content.decode().count('src="data:image/png;base64,') == 1
    assert (
        client.get(reverse("invoicing:pdf", args=[rechnung.pk]))["Content-Type"]
        == "application/pdf"
    )

    client.post(reverse("invoicing:loeschen", args=[rechnung.pk]))
    assert not Rechnung.objects.exists()


def test_versand_mit_pdf_anhang(client, firma, kunde, daten, monkeypatch):
    monkeypatch.setattr(versand, "SmtpVersand", lambda **_: locmem.EmailBackend())
    firma.mail_server = "smtp.muster.test"
    firma.save()
    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get()

    seite = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk]))
    assert "buchhaltung@baeckerei.test" in seite.content.decode()
    client.post(
        reverse("invoicing:bearbeiten", args=[rechnung.pk]),
        {
            "an": "buchhaltung@baeckerei.test",
            "betreff": "Rechnung 260001",
            "text": "Anbei die Rechnung.",
            "kopie": "on",
        },
    )

    (nachricht,) = mail.outbox
    assert nachricht.to == ["buchhaltung@baeckerei.test"]
    assert nachricht.bcc == ["post@muster.test"]
    assert nachricht.attachments[0].filename == "Rechnung-260001.pdf"
    rechnung.refresh_from_db()
    assert rechnung.versendet_an == "buchhaltung@baeckerei.test"


def test_passwort_bleibt_bei_leerem_feld(client, firma):
    firma.mail_passwort = "geheim"
    firma.save()
    werte = {
        f: getattr(firma, f)
        for f in ("name", "strasse", "plz", "ort", "steuernummer", "email", "iban")
    }
    client.post(
        reverse("core:einstellungen"),
        {
            **werte,
            "kleinunternehmer": "on",
            "mail_port": "587",
            "mail_verschluesselung": "starttls",
            "mail_passwort": "",
        },
    )

    assert Firmendaten.laden().mail_passwort == "geheim"
    assert "geheim" not in client.get(reverse("core:einstellungen")).content.decode()


LOGO = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    b'<rect width="32" height="32" rx="9" fill="#0b1220"/></svg>'
)


def einstellungen_absenden(client, firma, **mehr):
    werte = {
        f: getattr(firma, f)
        for f in ("name", "strasse", "plz", "ort", "steuernummer", "email", "iban")
    }
    return client.post(
        reverse("core:einstellungen"),
        {
            **werte,
            "kleinunternehmer": "on",
            "mail_port": "587",
            "mail_verschluesselung": "starttls",
            **mehr,
        },
    )


def test_logo_hochladen_und_auf_rechnung(client, firma, kunde, daten):
    einstellungen_absenden(
        client, firma, logo_datei=SimpleUploadedFile("logo.svg", LOGO, "image/svg+xml")
    )
    assert bytes(Firmendaten.laden().logo) == LOGO
    seite = client.get(reverse("core:einstellungen")).content.decode()
    assert 'src="data:image/svg+xml;base64,' in seite

    ohne = client.get(reverse("invoicing:pdf", args=[Rechnung.objects.create().pk]))
    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get(status=Rechnung.Status.FESTGESCHRIEBEN)
    inhalt = (daten / rechnung.datei).read_bytes()
    assert len(inhalt) > len(ohne.content)  # Logo als Vektorgrafik im Kopf

    # Leeres Feld behält das Logo, „entfernen“ löscht es.
    einstellungen_absenden(client, firma)
    assert bytes(Firmendaten.laden().logo) == LOGO
    einstellungen_absenden(client, firma, logo_entfernen="on")
    assert bytes(Firmendaten.laden().logo) == b""


def test_marke_unter_dem_firmennamen(client, firma, kunde, daten):
    einstellungen_absenden(client, firma, marke="Muster Netz & Web")
    client.post(reverse("invoicing:neu"), formular(kunde))

    rechnung = Rechnung.objects.get()
    assert rechnung.beleg["absender"]["marke"] == "Muster Netz & Web"
    pdf = PdfReader(BytesIO((daten / rechnung.datei).read_bytes()))
    assert "Muster IT\nMuster Netz & Web" in pdf.pages[0].extract_text()


def test_kaputtes_logo_abgelehnt(client, firma):
    antwort = einstellungen_absenden(
        client,
        firma,
        logo_datei=SimpleUploadedFile("logo.png", b"\x89PNG kaputt", "image/png"),
    )
    assert "nicht als Bild lesen" in antwort.content.decode()
    assert bytes(Firmendaten.laden().logo) == b""
