"""Empfangene E-Rechnungen (Spezifikation M-7)."""

import base64
import hashlib
import os
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from pypdf import PdfWriter

from contacts.models import Kontakt
from core.models import Firmendaten
from eingang import lesen
from eingang.models import Aufbewahrt, Eingangsrechnung
from eingang.templatetags.geld import geld
from invoicing.models import Rechnung

pytestmark = pytest.mark.django_db

ANHANG = b"%PDF-1.4 Stundenzettel"

# Eine kleine XRechnung in UBL-Syntax mit Rabatt, Skonto und Anhang.
UBL = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
  <cbc:ID>RE-2026-0815</cbc:ID>
  <cbc:IssueDate>2026-10-20</cbc:IssueDate>
  <cbc:DueDate>2026-11-03</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:Note>#ADU#Vielen Dank für Ihren Auftrag.</cbc:Note>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cbc:BuyerReference>Bestellung Oktober</cbc:BuyerReference>
  <cac:InvoicePeriod>
    <cbc:StartDate>2026-10-01</cbc:StartDate>
    <cbc:EndDate>2026-10-31</cbc:EndDate>
  </cac:InvoicePeriod>
  <cac:OrderReference><cbc:ID>B-4711</cbc:ID></cac:OrderReference>
  <cac:AdditionalDocumentReference>
    <cbc:ID>Stundenzettel</cbc:ID>
    <cbc:DocumentDescription>Stundenzettel Oktober</cbc:DocumentDescription>
    <cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject mimeCode="application/pdf" filename="stunden.pdf">{base64.b64encode(ANHANG).decode()}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment>
  </cac:AdditionalDocumentReference>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cbc:EndpointID schemeID="EM">rechnung@serverhaus.test</cbc:EndpointID>
      <cac:PartyName><cbc:Name>Serverhaus</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>Hafenstraße 7</cbc:StreetName>
        <cbc:CityName>Hamburg</cbc:CityName>
        <cbc:PostalZone>20457</cbc:PostalZone>
        <cac:Country><cbc:IdentificationCode>DE</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>DE 987654321</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity><cbc:RegistrationName>Serverhaus Nord GmbH</cbc:RegistrationName></cac:PartyLegalEntity>
      <cac:Contact>
        <cbc:Name>Buchhaltung</cbc:Name>
        <cbc:Telephone>040 123456</cbc:Telephone>
        <cbc:ElectronicMail>buchhaltung@serverhaus.test</cbc:ElectronicMail>
      </cac:Contact>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cbc:EndpointID schemeID="EM">post@muster.test</cbc:EndpointID>
      <cac:PostalAddress>
        <cbc:StreetName>Gartenweg 1</cbc:StreetName>
        <cbc:CityName>Mainz</cbc:CityName>
        <cbc:PostalZone>55116</cbc:PostalZone>
        <cac:Country><cbc:IdentificationCode>DE</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyLegalEntity><cbc:RegistrationName>Muster IT</cbc:RegistrationName></cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>58</cbc:PaymentMeansCode>
    <cbc:PaymentID>RE-2026-0815</cbc:PaymentID>
    <cac:PayeeFinancialAccount>
      <cbc:ID>DE02120300000000202051</cbc:ID>
      <cbc:Name>Serverhaus Nord GmbH</cbc:Name>
    </cac:PayeeFinancialAccount>
  </cac:PaymentMeans>
  <cac:PaymentTerms><cbc:Note>#SKONTO#TAGE=7#PROZENT=2.00#
</cbc:Note></cac:PaymentTerms>
  <cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>Treuerabatt</cbc:AllowanceChargeReason>
    <cbc:Amount currencyID="EUR">10.00</cbc:Amount>
    <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>
  </cac:AllowanceCharge>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="EUR">36.10</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="EUR">190.00</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="EUR">36.10</cbc:TaxAmount>
      <cac:TaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="EUR">200.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="EUR">190.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="EUR">226.10</cbc:TaxInclusiveAmount>
    <cbc:AllowanceTotalAmount currencyID="EUR">10.00</cbc:AllowanceTotalAmount>
    <cbc:PayableAmount currencyID="EUR">226.10</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="MON">1</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="EUR">150.00</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Description>Rack-Platz im Rechenzentrum</cbc:Description>
      <cbc:Name>Serverhosting</cbc:Name>
      <cac:SellersItemIdentification><cbc:ID>SH-1</cbc:ID></cac:SellersItemIdentification>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="EUR">150.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
  <cac:InvoiceLine>
    <cbc:ID>2</cbc:ID>
    <cbc:InvoicedQuantity unitCode="HUR">2.5</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="EUR">50.00</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>Einrichtung</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>19</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="EUR">20.00</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>
""".encode()


def hochladen(client, *dateien):
    """Dateien als (Name, Inhalt) hochladen und der Weiterleitung folgen."""
    return client.post(
        reverse("eingang:hochladen"),
        {"dateien": [SimpleUploadedFile(name, inhalt) for name, inhalt in dateien]},
        follow=True,
    )


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


def eigene_rechnung(client, **adresse):
    """Eine eigene Rechnung festschreiben: ein Beispiel für ZUGFeRD und XRechnung."""
    kunde = Kontakt.objects.create(
        firmenname="Kunde GmbH",
        strasse="Lindenweg 4",
        plz="55116",
        ort="Mainz",
        email="buchhaltung@kunde.test",
        **adresse,
    )
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": "2026-10-29",
            "leistung_von": "2026-10-01",
            "leistung_bis": "2026-10-31",
            "zahlungsziel": "14",
            "steuerfall": "regel",
            "kopftext": "Sehr geehrte Damen und Herren,",
            "fusstext": "Mit freundlichen Grüßen",
            "bezeichnung": ["Wartung Webseite"],
            "beschreibung": [""],
            "menge": ["4"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    rechnung = Rechnung.objects.get(kontakt=kunde)
    assert not rechnung.ist_entwurf
    return rechnung


def test_ubl_lesbar_anzeigen(client, settings):
    antwort = hochladen(client, ("RE-2026-0815.xml", UBL))
    r = Eingangsrechnung.objects.get()
    assert (r.format, r.syntax, r.art) == ("xml", "UBL", "380")
    assert (r.nummer, r.datum, r.faellig) == (
        "RE-2026-0815",
        date(2026, 10, 20),
        date(2026, 11, 3),
    )
    assert (r.lieferant, r.ust_id) == ("Serverhaus Nord GmbH", "DE987654321")
    assert r.brutto == r.zahlbetrag == Decimal("226.10")
    assert r.kontakt is None
    original = Path(settings.DATA_DIR) / r.datei
    assert original.read_bytes() == UBL
    assert r.sha256 == hashlib.sha256(UBL).hexdigest()

    seite = antwort.content.decode()
    assert antwort.redirect_chain[-1][0] == reverse("eingang:anzeigen", args=[r.pk])
    for text in [
        "Rechnung RE-2026-0815 von Serverhaus Nord GmbH ist abgelegt.",
        "Hafenstraße 7",
        "Rack-Platz im Rechenzentrum",
        "2,5 Std.",
        "Treuerabatt",
        "−10,00 €",
        "Umsatzsteuer 19 %",
        "226,10 €",
        "2 % Skonto bei Zahlung innerhalb von 7 Tagen",
        "DE02 1203 0000 0000 2020 51",
        "Vielen Dank für Ihren Auftrag.",
        "B-4711",
        "Käuferreferenz",
        "stunden.pdf",
        "XRechnung 3.0",
        "eben geprüft: unverändert",
    ]:
        assert text in seite, text
    assert "#ADU#" not in seite


def test_anhang_herunterladen(client):
    hochladen(client, ("re.xml", UBL))
    r = Eingangsrechnung.objects.get()
    antwort = client.get(reverse("eingang:anhang", args=[r.pk, 0]))
    assert b"".join(antwort.streaming_content) == ANHANG
    assert antwort["Content-Disposition"].startswith("attachment")
    assert client.get(reverse("eingang:anhang", args=[r.pk, 5])).status_code == 404


def test_xml_wird_heruntergeladen(client):
    hochladen(client, ("re.xml", UBL))
    r = Eingangsrechnung.objects.get()
    antwort = client.get(reverse("eingang:datei", args=[r.pk]))
    assert b"".join(antwort.streaming_content) == UBL
    assert antwort["Content-Disposition"].startswith("attachment")


def test_zugferd_pdf_einlesen(client, firma, settings):
    eigene = eigene_rechnung(client)
    pdf = (Path(settings.DATA_DIR) / eigene.datei).read_bytes()
    antwort = hochladen(client, ("rechnung.pdf", pdf))
    r = Eingangsrechnung.objects.get()
    assert (r.format, r.syntax) == ("pdf", "CII")
    assert (r.nummer, r.lieferant, r.brutto) == (
        eigene.nummer,
        "Muster IT",
        eigene.brutto,
    )
    seite = antwort.content.decode()
    for text in [
        "Wartung Webseite",
        "Gartenweg 1",
        "Kunde GmbH",
        "PDF öffnen",
        "ZUGFeRD EN 16931",
    ]:
        assert text in seite, text

    ansehen = client.get(reverse("eingang:datei", args=[r.pk]))
    assert ansehen["Content-Type"] == "application/pdf"
    assert not ansehen["Content-Disposition"].startswith("attachment")
    laden = client.get(reverse("eingang:datei", args=[r.pk]) + "?herunterladen")
    assert laden["Content-Disposition"].startswith("attachment")
    assert b"".join(laden.streaming_content) == pdf


def test_xrechnung_cii_einlesen(client, firma, settings):
    eigene = eigene_rechnung(client, kaeuferreferenz="991-33333TEST-33", xrechnung=True)
    xml = (Path(settings.DATA_DIR) / eigene.xml_datei).read_bytes()
    seite = hochladen(client, ("rechnung.xml", xml)).content.decode()
    r = Eingangsrechnung.objects.get()
    assert (r.format, r.syntax, r.nummer) == ("xml", "CII", eigene.nummer)
    assert "Leitweg-ID" in seite
    assert "991-33333TEST-33" in seite
    assert "XRechnung 3.0" in seite


def test_lieferant_ueber_ust_id(client):
    kontakt = Kontakt.objects.create(
        firmenname="Serverhaus",
        kategorie=Kontakt.Kategorie.LIEFERANT,
        ust_id="DE987654321",
    )
    seite = hochladen(client, ("re.xml", UBL)).content.decode()
    assert Eingangsrechnung.objects.get().kontakt == kontakt
    assert "und der Adresse Serverhaus zugeordnet" in seite


def test_lieferant_ueber_namen(client):
    kontakt = Kontakt.objects.create(firmenname="serverhaus nord gmbh")
    hochladen(client, ("re.xml", UBL))
    assert Eingangsrechnung.objects.get().kontakt == kontakt


def test_kein_lieferant_bei_zwei_treffern(client):
    Kontakt.objects.create(firmenname="Serverhaus Nord GmbH")
    Kontakt.objects.create(firmenname="Serverhaus Nord GmbH", ort="Kiel")
    hochladen(client, ("re.xml", UBL))
    assert Eingangsrechnung.objects.get().kontakt is None


def test_dieselbe_datei_nur_einmal(client):
    hochladen(client, ("re.xml", UBL))
    antwort = hochladen(client, ("nochmal.xml", UBL))
    r = Eingangsrechnung.objects.get()
    assert antwort.redirect_chain[-1][0] == reverse("eingang:anzeigen", args=[r.pk])
    assert "Diese Datei ist schon abgelegt" in antwort.content.decode()


def test_gleiche_nummer_vom_selben_lieferanten_warnt(client):
    hochladen(client, ("re.xml", UBL))
    zweite = UBL.replace(b"Vielen Dank", b"Herzlichen Dank")
    seite = hochladen(client, ("re-2.xml", zweite)).content.decode()
    assert Eingangsrechnung.objects.count() == 2
    assert "ist schon eine Rechnung RE-2026-0815 abgelegt" in seite


def test_mehrere_dateien_auf_einmal(client, firma, settings):
    eigene = eigene_rechnung(client)
    pdf = (Path(settings.DATA_DIR) / eigene.datei).read_bytes()
    antwort = hochladen(client, ("a.xml", UBL), ("b.pdf", pdf), ("c.txt", b"Hallo"))
    assert Eingangsrechnung.objects.count() == 2
    assert antwort.redirect_chain[-1][0] == reverse("eingang:liste")
    seite = antwort.content.decode()
    assert "2 E-Rechnungen sind abgelegt." in seite
    assert "c.txt: Die Datei ist weder eine XML- noch eine PDF-Datei." in seite


def _pdf_ohne_xml():
    schreiber = PdfWriter()
    schreiber.add_blank_page(width=595, height=842)
    ausgabe = BytesIO()
    schreiber.write(ausgabe)
    return ausgabe.getvalue()


@pytest.mark.parametrize(
    ("name", "inhalt", "meldung"),
    [
        ("brief.txt", b"Hallo", "weder eine XML- noch eine PDF-Datei"),
        ("scan.pdf", _pdf_ohne_xml(), "enthält keine E-Rechnung"),
        ("kaputt.pdf", b"%PDF-1.7 kaputt", "lässt sich nicht öffnen"),
        (
            "dtd.xml",
            b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>',
            "Dokumenttyp-Definition",
        ),
        ("andere.xml", b"<bestellung/>", "keine E-Rechnung im Format"),
        (
            "leer.xml",
            b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>',
            "fehlen Rechnungsnummer oder -datum",
        ),
    ],
)
def test_ungeeignete_dateien_werden_abgelehnt(client, settings, name, inhalt, meldung):
    seite = hochladen(client, (name, inhalt)).content.decode()
    assert meldung in seite
    assert not Eingangsrechnung.objects.exists()
    assert not (Path(settings.DATA_DIR) / "archiv" / "eingang").exists()


def test_eingangsrechnung_ist_unveraenderbar(client):
    hochladen(client, ("re.xml", UBL))
    r = Eingangsrechnung.objects.get()
    r.nummer = "anders"
    with pytest.raises(Aufbewahrt):
        r.save()
    with pytest.raises(Aufbewahrt):
        r.save(update_fields=["nummer"])
    with pytest.raises(Aufbewahrt):
        r.delete()
    r.refresh_from_db()
    r.kontakt = Kontakt.objects.create(firmenname="Serverhaus")
    r.save(update_fields=["kontakt"])


def test_zuordnen_und_als_adresse_anlegen(client):
    hochladen(client, ("re.xml", UBL))
    r = Eingangsrechnung.objects.get()
    adresse = reverse("eingang:zuordnen", args=[r.pk])
    client.post(adresse, {"kontakt": "", "neu": "1"})
    r.refresh_from_db()
    k = r.kontakt
    assert k.kategorie == Kontakt.Kategorie.LIEFERANT
    assert (k.firmenname, k.strasse, k.plz, k.ort, k.land) == (
        "Serverhaus Nord GmbH",
        "Hafenstraße 7",
        "20457",
        "Hamburg",
        "Deutschland",
    )
    assert (k.email, k.telefon, k.ust_id) == (
        "buchhaltung@serverhaus.test",
        "040 123456",
        "DE987654321",
    )

    andere = Kontakt.objects.create(firmenname="Serverhaus")
    client.post(adresse, {"kontakt": str(andere.pk)})
    r.refresh_from_db()
    assert r.kontakt == andere
    client.post(adresse, {"kontakt": ""})
    r.refresh_from_db()
    assert r.kontakt is None


def test_veraenderte_datei_faellt_auf(client, settings):
    hochladen(client, ("re.xml", UBL))
    r = Eingangsrechnung.objects.get()
    (Path(settings.DATA_DIR) / r.datei).write_bytes(UBL.replace(b"226.10", b"26.10"))
    seite = client.get(reverse("eingang:anzeigen", args=[r.pk])).content.decode()
    assert "stimmt nicht mehr mit der Prüfsumme überein" in seite
    assert "Rack-Platz" not in seite


def test_liste_und_suche(client):
    hochladen(client, ("re.xml", UBL))
    seite = client.get(reverse("eingang:liste")).content.decode()
    assert "Serverhaus Nord GmbH" in seite
    assert "RE-2026-0815" in seite
    leer = client.get(reverse("eingang:liste"), {"q": "Bäckerei"}).content.decode()
    assert "Keine Rechnung gefunden" in leer


def test_geld():
    assert geld(Decimal("0.4400")) == "0,44 €"
    assert geld(Decimal("1.23456")) == "1,23456 €"
    assert geld(Decimal("1234.5"), "USD") == "1.234,50 USD"
    assert geld(None) == ""


TESTSUITE = os.environ.get("XRECHNUNG_TESTSUITE")


@pytest.mark.skipif(
    not TESTSUITE, reason="Die XRechnung-Testsuite liegt nur in der CI bereit"
)
def test_beispiele_der_xrechnung_testsuite(client):
    """Abnahme Phase 3: Die offiziellen Beispielrechnungen werden korrekt angezeigt."""
    null = Decimal("0")
    dateien = sorted(Path(TESTSUITE).rglob("*.xml"))
    assert len(dateien) > 50
    for datei in dateien:
        d = lesen.auswerten(datei.read_bytes())
        s = d["summen"]
        oben = sum((p["netto"] for p in d["positionen"] if not p["unter"]), null)
        assert oben == s["positionen"], datei.name
        netto = s["positionen"] + (s["zuschlaege"] or null) - (s["abschlaege"] or null)
        assert netto == s["netto"], datei.name
        assert s["netto"] + (s["steuer"] or null) == s["brutto"], datei.name
        assert sum((t["betrag"] for t in d["steuern"]), null) == (s["steuer"] or null)
        assert (
            s["brutto"]
            - (s["gezahlt"] or null)
            + (s["rundung"] or null)
            + sum((x["betrag"] for x in s["dritte"]), null)
            == s["zahlbetrag"]
        ), datei.name
        assert d["verkaeufer"]["name"] and d["kaeufer"]["name"], datei.name
        assert all(p["name"] for p in d["positionen"]), datei.name

        antwort = hochladen(client, (datei.name, datei.read_bytes()))
        assert antwort.status_code == 200, datei.name
        assert d["nummer"] in antwort.content.decode(), datei.name
