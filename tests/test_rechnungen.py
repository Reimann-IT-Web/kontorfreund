"""Rechnung schreiben, festschreiben und versenden – mit erfundenen Daten."""

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail.backends import locmem
from django.urls import reverse
from pypdf import PdfReader

from angebote.models import Angebot
from archive.models import Altbeleg
from auftraege.models import Auftragsbestaetigung
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import versand
from invoicing.beleg import (
    absender_daten,
    briefkopf,
    druckdaten,
    grussformel,
    leistungszeit,
    schlusstext,
    setzen,
)
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


def seitentext(pfad):
    """Text der ersten Seite ohne die Zeilenumbrüche des Satzes."""
    return " ".join(
        PdfReader(BytesIO(pfad.read_bytes())).pages[0].extract_text().split()
    )


def test_skonto_steht_in_pdf_und_xml(client, firma, kunde, daten):
    client.post(
        reverse("invoicing:neu"),
        formular(kunde, skonto_prozent="2", skonto_tage="7"),
    )
    rechnung = Rechnung.objects.get()
    assert rechnung.beleg["skonto"] == {
        "prozent": "2.00",
        "tage": 7,
        "bis": "2026-11-05",
        "betrag": "47.20",
        "zahlbetrag": "2312.80",
    }
    text = seitentext(daten / rechnung.datei)
    assert "Bei Zahlung bis zum 05.11.2026 ziehen Sie 2 % Skonto ab" in text
    assert "2.312,80" in text
    xml = (
        PdfReader(BytesIO((daten / rechnung.datei).read_bytes()))
        .attachments["factur-x.xml"][0]
        .decode()
    )
    assert "#SKONTO#TAGE=7#PROZENT=2.00#" in xml

    # Die Kopie übernimmt das Skonto, die Stornorechnung nicht.
    assert rechnung.kopieren().skonto_prozent == Decimal("2.00")
    client.post(reverse("invoicing:stornieren", args=[rechnung.pk]))
    storno = Rechnung.objects.get(storno_zu=rechnung)
    assert storno.skonto_prozent == 0 and storno.beleg["skonto"] is None


@pytest.mark.parametrize(
    ("mehr", "fehler"),
    [
        ({"skonto_tage": "14"}, "kürzer sein als das Zahlungsziel"),
        ({"skonto_tage": ""}, "Tage für das Skonto"),
        ({"skonto_tage": "7", "zahlungsziel": "0"}, "gibt es kein Skonto"),
        ({"skonto_tage": "7", "skonto_prozent": "12"}, "kleiner oder gleich 10"),
    ],
)
def test_skonto_wird_geprueft(client, firma, kunde, mehr, fehler):
    antwort = client.post(
        reverse("invoicing:neu"),
        formular(kunde, aktion="speichern", **{"skonto_prozent": "2", **mehr}),
    )
    assert fehler in antwort.content.decode()
    assert not Rechnung.objects.exists()


def test_verzugshinweis_nur_bei_privatkunden(client, firma, kunde, daten):
    privat = Kontakt.objects.create(
        art=Kontakt.Art.PERSON,
        anrede="Frau",
        vorname="Erika",
        nachname="Beispiel",
        strasse="Ahornweg 2",
        plz="55116",
        ort="Mainz",
    )
    editor = client.get(reverse("invoicing:neu")).content.decode()
    assert 'name="verzugshinweis" id="verzugshinweis" checked' in editor

    for empfaenger in (kunde, privat):
        client.post(reverse("invoicing:neu"), formular(empfaenger, verzugshinweis="on"))
    firmenrechnung, privatrechnung = Rechnung.objects.order_by("pk")
    assert not firmenrechnung.beleg["verzugshinweis"]
    assert privatrechnung.beleg["verzugshinweis"]
    assert "nach § 286 Abs. 3 BGB auch ohne Mahnung in Verzug" in seitentext(
        daten / privatrechnung.datei
    )
    assert "§ 286" not in seitentext(daten / firmenrechnung.datei)

    client.post(reverse("invoicing:neu"), formular(privat))
    assert not Rechnung.objects.latest("pk").beleg["verzugshinweis"]


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


def korrektur_formular(kunde, menge, **mehr):
    return formular(
        kunde,
        bezeichnung=["Webdesign"],
        beschreibung=[""],
        menge=[menge],
        einheit=["Std."],
        preis=["80,00"],
        **mehr,
    )


def test_rechnungskorrektur_mindert_teilbetrag(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    original = Rechnung.objects.get()
    andere = Kontakt.objects.create(firmenname="Andere GmbH", ort="Mainz")

    antwort = client.post(reverse("invoicing:korrigieren", args=[original.pk]))

    entwurf = Rechnung.objects.get(korrektur_zu=original)
    assert antwort.url == reverse("invoicing:bearbeiten", args=[entwurf.pk])
    assert entwurf.ist_entwurf and entwurf.kontakt == kunde
    # Vorbelegt mit allen Positionen zum Kürzen, wie bei der Stornorechnung.
    assert entwurf.positionen.get().menge == Decimal("-29.500")
    seite = client.get(antwort.url).content.decode()
    assert "Rechnungskorrektur" in seite and "2.360,00" in seite

    # Empfänger und Steuerfall bleiben die des Originals, auch wenn etwas anderes kommt.
    client.post(
        antwort.url,
        korrektur_formular(
            andere,
            "-2,5",
            steuerfall="regel",
            girocode="on",
            kopftext=entwurf.kopftext,
        ),
    )

    korrektur = Rechnung.objects.get(pk=entwurf.pk)
    assert korrektur.status == Rechnung.Status.FESTGESCHRIEBEN
    assert korrektur.nummer == "260002"
    assert korrektur.kontakt == kunde
    assert korrektur.steuerfall == Rechnung.Steuerfall.KLEINUNTERNEHMER
    assert korrektur.brutto == Decimal("-200.00")
    assert korrektur.beleg["korrektur_zu"] == {
        "nummer": "260001",
        "datum": "2026-10-29",
    }
    assert korrektur.datei.endswith("Rechnungskorrektur-260002.pdf")
    pdf = PdfReader(BytesIO((daten / korrektur.datei).read_bytes()))
    text = pdf.pages[0].extract_text()
    assert "Rechnungskorrektur 260002" in text
    assert "260001 vom 29.10.2026 wird wie folgt korrigiert" in text
    assert "mindert sich damit um 200,00" in text and "Korrekturbetrag" in text
    assert "Bitte überweisen" not in text and "GiroCode" not in text
    xml = pdf.attachments["factur-x.xml"][0].decode()
    assert "<ram:IssuerAssignedID>260001</ram:IssuerAssignedID>" in xml
    assert 'unitCode="HUR">-2.5' in xml
    assert "<ram:SpecifiedTradeSettlementPaymentMeans>" not in xml

    original = Rechnung.objects.get(pk=original.pk)
    assert original.korrigierter_betrag == Decimal("2160.00")
    ansicht = client.get(reverse("invoicing:bearbeiten", args=[original.pk]))
    ansicht = ansicht.content.decode()
    assert "Rechnungskorrektur 260002" in ansicht and "2.160,00" in ansicht
    # Nach einer Korrektur nur noch weiter mindern, nicht mehr voll stornieren.
    assert 'id="storno-dialog"' not in ansicht and "Betrag mindern" in ansicht
    client.post(reverse("invoicing:stornieren", args=[original.pk]))
    assert not Rechnung.objects.filter(storno_zu=original).exists()
    liste = client.get(reverse("invoicing:liste")).content.decode()
    assert "Korrektur zu 260001" in liste


def test_rechnungskorrektur_hoechstens_bis_null(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    original = Rechnung.objects.get()
    client.post(reverse("invoicing:korrigieren", args=[original.pk]))
    entwurf = Rechnung.objects.get(korrektur_zu=original)
    hier = reverse("invoicing:bearbeiten", args=[entwurf.pk])

    zu_viel = client.post(hier, korrektur_formular(kunde, "-30"), follow=True)
    assert "Korrekturbetrag (höchstens 2.360,00" in zu_viel.content.decode()
    erhoeht = client.post(hier, korrektur_formular(kunde, "1"), follow=True)
    assert "Menge und Art der Leistung" in erhoeht.content.decode()
    assert Rechnung.objects.get(pk=entwurf.pk).ist_entwurf

    # Den ganzen Rest mindern ist erlaubt; danach ist nichts mehr zu korrigieren.
    client.post(hier, korrektur_formular(kunde, "-29,5"))
    korrektur = Rechnung.objects.get(pk=entwurf.pk)
    assert not korrektur.ist_entwurf
    assert Rechnung.objects.get(pk=original.pk).korrigierter_betrag == 0
    for pk in (original.pk, korrektur.pk):
        assert (
            client.post(reverse("invoicing:korrigieren", args=[pk])).status_code == 404
        )
    assert (
        client.post(reverse("invoicing:kopieren", args=[korrektur.pk])).status_code
        == 404
    )


def test_negative_menge_nur_in_der_korrektur(client, firma, kunde, daten):
    antwort = client.post(
        reverse("invoicing:neu"), korrektur_formular(kunde, "-1"), follow=True
    )

    assert "dürfen nicht negativ sein" in antwort.content.decode()
    assert not Rechnung.objects.exists()


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


def test_kurze_zahlen_lassen_der_leistung_platz(client, firma, kunde, daten):
    zeile = "14. Synchronisierung der FAQ-Daten mit den sichtbaren Inhalten"
    client.post(
        reverse("invoicing:neu"),
        formular(kunde, aktion="vorschau", beschreibung=[zeile, ""]),
    )

    pdf = client.get(reverse("invoicing:pdf", args=[Rechnung.objects.get().pk]))

    assert zeile in PdfReader(BytesIO(pdf.content)).pages[0].extract_text()


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


def test_unterschrift_hochladen_und_auf_rechnung(
    client, firma, kunde, daten, unterschrift
):
    einstellungen_absenden(
        client,
        firma,
        unterschrift_datei=SimpleUploadedFile("u.png", unterschrift, "image/png"),
        unterschrift_text="Mara Beispiel\r\nGeschäftsführung",
    )
    assert bytes(Firmendaten.laden().unterschrift) == unterschrift
    seite = client.get(reverse("core:einstellungen")).text
    assert 'alt="Ihre aktuelle Unterschrift"' in seite

    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get()
    absender = rechnung.beleg["absender"]
    assert absender["unterschrift_text"] == "Mara Beispiel\r\nGeschäftsführung"
    pdf = PdfReader(BytesIO((daten / rechnung.datei).read_bytes())).pages[0]
    assert "Mara Beispiel\nGeschäftsführung" in pdf.extract_text()
    assert len(pdf.images) == 1


def test_ohne_unterschrift_kein_bild_und_kein_text(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get()
    pdf = PdfReader(BytesIO((daten / rechnung.datei).read_bytes())).pages[0]
    assert not pdf.images


@pytest.mark.parametrize(
    "modell, adresse",
    [
        (Rechnung, "invoicing:pdf"),
        (Angebot, "angebote:pdf"),
        (Auftragsbestaetigung, "auftraege:pdf"),
    ],
)
def test_unterschrift_steht_auf_jeder_belegart(
    client, firma, unterschrift, modell, adresse
):
    firma.unterschrift = unterschrift
    firma.unterschrift_text = "Geschäftsführung"
    firma.save()

    entwurf = client.get(reverse(adresse, args=[modell.objects.create().pk]))

    pdf = PdfReader(BytesIO(entwurf.content)).pages[0]
    assert "Geschäftsführung" in pdf.extract_text()
    assert len(pdf.images) == 1


@pytest.mark.parametrize(
    "modell, adresse",
    [
        (Rechnung, "invoicing:pdf"),
        (Angebot, "angebote:pdf"),
        (Auftragsbestaetigung, "auftraege:pdf"),
    ],
)
def test_name_steht_nur_unter_der_unterschrift(
    client, firma, unterschrift, modell, adresse
):
    firma.unterschrift = unterschrift
    firma.unterschrift_text = "Max Muster\r\nGeschäftsführung"
    firma.save()
    # Gespeicherte Entwürfe tragen den Vorgabetext mit den Zeilenenden des Browsers.
    fusstext = grussformel(firma).replace("\n", "\r\n")

    entwurf = client.get(
        reverse(adresse, args=[modell.objects.create(fusstext=fusstext).pk])
    )

    text = PdfReader(BytesIO(entwurf.content)).pages[0].extract_text()
    assert "Mit freundlichen Grüßen\nMax Muster\nGeschäftsführung" in text


@pytest.mark.parametrize(
    "text, unter_der_unterschrift, erwartet",
    [
        ("Gruß\n\nMax Muster", "Max Muster", [["Gruß"]]),
        ("Gruß\r\n\r\nMax Muster\r\n", "Max Muster\r\nInhaber", [["Gruß"]]),
        ("Gruß\n\nMax Muster", "Max Muster, Inhaber", [["Gruß"]]),
        ("Gruß\n\nMax Muster", "Inhaber", [["Gruß"], ["Max Muster"]]),
        ("Gruß\n\nMax Muster", "", [["Gruß"], ["Max Muster"]]),
        ("Ihr Max Muster", "Max Muster", [["Ihr Max Muster"]]),
        ("Max Muster\n\nDanke.", "Max Muster", [["Max Muster"], ["Danke."]]),
        ("", "Max Muster", []),
    ],
)
def test_schlusstext_laesst_nur_den_doppelten_namen_weg(
    text, unter_der_unterschrift, erwartet
):
    absender = {
        "inhaber": "Max Muster",
        "name": "Muster IT",
        "unterschrift_text": unter_der_unterschrift,
    }
    assert schlusstext(text, absender) == erwartet


def test_schlusstext_nimmt_ohne_inhaber_den_firmennamen():
    absender = {"inhaber": "", "name": "Muster IT", "unterschrift_text": "Muster IT"}
    assert schlusstext("Gruß\n\nMuster IT", absender) == [["Gruß"]]


def test_gruss_und_unterschrift_bleiben_auf_einer_seite(
    client, firma, kunde, unterschrift
):
    firma.unterschrift = unterschrift
    firma.save()
    rechnung = Rechnung.objects.create(
        kontakt=kunde, fusstext="Mit freundlichen Grüßen"
    )

    # Mit jeder Position wandert das Ende des Belegs weiter nach unten über den Umbruch.
    for nr in range(1, 18):
        rechnung.positionen.create(
            nr=nr, bezeichnung=f"Leistung {nr}", menge=1, einheit="Std.", preis=80
        )
        entwurf = client.get(reverse("invoicing:pdf", args=[rechnung.pk]))
        pdf = PdfReader(BytesIO(entwurf.content))
        for seite in pdf.pages:
            gruss = "Mit freundlichen Grüßen" in seite.extract_text()
            assert bool(seite.images) == gruss, nr
    assert len(pdf.pages) == 2


def test_unterschrift_nur_als_bild(client, firma, unterschrift):
    firma.unterschrift = unterschrift
    firma.save()

    entwurf = client.get(reverse("invoicing:pdf", args=[Rechnung.objects.create().pk]))

    assert len(PdfReader(BytesIO(entwurf.content)).pages[0].images) == 1


def test_leeres_feld_behaelt_die_unterschrift(client, firma, unterschrift):
    einstellungen_absenden(
        client,
        firma,
        unterschrift_datei=SimpleUploadedFile("u.png", unterschrift, "image/png"),
    )
    einstellungen_absenden(client, firma)
    assert bytes(Firmendaten.laden().unterschrift) == unterschrift

    einstellungen_absenden(client, firma, unterschrift_entfernen="on")
    assert bytes(Firmendaten.laden().unterschrift) == b""


def test_kaputte_unterschrift_abgelehnt(client, firma):
    antwort = einstellungen_absenden(
        client,
        firma,
        unterschrift_datei=SimpleUploadedFile("u.png", b"\x89PNG kaputt", "image/png"),
    )
    assert "nicht als Bild lesen" in antwort.text
    assert bytes(Firmendaten.laden().unterschrift) == b""


def test_zu_grosse_unterschrift_abgelehnt(client, firma):
    antwort = einstellungen_absenden(
        client,
        firma,
        unterschrift_datei=SimpleUploadedFile(
            "u.png", b"\x89PNG" + bytes(1024 * 1024), "image/png"
        ),
    )
    assert "Die Unterschrift darf höchstens 1 MB groß sein." in antwort.text
    assert bytes(Firmendaten.laden().unterschrift) == b""


def test_entwurf_steht_auf_der_uebersicht_bis_zum_festschreiben(
    client, firma, kunde, daten
):
    assert 'id="entwuerfe"' not in client.get(reverse("core:start")).text

    client.post(reverse("invoicing:neu"), formular(kunde, aktion="speichern"))
    rechnung = Rechnung.objects.get()
    start = client.get(reverse("core:start")).text
    assert 'id="entwuerfe"' in start
    assert f'href="{reverse("invoicing:bearbeiten", args=[rechnung.pk])}"' in start

    client.post(reverse("invoicing:bearbeiten", args=[rechnung.pk]), formular(kunde))
    assert 'id="entwuerfe"' not in client.get(reverse("core:start")).text


def test_uebersicht_zeigt_entwuerfe_aller_belegarten_zuletzt_geaenderte_oben(
    client, kunde
):
    rechnung = Rechnung.objects.create(kontakt=kunde)
    angebot = Angebot.objects.create(kontakt=kunde)
    auftrag = Auftragsbestaetigung.objects.create()
    # Feste Zeiten: Unter Windows bekommen schnell angelegte Belege oft dieselbe.
    for beleg, stunde in ((rechnung, 18), (auftrag, 9), (angebot, 8)):
        type(beleg).objects.filter(pk=beleg.pk).update(
            geaendert=datetime(2026, 11, 6, stunde, 53, tzinfo=UTC)
        )

    start = client.get(reverse("core:start")).text

    assert "noch kein Empfänger" in start
    assert "Rechnung · 06.11.2026, 19:53" in start  # Ortszeit, nicht UTC
    assert (
        start.index(f'href="{reverse("invoicing:bearbeiten", args=[rechnung.pk])}"')
        < start.index(f'href="{reverse("auftraege:bearbeiten", args=[auftrag.pk])}"')
        < start.index(f'href="{reverse("angebote:bearbeiten", args=[angebot.pk])}"')
    )


def seitentexte(inhalt):
    """Text jeder Seite ohne die Zeilenumbrüche des Satzes."""
    return [
        " ".join(seite.extract_text().split())
        for seite in PdfReader(BytesIO(inhalt)).pages
    ]


def belegseiten(client, kunde, daten, **mehr):
    client.post(reverse("invoicing:neu"), formular(kunde, **mehr))
    return seitentexte((daten / Rechnung.objects.get().datei).read_bytes())


def test_eintrag_reisst_nicht_ueber_zwei_seiten(client, firma, kunde, daten):
    fuellung = "Betriebssystem, Bürosoftware und Scanner aktualisiert, " * 3
    eintraege = [f"Anfang{i} {fuellung}Ende{i}" for i in range(50)]

    seiten = belegseiten(
        client, kunde, daten, beschreibung=["\r\n".join(eintraege), ""]
    )

    assert len(seiten) > 2
    for i in range(50):
        assert any(f"Anfang{i} " in s and f"Ende{i} " in s for s in seiten), i


def test_kurze_position_wechselt_als_ganzes_die_seite(client, firma, kunde, daten):
    anzahl = 14

    seiten = belegseiten(
        client,
        kunde,
        daten,
        bezeichnung=[f"Leistung{i}" for i in range(anzahl)] + [""],
        beschreibung=[
            "\r\n".join(f"Zeile{i}x{j}" for j in range(5)) for i in range(anzahl)
        ]
        + [""],
        menge=[str(i + 2) for i in range(anzahl)] + [""],
        einheit=["Std."] * anzahl + [""],
        preis=["80,00"] * anzahl + [""],
    )

    assert len(seiten) > 1
    for i in range(anzahl):
        fundstellen = [s for s in seiten if f"Leistung{i} " in s]
        assert len(fundstellen) == 1, i
        assert f"{i + 1} Leistung{i} " in fundstellen[0]
        assert f"Zeile{i}x4 " in fundstellen[0]
        assert f" {i + 2} Std." in fundstellen[0]


def test_zu_langer_eintrag_laeuft_nicht_ueber_den_seitenrand(
    client, firma, kunde, daten
):
    seiten = belegseiten(
        client, kunde, daten, beschreibung=["Wort " * 3000 + "Schlusswort", ""]
    )

    assert len(seiten) > 3  # sonst stünde der Rest unsichtbar unter der Seite
    assert "Schlusswort" in seiten[-1]


def test_position_beginnt_nie_ohne_ihren_ersten_eintrag(client, firma, kunde, daten):
    client.post(
        reverse("invoicing:neu"),
        formular(
            kunde,
            bezeichnung=["Vorab", "Wartung", ""],
            beschreibung=["", "\r\n".join(f"Eintrag{i}" for i in range(30)), ""],
            menge=["1", "2,5", ""],
            einheit=["Std.", "Std.", ""],
            preis=["80,00", "80,00", ""],
        ),
    )
    druck = druckdaten(Rechnung.objects.get().beleg)

    for anzahl in range(40):  # schiebt die Position bis über das Seitenende
        druck["kopftext"] = [["Einleitung"] * anzahl]
        seiten = seitentexte(setzen(druck))
        for teil in ("2 Wartung", "2,5 Std.", "Eintrag0 "):
            assert ("Wartung" in seiten[0]) == (teil in seiten[0]), (anzahl, teil)


@pytest.mark.parametrize(
    "modell, adresse",
    [
        (Rechnung, "invoicing:pdf"),
        (Angebot, "angebote:pdf"),
        (Auftragsbestaetigung, "auftraege:pdf"),
    ],
)
def test_internetadresse_steht_in_der_fusszeile(client, firma, modell, adresse):
    firma.internetadresse = "https://muster-it.test"
    firma.save()

    entwurf = client.get(reverse(adresse, args=[modell.objects.create().pk]))

    text = PdfReader(BytesIO(entwurf.content)).pages[0].extract_text()
    assert "post@muster.test\nhttps://muster-it.test" in text


def test_ohne_internetadresse_bleibt_die_fusszeile_wie_sie_war(firma):
    assert briefkopf(absender_daten(firma))["fuss"][1] == ["post@muster.test"]


def test_internetadresse_ohne_https_wird_ergaenzt(client, firma):
    einstellungen_absenden(client, firma, internetadresse="muster-it.test")

    assert Firmendaten.laden().internetadresse == "https://muster-it.test"
    assert 'inputmode="url"' in client.get(reverse("core:einstellungen")).text


def test_ungueltige_internetadresse_wird_abgelehnt(client, firma):
    einstellungen_absenden(client, firma, internetadresse="keine adresse")

    assert Firmendaten.laden().internetadresse == ""


def test_festgeschriebener_beleg_behaelt_seine_internetadresse(
    client, firma, kunde, daten
):
    firma.internetadresse = "https://alt.test"
    firma.save()
    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get()

    firma.internetadresse = "https://neu.test"
    firma.save()

    assert rechnung.beleg["absender"]["internetadresse"] == "https://alt.test"
    assert "https://alt.test" in seitentext(daten / rechnung.datei)
