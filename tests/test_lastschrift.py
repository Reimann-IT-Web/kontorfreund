"""SEPA-Lastschrift (Spezifikation B-12) – mit erfundenen Daten."""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from pypdf import PdfReader

from contacts.models import Kontakt, monate_zurueck
from core.models import Firmendaten, glaeubiger_pruefen
from invoicing.models import Rechnung
from zahlungen.models import Zahlung

pytestmark = pytest.mark.django_db

# Die Beispiel-ID der Deutschen Bundesbank.
GLAEUBIGER = "DE98ZZZ09999999999"


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster Seminare"
    f.inhaber = "Mara Beispiel"
    f.strasse = "Gartenweg 1"
    f.plz = "10115"
    f.ort = "Berlin"
    f.steuernummer = "12/345/67890"
    f.email = "post@seminare.test"
    f.iban = "DE02120300000000202051"
    f.bank = "Musterbank"
    f.glaeubiger_id = GLAEUBIGER
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Betreuungsbüro Muster",
        anrede="Frau",
        vorname="Jana",
        nachname="Beispiel",
        strasse="Gartenstraße 7a",
        plz="04109",
        ort="Leipzig",
        email="kontakt@betreuung.test",
        mandat_referenz="9003",
        mandat_datum=date.today() - timedelta(days=400),
    )


@pytest.fixture
def daten(tmp_path, settings):
    settings.DATA_DIR = tmp_path
    return tmp_path


def formular(kunde, aktion="festschreiben", **mehr):
    return {
        "kontakt": kunde.pk,
        "datum": date.today().isoformat(),
        "leistung_von": date.today().isoformat(),
        "zahlungsziel": "14",
        "zahlweg": "lastschrift",
        "steuerfall": "kleinunternehmer",
        "kopftext": "Sehr geehrte Frau Beispiel,",
        "fusstext": "Mit freundlichen Grüßen",
        "girocode": "on",
        "bezeichnung": ["Teilnahme am Webinar"],
        "beschreibung": [""],
        "menge": ["1"],
        "einheit": [""],
        "preis": ["89,00"],
        "aktion": aktion,
        **mehr,
    }


def pdf_und_xml(rechnung, daten):
    pdf = PdfReader(BytesIO((daten / rechnung.datei).read_bytes()))
    text = " ".join(pdf.pages[0].extract_text().split())
    return text, pdf.attachments["factur-x.xml"][0].decode()


@pytest.mark.parametrize("kennung", [GLAEUBIGER, "de98 zzz0 9999 9999 99"])
def test_gueltige_glaeubiger_id(kennung):
    glaeubiger_pruefen(kennung)


@pytest.mark.parametrize(
    "kennung", ["DE97ZZZ09999999999", "DE98ZZZ0999999999", "Gläubiger", ""]
)
def test_falsche_glaeubiger_id(kennung):
    with pytest.raises(ValidationError):
        glaeubiger_pruefen(kennung)


def test_einstellungen_speichern_glaeubiger_id_und_lastschrifttext(client, firma):
    antwort = client.post(
        reverse("core:einstellungen"),
        {
            **{
                f: getattr(firma, f)
                for f in ("name", "strasse", "plz", "ort", "steuernummer", "email")
            },
            "umsatzsteuer": "kleinunternehmer",
            "mail_port": "587",
            "mail_verschluesselung": "starttls",
            "glaeubiger_id": "de98 zzz0 9999 9999 99",
            "lastschrifttext": "Wir ziehen {betrag} ein (Mandat {mandat}).",
        },
    )
    assert antwort.status_code == 302
    firma.refresh_from_db()
    assert firma.glaeubiger_id == GLAEUBIGER
    assert firma.lastschrifttext == "Wir ziehen {betrag} ein (Mandat {mandat})."


def test_lastschrifttext_mit_unbekanntem_platzhalter(client, firma):
    antwort = client.post(
        reverse("core:einstellungen"),
        {
            **{
                f: getattr(firma, f)
                for f in ("name", "strasse", "plz", "ort", "steuernummer", "email")
            },
            "umsatzsteuer": "kleinunternehmer",
            "mail_port": "587",
            "mail_verschluesselung": "starttls",
            "lastschrifttext": "Einzug {wann}",
        },
    )
    assert "{wann}" in antwort.content.decode()
    assert Firmendaten.laden().lastschrifttext == ""


@pytest.mark.parametrize(
    ("tag", "monate", "erwartet"),
    [
        (date(2026, 11, 18), 36, date(2023, 11, 18)),
        (date(2027, 5, 31), 3, date(2027, 2, 28)),
        (date(2028, 2, 29), 12, date(2027, 2, 28)),
    ],
)
def test_monate_zurueck(tag, monate, erwartet):
    assert monate_zurueck(tag, monate) == erwartet


def test_mandat_verfaellt_nach_36_monaten_ohne_einzug():
    k = Kontakt(
        firmenname="Kanzlei", mandat_referenz="9004", mandat_datum=date(2023, 11, 19)
    )
    assert k.mandat_gueltig(date(2026, 11, 18))
    assert not k.mandat_gueltig(date(2026, 11, 19))
    assert "unterschrieben am 19.11.2023" in k.mandat_verfallen_text(date(2026, 11, 19))
    # Ein Einzug hält es gültig.
    k.mandat_zuletzt = date(2026, 1, 10)
    assert k.mandat_gueltig(date(2028, 1, 10))
    assert not Kontakt(firmenname="Ohne", mandat_referenz="1").mandat_gueltig()


def test_adresse_braucht_referenz_und_datum(client):
    antwort = client.post(
        reverse("contacts:neu"),
        {"art": "person", "nachname": "Beispiel", "mandat_datum": "2025-02-03"},
    )
    assert "Bitte die Mandatsreferenz eintragen." in antwort.content.decode()
    antwort = client.post(
        reverse("contacts:neu"),
        {"art": "person", "nachname": "Beispiel", "mandat_referenz": "9003"},
    )
    assert "Bitte das Datum der Unterschrift eintragen." in antwort.content.decode()
    assert not Kontakt.objects.exists()


def test_mandatsreferenz_ist_eindeutig(client, kunde):
    antwort = client.post(
        reverse("contacts:neu"),
        {
            "art": "person",
            "nachname": "Zweite",
            "mandat_referenz": "9003",
            "mandat_datum": "2025-02-03",
        },
    )
    assert "hat schon eine andere Adresse" in antwort.content.decode()
    antwort = client.post(
        reverse("contacts:neu"),
        {
            "art": "person",
            "nachname": "Zweite",
            "mandat_referenz": "Mandat 1",
            "mandat_datum": "2025-02-03",
        },
    )
    assert "ohne Leerzeichen" in antwort.content.decode()


def test_neue_rechnung_waehlt_lastschrift_bei_gueltigem_mandat(client, firma, kunde):
    antwort = client.get(reverse("invoicing:neu"), {"empfaenger": kunde.pk})
    assert antwort.context["form"]["zahlweg"].value() == "lastschrift"

    firma.glaeubiger_id = ""
    firma.save()
    antwort = client.get(reverse("invoicing:neu"), {"empfaenger": kunde.pk})
    assert antwort.context["form"]["zahlweg"].value() == "ueberweisung"


def test_verfallenes_mandat_ergibt_ueberweisung(client, firma, kunde):
    kunde.mandat_datum = date.today() - timedelta(days=4 * 365)
    kunde.save()
    antwort = client.get(reverse("invoicing:neu"), {"empfaenger": kunde.pk})
    assert antwort.context["form"]["zahlweg"].value() == "ueberweisung"


def test_lastschrift_rechnung_festschreiben(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))

    rechnung = Rechnung.objects.get()
    assert not rechnung.ist_entwurf
    assert rechnung.beleg["girocode"] is False
    assert rechnung.beleg["lastschrift"]["mandat"] == "9003"
    text, xml = pdf_und_xml(rechnung, daten)
    faellig = f"{rechnung.faellig:%d.%m.%Y}"
    assert f"Der Betrag von 89,00 € wird am {faellig} per SEPA-Lastschrift" in text
    assert f"Mandatsreferenz 9003, Gläubiger-ID {GLAEUBIGER}" in text
    assert "Bitte überweisen" not in text
    assert "<ram:TypeCode>59</ram:TypeCode>" in xml
    assert f"<ram:CreditorReferenceID>{GLAEUBIGER}</ram:CreditorReferenceID>" in xml
    assert "<ram:DirectDebitMandateID>9003</ram:DirectDebitMandateID>" in xml
    assert "PayeePartyCreditorFinancialAccount" not in xml
    assert "PayerPartyDebtorFinancialAccount" not in xml


def test_eigener_lastschrifttext_und_iban_des_kunden(client, firma, kunde, daten):
    firma.lastschrifttext = (
        "Da Sie unter der Kunden-Nr. {kundennummer} eine Lastschriftermächtigung "
        "erteilt haben, wird das Entgelt von {betrag} eingezogen."
    )
    firma.save()
    kunde.mandat_iban = "DE89 3704 0044 0532 0130 00"
    kunde.save()
    client.post(reverse("invoicing:neu"), formular(kunde))

    rechnung = Rechnung.objects.get()
    text, xml = pdf_und_xml(rechnung, daten)
    assert f"Kunden-Nr. {kunde.kundennummer} eine Lastschriftermächtigung" in text
    assert "Mandatsreferenz" not in text
    assert "<ram:IBANID>DE89370400440532013000</ram:IBANID>" in xml


def test_ohne_glaeubiger_id_kein_festschreiben(client, firma, kunde):
    firma.glaeubiger_id = ""
    firma.save()
    antwort = client.post(reverse("invoicing:neu"), formular(kunde), follow=True)

    assert Rechnung.objects.get().ist_entwurf
    assert "Ihre Gläubiger-ID für die Lastschrift" in antwort.content.decode()


def test_ohne_mandat_kein_festschreiben(client, firma, kunde):
    kunde.mandat_referenz = ""
    kunde.mandat_datum = None
    kunde.save()
    antwort = client.post(reverse("invoicing:neu"), formular(kunde), follow=True)

    assert Rechnung.objects.get().ist_entwurf
    assert "SEPA-Mandat des Empfängers" in antwort.content.decode()


def test_xrechnung_mit_lastschrift_braucht_iban_des_kunden(client, firma, kunde):
    firma.telefon = "030 23125 100"
    firma.save()
    kunde.xrechnung = True
    kunde.kaeuferreferenz = "991-33333TEST-33"
    kunde.save()
    antwort = client.post(reverse("invoicing:neu"), formular(kunde), follow=True)

    assert Rechnung.objects.get().ist_entwurf
    assert "IBAN des Empfängers für die XRechnung" in antwort.content.decode()


def test_kein_skonto_bei_lastschrift(client, firma, kunde):
    antwort = client.post(
        reverse("invoicing:neu"),
        formular(kunde, skonto_prozent="2", skonto_tage="7"),
    )
    assert "Bei Lastschrift gibt es kein Skonto." in antwort.content.decode()
    assert not Rechnung.objects.exists()


def test_hinweis_auf_vorabinformation(client, firma, kunde):
    client.post(
        reverse("invoicing:neu"), formular(kunde, "speichern", zahlungsziel="7")
    )
    rechnung = Rechnung.objects.get()

    antwort = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk]))
    assert "14 Tage vorher vorliegen" in antwort.content.decode()


def test_storno_einer_lastschrift_erstattet_per_ueberweisung(
    client, firma, kunde, daten
):
    client.post(reverse("invoicing:neu"), formular(kunde))
    original = Rechnung.objects.get()
    client.post(reverse("invoicing:stornieren", args=[original.pk]))

    storno = Rechnung.objects.get(storno_zu=original)
    assert storno.zahlweg == Rechnung.Zahlweg.UEBERWEISUNG
    assert storno.beleg["lastschrift"] is None


def test_lastschrift_zahlung_merkt_den_letzten_einzug(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde))
    rechnung = Rechnung.objects.get()

    Zahlung.objects.create(
        rechnung=rechnung,
        datum=date(2026, 12, 1),
        betrag=Decimal("89.00"),
        art=Zahlung.Art.LASTSCHRIFT,
    )
    kunde.refresh_from_db()
    assert kunde.mandat_zuletzt == date(2026, 12, 1)

    # Eine nachgetragene ältere Zahlung setzt das Datum nicht zurück.
    Zahlung.objects.create(
        rechnung=rechnung,
        datum=date(2026, 6, 1),
        betrag=Decimal("0.01"),
        art=Zahlung.Art.LASTSCHRIFT,
    )
    kunde.refresh_from_db()
    assert kunde.mandat_zuletzt == date(2026, 12, 1)


def test_ueberweisung_aendert_das_mandat_nicht(client, firma, kunde, daten):
    client.post(reverse("invoicing:neu"), formular(kunde, zahlweg="ueberweisung"))
    rechnung = Rechnung.objects.get()
    Zahlung.objects.create(rechnung=rechnung, betrag=Decimal("89.00"))

    kunde.refresh_from_db()
    assert kunde.mandat_zuletzt is None
    text, xml = pdf_und_xml(rechnung, daten)
    assert "Bitte überweisen Sie den Betrag" in text
    assert "<ram:TypeCode>58</ram:TypeCode>" in xml
