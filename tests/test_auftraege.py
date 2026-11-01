"""Auftragsbestätigung schreiben, aus dem Angebot machen und daraus die Rechnung – mit erfundenen Daten."""

import hashlib
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail.backends import locmem
from django.urls import reverse
from pypdf import PdfReader

from angebote.models import Angebot
from auftraege.models import Auftragsbestaetigung, Position
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import versand
from invoicing.models import Rechnung
from protokoll.models import Eintrag

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


def formular(kunde, aktion="fertigstellen", **mehr):
    return {
        "kontakt": kunde.pk,
        "datum": "2026-11-02",
        "leistung_von": "2026-11-09",
        "leistung_bis": "2026-11-13",
        "steuerfall": "kleinunternehmer",
        "betreff": "Neue Website",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Ich freue mich auf die Zusammenarbeit.",
        "bezeichnung": ["Webdesign", "Wartung", ""],
        "beschreibung": ["- Startseite\n- Galerie", "", ""],
        "menge": ["12", "1", "1"],
        "einheit": ["Std.", "Pauschale", "Stück"],
        "preis": ["80,00", "146,64", ""],
        "aktion": aktion,
        **mehr,
    }


def fertiger_auftrag(client, kunde, **mehr):
    client.post(reverse("auftraege:neu"), formular(kunde, **mehr))
    return Auftragsbestaetigung.objects.get()


def angebot_fertig(firma, kunde, nummer="260001"):
    angebot = Angebot.objects.create(
        kontakt=kunde, betreff="Neue Website", datum=date(2026, 10, 30)
    )
    angebot.positionen.create(
        nr=1, bezeichnung="Webdesign", menge=12, einheit="Std.", preis=80
    )
    Angebot.objects.filter(pk=angebot.pk).update(
        status=Angebot.Status.FERTIG, nummer=nummer
    )
    angebot.refresh_from_db()
    return angebot


def test_nummer_eigener_kreis():
    Rechnung.objects.create(nummer="260007", status=Rechnung.Status.FESTGESCHRIEBEN)
    Angebot.objects.create(nummer="260004", status=Angebot.Status.FERTIG)
    assert Auftragsbestaetigung.naechste_nummer(date(2026, 11, 2)) == "260001"
    Auftragsbestaetigung.objects.create(nummer="260001")
    assert Auftragsbestaetigung.naechste_nummer(date(2026, 11, 2)) == "260002"
    assert Auftragsbestaetigung.naechste_nummer(date(2027, 1, 2)) == "270001"


def test_neu_mit_vorbelegten_texten(client, firma, kunde):
    seite = client.get(reverse("auftraege:neu") + f"?empfaenger={kunde.pk}").text
    assert "Neue Auftragsbestätigung" in seite
    assert "Hiermit bestätige ich Ihnen folgende Leistungen" in seite
    assert "Ich freue mich auf die Zusammenarbeit" in seite
    assert 'data-beleg="auftrag"' in seite
    assert "Was liefern oder leisten Sie?" in seite


def test_fertigstellen_legt_pdf_ab(client, firma, kunde, settings):
    antwort = client.post(reverse("auftraege:neu"), formular(kunde))
    auftrag = Auftragsbestaetigung.objects.get()
    assert antwort.url == reverse("auftraege:bearbeiten", args=[auftrag.pk])
    assert auftrag.status == Auftragsbestaetigung.Status.FERTIG
    assert auftrag.nummer == "260001"
    # 12 × 80 € + 146,64 €, Kleinunternehmer ohne Umsatzsteuer
    assert auftrag.brutto == Decimal("1106.64")
    assert auftrag.positionen.count() == 2

    assert auftrag.datei == "archiv/auftraege/2026/Auftragsbestaetigung-260001.pdf"
    inhalt = (settings.DATA_DIR / auftrag.datei).read_bytes()
    assert hashlib.sha256(inhalt).hexdigest() == auftrag.sha256
    text = " ".join(PdfReader(BytesIO(inhalt)).pages[0].extract_text().split())
    assert "Auftragsbestätigung 260001" in text
    assert "09.11.2026 – 13.11.2026" in text
    assert "Auftragssumme" in text
    assert "§ 19 UStG" in text
    # Keine Rechnung: keine E-Rechnungsdaten und keine Zahlungsaufforderung.
    assert not PdfReader(BytesIO(inhalt)).attachments
    assert "Zahlbar" not in text

    ansicht = client.get(reverse("auftraege:bearbeiten", args=[auftrag.pk])).text
    assert "Rechnung erstellen" in ansicht
    assert "Offen" in ansicht


def test_fertig_ist_unveraenderbar(client, firma, kunde):
    auftrag = fertiger_auftrag(client, kunde)
    auftrag.betreff = "Anders"
    with pytest.raises(ValidationError):
        auftrag.save()
    with pytest.raises(ValidationError):
        auftrag.positionen.first().save()
    with pytest.raises(ValidationError):
        Position.objects.create(auftrag=auftrag, nr=3, bezeichnung="Nachtrag")
    with pytest.raises(ValidationError):
        auftrag.delete()
    client.post(
        reverse("auftraege:bearbeiten", args=[auftrag.pk]),
        formular(kunde, betreff="Geändert", aktion="speichern"),
    )
    auftrag.refresh_from_db()
    assert auftrag.betreff == "Neue Website"
    assert (
        client.post(reverse("auftraege:loeschen", args=[auftrag.pk])).status_code == 404
    )


def test_ausfuehrung_ist_freiwillig_aber_gueltig(client, firma, kunde):
    client.post(
        reverse("auftraege:neu"), formular(kunde, leistung_von="", leistung_bis="")
    )
    assert Auftragsbestaetigung.objects.get().nummer == "260001"
    antwort = client.post(
        reverse("auftraege:neu"),
        formular(kunde, leistung_von="2026-11-13", leistung_bis="2026-11-09"),
        follow=True,
    )
    assert "Ausführungszeitraum" in antwort.text
    assert Auftragsbestaetigung.objects.filter(nummer="").count() == 1


def test_unvollstaendig_bleibt_entwurf(client, kunde):
    antwort = client.post(reverse("auftraege:neu"), formular(kunde), follow=True)
    auftrag = Auftragsbestaetigung.objects.get()
    assert auftrag.ist_entwurf
    assert auftrag.nummer == ""
    assert "Ihre Firmendaten" in antwort.text


def test_entwurf_vorschau_und_loeschen(client, firma, kunde):
    antwort = client.post(reverse("auftraege:neu"), formular(kunde, aktion="vorschau"))
    auftrag = Auftragsbestaetigung.objects.get()
    assert antwort.url.endswith("?vorschau=1")
    seite = client.get(antwort.url).text
    assert seite.count('src="data:image/png;base64,') == 1
    entwurf = client.get(reverse("auftraege:pdf", args=[auftrag.pk]))
    assert entwurf["Content-Type"] == "application/pdf"
    assert (
        "Auftragsbestätigung (Entwurf)"
        in PdfReader(BytesIO(entwurf.content)).pages[0].extract_text()
    )
    client.post(reverse("auftraege:loeschen", args=[auftrag.pk]))
    assert not Auftragsbestaetigung.objects.exists()


def test_aus_angebot_dann_rechnung(client, firma, kunde, settings):
    angebot = angebot_fertig(firma, kunde)
    client.post(
        reverse("angebote:antwort", args=[angebot.pk]), {"antwort": "angenommen"}
    )
    seite = client.get(reverse("angebote:bearbeiten", args=[angebot.pk])).text
    assert "Auftrag bestätigen" in seite

    antwort = client.post(reverse("auftraege:aus_angebot", args=[angebot.pk]))
    auftrag = Auftragsbestaetigung.objects.get()
    assert antwort.url == reverse("auftraege:bearbeiten", args=[auftrag.pk])
    assert auftrag.ist_entwurf
    assert auftrag.angebot == angebot
    assert auftrag.kontakt == kunde
    assert auftrag.betreff == "Neue Website"
    assert "zu meinem Angebot 260001 vom 30.10.2026" in auftrag.kopftext
    assert [(p.bezeichnung, p.menge, p.preis) for p in auftrag.positionen.all()] == [
        ("Webdesign", Decimal("12"), Decimal("80"))
    ]
    angebot.refresh_from_db()
    assert angebot.antwort == Angebot.Antwort.ANGENOMMEN
    # Ein zweiter Klick legt keine zweite an, und die Rechnung kommt jetzt aus ihr.
    client.post(reverse("auftraege:aus_angebot", args=[angebot.pk]))
    assert Auftragsbestaetigung.objects.count() == 1
    weiter = client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    assert weiter.url == reverse("auftraege:bearbeiten", args=[auftrag.pk])
    assert not Rechnung.objects.exists()
    # Die Zusage lässt sich nicht mehr zurücknehmen.
    client.post(reverse("angebote:antwort", args=[angebot.pk]), {"antwort": ""})
    angebot.refresh_from_db()
    assert angebot.antwort == Angebot.Antwort.ANGENOMMEN
    assert "Zum Entwurf der Auftragsbestätigung" in (
        client.get(reverse("angebote:bearbeiten", args=[angebot.pk])).text
    )

    client.post(
        reverse("auftraege:bearbeiten", args=[auftrag.pk]),
        formular(kunde, kopftext=auftrag.kopftext),
    )
    auftrag.refresh_from_db()
    assert auftrag.nummer == "260001"
    text = (
        PdfReader(BytesIO((settings.DATA_DIR / auftrag.datei).read_bytes()))
        .pages[0]
        .extract_text()
    )
    assert "Zum Angebot" in text

    antwort = client.post(reverse("auftraege:rechnung_erstellen", args=[auftrag.pk]))
    rechnung = Rechnung.objects.get()
    assert antwort.url == reverse("invoicing:bearbeiten", args=[rechnung.pk])
    assert rechnung.ist_entwurf
    assert rechnung.kontakt == kunde
    assert rechnung.leistung_von == date(2026, 11, 9)
    assert rechnung.leistung_bis == date(2026, 11, 13)
    assert "Auftragsbestätigung 260001 vom 02.11.2026" in rechnung.kopftext
    assert rechnung.summen()[2] == auftrag.brutto
    auftrag.refresh_from_db()
    assert auftrag.rechnung == rechnung
    assert auftrag.stand == "berechnet"
    editor = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk])).text
    assert "Auftragsbestätigung 260001" in editor

    erneut = client.post(reverse("auftraege:rechnung_erstellen", args=[auftrag.pk]))
    assert erneut.url == reverse("invoicing:bearbeiten", args=[rechnung.pk])
    assert Rechnung.objects.count() == 1
    # Wird der Rechnungsentwurf gelöscht, lässt sich eine neue Rechnung erstellen.
    client.post(reverse("invoicing:loeschen", args=[rechnung.pk]))
    auftrag.refresh_from_db()
    assert auftrag.rechnung is None


def test_nicht_aus_abgelehntem_oder_berechnetem_angebot(client, firma, kunde):
    angebot = angebot_fertig(firma, kunde)
    client.post(
        reverse("angebote:antwort", args=[angebot.pk]), {"antwort": "abgelehnt"}
    )
    client.post(reverse("auftraege:aus_angebot", args=[angebot.pk]))
    assert not Auftragsbestaetigung.objects.exists()
    client.post(reverse("angebote:antwort", args=[angebot.pk]), {"antwort": ""})
    client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    client.post(reverse("auftraege:aus_angebot", args=[angebot.pk]))
    assert not Auftragsbestaetigung.objects.exists()
    zweites = angebot_fertig(firma, kunde, nummer="260002")
    client.post(reverse("auftraege:aus_angebot", args=[zweites.pk]))
    zweites.refresh_from_db()
    assert zweites.antwort == Angebot.Antwort.ANGENOMMEN
    assert zweites.auftrag
    # Entwürfe zählen nicht: aus einem Angebotsentwurf entsteht nichts.
    entwurf = Angebot.objects.create(kontakt=kunde)
    assert (
        client.post(reverse("auftraege:aus_angebot", args=[entwurf.pk])).status_code
        == 404
    )


def test_kopieren_fuer_geaenderte_fassung(client, firma, kunde):
    original = fertiger_auftrag(client, kunde)
    antwort = client.post(reverse("auftraege:kopieren", args=[original.pk]))
    kopie = Auftragsbestaetigung.objects.exclude(pk=original.pk).get()
    assert antwort.url == reverse("auftraege:bearbeiten", args=[kopie.pk])
    assert kopie.ist_entwurf
    assert kopie.datum == date.today()
    assert kopie.leistung_von == original.leistung_von
    assert kopie.positionen.count() == 2


def test_liste_umschalter_suche_und_verlauf(client, firma, kunde):
    fertiger_auftrag(client, kunde)
    liste = client.get(reverse("auftraege:liste")).text
    assert "260001" in liste
    assert "Muster Bäckerei GmbH" in liste
    assert 'aria-current="page"><span class="step-long">Auftragsbestätigungen' in liste
    assert reverse("auftraege:liste") in client.get(reverse("angebote:liste")).text
    assert "Neue Auftragsbestätigung" in client.get(reverse("core:start")).text
    verlauf = client.get(reverse("historie:verlauf", args=[kunde.pk])).text
    assert "Auftragsbestätigung 260001" in verlauf


def test_versand_mit_pdf_anhang(client, firma, kunde, monkeypatch):
    firma.mail_server = "smtp.muster.test"
    firma.save()
    monkeypatch.setattr(versand, "SmtpVersand", lambda **_: locmem.EmailBackend())
    auftrag = fertiger_auftrag(client, kunde)
    seite = client.get(reverse("auftraege:bearbeiten", args=[auftrag.pk])).text
    assert "Auftragsbestätigung 260001 vom 02.11.2026" in seite
    client.post(
        reverse("auftraege:bearbeiten", args=[auftrag.pk]),
        {
            "an": "buchhaltung@baeckerei.test",
            "betreff": "Auftragsbestätigung 260001",
            "text": "Anbei.",
            "kopie": "on",
        },
    )
    nachricht = mail.outbox[0]
    assert nachricht.attachments[0].filename == "Auftragsbestaetigung-260001.pdf"
    auftrag.refresh_from_db()
    assert auftrag.versendet_an == "buchhaltung@baeckerei.test"
    assert auftrag.stand == "versendet"


def test_im_protokoll(client, firma, kunde):
    auftrag = fertiger_auftrag(client, kunde)
    assert Eintrag.objects.filter(
        objekt_id=str(auftrag.pk), art="Auftragsbestätigung"
    ).exists()
