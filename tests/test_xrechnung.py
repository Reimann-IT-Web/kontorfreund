"""XRechnung für Behörden und Kunden, die sie verlangen – mit erfundenen Daten."""

import hashlib
from io import BytesIO

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail.backends import locmem
from django.urls import reverse
from pypdf import PdfReader

from contacts.models import Kontakt, kaeuferreferenz_pruefen
from core.models import Firmendaten
from invoicing import versand
from invoicing.beleg import XRECHNUNG
from invoicing.models import Rechnung

pytestmark = pytest.mark.django_db

# Test-Leitweg-ID aus den Beispielen der KoSIT, Prüfziffer 33.
LEITWEG_ID = "991-33333TEST-33"


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
    f.telefon = "06131 123456"
    f.iban = "DE02120300000000202051"
    f.save()
    return f


@pytest.fixture
def behoerde():
    return Kontakt.objects.create(
        firmenname="Stadtverwaltung Musterstadt",
        strasse="Rathausplatz 1",
        plz="55116",
        ort="Mainz",
        kaeuferreferenz=LEITWEG_ID.lower(),
        xrechnung=True,
    )


def formular(kontakt, aktion="festschreiben"):
    return {
        "kontakt": kontakt.pk,
        "datum": "2026-10-29",
        "leistung_von": "2026-10-01",
        "leistung_bis": "2026-10-31",
        "zahlungsziel": "30",
        "steuerfall": "kleinunternehmer",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Mit freundlichen Grüßen",
        "bezeichnung": ["Wartung Webseite"],
        "beschreibung": [""],
        "menge": ["4"],
        "einheit": ["Std."],
        "preis": ["80,00"],
        "aktion": aktion,
    }


@pytest.mark.parametrize(
    "wert",
    [
        "991-33333TEST-33",
        "04011000-1234512345-06",
        "992-90009-96",
        "Kostenstelle 4711",
        "",
    ],
)
def test_kaeuferreferenz_gueltig(wert):
    kaeuferreferenz_pruefen(wert)


def test_leitweg_id_mit_falscher_pruefziffer():
    with pytest.raises(ValidationError, match="Prüfziffer"):
        kaeuferreferenz_pruefen("991-33333TEST-34")


def test_adresse_mit_xrechnung_braucht_referenz_und_adresse(client):
    daten = {
        "art": "firma",
        "firmenname": "Stadtverwaltung Musterstadt",
        "land": "Deutschland",
        "xrechnung": "on",
    }
    ohne = client.post(reverse("contacts:neu"), daten).content.decode()
    assert "Für die XRechnung braucht es eine Käuferreferenz" in ohne

    ohne_mail = client.post(
        reverse("contacts:neu"), {**daten, "kaeuferreferenz": "Kostenstelle 4711"}
    ).content.decode()
    assert "braucht es eine E-Mail-Adresse" in ohne_mail

    tippfehler = client.post(
        reverse("contacts:neu"), {**daten, "kaeuferreferenz": "991-33333TEST-34"}
    ).content.decode()
    assert "Die Prüfziffer der Leitweg-ID stimmt nicht" in tippfehler
    assert not Kontakt.objects.exists()

    client.post(reverse("contacts:neu"), {**daten, "kaeuferreferenz": LEITWEG_ID})
    assert Kontakt.objects.get().kaeuferreferenz == LEITWEG_ID


def test_festschreiben_legt_xrechnung_ab(client, firma, behoerde, settings):
    client.post(reverse("invoicing:neu"), formular(behoerde))
    rechnung = Rechnung.objects.get()

    assert rechnung.nummer == "260001"
    assert rechnung.xml_datei == "archiv/rechnungen/2026/Rechnung-260001.xml"
    xml = (settings.DATA_DIR / rechnung.xml_datei).read_bytes()
    assert rechnung.xml_sha256 == hashlib.sha256(xml).hexdigest()
    text = xml.decode()
    assert f"<ram:ID>{XRECHNUNG}</ram:ID>" in text
    assert "<ram:ID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</ram:ID>" in text
    # Leitweg-ID als Käuferreferenz (BT-10) und elektronische Adresse (BT-49).
    assert f"<ram:BuyerReference>{LEITWEG_ID}</ram:BuyerReference>" in text
    assert f'<ram:URIID schemeID="0204">{LEITWEG_ID}</ram:URIID>' in text
    assert '<ram:URIID schemeID="EM">post@muster.test</ram:URIID>' in text
    # Ansprechpartner des Verkäufers (BG-6) und Zahlungsweg (BG-16).
    assert "<ram:PersonName>Max Muster</ram:PersonName>" in text
    assert "<ram:CompleteNumber>06131 123456</ram:CompleteNumber>" in text
    assert "<ram:IBANID>DE02120300000000202051</ram:IBANID>" in text

    # Das PDF trägt genau dieselbe XML und nennt die Leitweg-ID.
    pdf = PdfReader(BytesIO((settings.DATA_DIR / rechnung.datei).read_bytes()))
    assert pdf.attachments["factur-x.xml"][0] == xml
    assert "Leitweg-ID" in pdf.pages[0].extract_text()
    assert b"XRECHNUNG" in pdf.xmp_metadata.stream.get_data()

    seite = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk]))
    assert "XRechnung (XML)" in seite.content.decode()
    datei = client.get(reverse("invoicing:xml", args=[rechnung.pk]))
    assert b"".join(datei.streaming_content) == xml
    assert 'filename="Rechnung-260001.xml"' in datei["Content-Disposition"]


def test_zugferd_ohne_xrechnung_bleibt_wie_bisher(client, firma, behoerde, settings):
    behoerde.xrechnung = False
    behoerde.save()
    client.post(reverse("invoicing:neu"), formular(behoerde))
    rechnung = Rechnung.objects.get()

    assert rechnung.xml_datei == ""
    pdf = PdfReader(BytesIO((settings.DATA_DIR / rechnung.datei).read_bytes()))
    xml = pdf.attachments["factur-x.xml"][0].decode()
    assert "<ram:ID>urn:cen.eu:en16931:2017</ram:ID>" in xml
    assert "DefinedTradeContact" not in xml
    # Die Käuferreferenz aus der Adresse kommt trotzdem auf die Rechnung.
    assert f"<ram:BuyerReference>{LEITWEG_ID}</ram:BuyerReference>" in xml
    assert client.get(reverse("invoicing:xml", args=[rechnung.pk])).status_code == 404


def test_xrechnung_braucht_telefon_mail_und_iban(client, firma, behoerde):
    firma.telefon = ""
    firma.save()

    antwort = client.post(reverse("invoicing:neu"), formular(behoerde), follow=True)

    assert "Ihre Telefonnummer, E-Mail-Adresse und IBAN" in antwort.content.decode()
    assert Rechnung.objects.get().ist_entwurf

    # Ohne Leitweg-ID braucht es die E-Mail-Adresse des Empfängers.
    Kontakt.objects.filter(pk=behoerde.pk).update(kaeuferreferenz="Kostenstelle 4711")
    rechnung = Rechnung.objects.get()
    assert "E-Mail-Adresse des Empfängers" in rechnung.fehlende_angaben(firma)


def test_storno_einer_xrechnung(client, firma, behoerde, settings):
    client.post(reverse("invoicing:neu"), formular(behoerde))
    original = Rechnung.objects.get()

    client.post(reverse("invoicing:stornieren", args=[original.pk]))

    storno = Rechnung.objects.get(storno_zu=original)
    text = (settings.DATA_DIR / storno.xml_datei).read_text(encoding="utf-8")
    assert "<ram:IssuerAssignedID>260001</ram:IssuerAssignedID>" in text
    # Den Zahlungsweg verlangt die XRechnung auch bei negativem Betrag.
    assert "<ram:IBANID>DE02120300000000202051</ram:IBANID>" in text
    assert "SpecifiedTradePaymentTerms" not in text


def test_versand_haengt_xml_an(client, firma, behoerde, monkeypatch):
    monkeypatch.setattr(versand, "SmtpVersand", lambda **_: locmem.EmailBackend())
    firma.mail_server = "smtp.muster.test"
    firma.save()
    client.post(reverse("invoicing:neu"), formular(behoerde))
    rechnung = Rechnung.objects.get()

    client.post(
        reverse("invoicing:bearbeiten", args=[rechnung.pk]),
        {"an": "rechnung@stadt.test", "betreff": "Rechnung 260001", "text": "Anbei."},
    )

    (nachricht,) = mail.outbox
    assert [a.filename for a in nachricht.attachments] == [
        "Rechnung-260001.pdf",
        "Rechnung-260001.xml",
    ]
