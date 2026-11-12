"""Angebot schreiben, fertigstellen und daraus die Rechnung machen – mit erfundenen Daten."""

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.mail.backends import locmem
from django.urls import reverse
from pypdf import PdfReader

from angebote.models import Angebot, Position
from archive.models import Altbeleg
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import versand
from invoicing.models import Rechnung

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
        "datum": "2026-10-30",
        "bindefrist": "30",
        "steuerfall": "kleinunternehmer",
        "betreff": "Neue Website",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Über Ihren Auftrag freue ich mich.",
        "bezeichnung": ["Webdesign", "Wartung", ""],
        "beschreibung": ["- Startseite\n- Galerie", "", ""],
        "menge": ["12", "1", "1"],
        "einheit": ["Std.", "Pauschale", "Stück"],
        "preis": ["80,00", "146,64", ""],
        "aktion": aktion,
        **mehr,
    }


def fertiges_angebot(client, kunde, **mehr):
    client.post(reverse("angebote:neu"), formular(kunde, **mehr))
    return Angebot.objects.get()


def test_nummer_eigener_kreis_nach_altangeboten():
    for nummer in ("260003", "260001"):
        Altbeleg.objects.create(
            art=Altbeleg.Art.ANGEBOT,
            nummer=nummer,
            datum=date(2026, 3, 1),
            datei=f"a/{nummer}.pdf",
            sha256=nummer * 10,
            originalname=f"{nummer}.pdf",
        )
    # Rechnungsnummern zählen nicht mit: eigener Nummernkreis je Belegart.
    Altbeleg.objects.create(
        art=Altbeleg.Art.RECHNUNG,
        nummer="260007",
        datum=date(2026, 3, 1),
        datei="r/260007.pdf",
        sha256="r" * 64,
        originalname="260007.pdf",
    )
    assert Angebot.naechste_nummer(date(2026, 10, 30)) == "260004"
    assert Angebot.naechste_nummer(date(2027, 1, 2)) == "270001"


def test_rabatt_geht_vom_angebot_in_die_rechnung(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde, rabatt_prozent="6")
    assert angebot.rabatt_prozent == Decimal("6")
    assert angebot.beleg["rabatt"]["prozent"] == "6.00"
    netto = Decimal(angebot.beleg["rabatt"]["zwischensumme"]) - Decimal(
        angebot.beleg["rabatt"]["betrag"]
    )
    assert angebot.netto == netto

    client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    rechnung = Rechnung.objects.get()
    assert rechnung.rabatt_prozent == Decimal("6")
    assert rechnung.summen()[2] == angebot.brutto


def test_neues_angebot_mit_vorbelegten_texten(client, firma, kunde):
    seite = client.get(reverse("angebote:neu") + f"?empfaenger={kunde.pk}").text
    assert "Neues Angebot" in seite
    assert "Gerne biete ich Ihnen folgende Leistungen an" in seite
    assert "Über Ihren Auftrag freue ich mich" in seite
    assert 'data-beleg="angebot"' in seite


def test_fertigstellen_legt_pdf_ab(client, firma, kunde, settings):
    antwort = client.post(reverse("angebote:neu"), formular(kunde))
    angebot = Angebot.objects.get()
    assert antwort.url == reverse("angebote:bearbeiten", args=[angebot.pk])
    assert angebot.status == Angebot.Status.FERTIG
    assert angebot.nummer == "260001"
    # 12 × 80 € + 146,64 €, Kleinunternehmer ohne Umsatzsteuer
    assert angebot.brutto == Decimal("1106.64")
    assert angebot.gueltig_bis == date(2026, 11, 29)
    assert angebot.positionen.count() == 2

    pfad = settings.DATA_DIR / angebot.datei
    assert angebot.datei == "archiv/angebote/2026/Angebot-260001.pdf"
    inhalt = pfad.read_bytes()
    assert hashlib.sha256(inhalt).hexdigest() == angebot.sha256
    text = PdfReader(BytesIO(inhalt)).pages[0].extract_text()
    assert "Angebot 260001" in text
    assert "29.11.2026" in text
    assert "§ 19 UStG" in text
    # Ein Angebot ist keine Rechnung: keine E-Rechnungsdaten im PDF.
    assert not PdfReader(BytesIO(inhalt)).attachments

    ansicht = client.get(reverse("angebote:bearbeiten", args=[angebot.pk])).text
    assert "Antwort des Kunden" in ansicht
    assert "Angenommen" in ansicht


def test_fertiges_angebot_ist_unveraenderbar(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde)
    angebot.betreff = "Anders"
    with pytest.raises(ValidationError):
        angebot.save()
    with pytest.raises(ValidationError):
        angebot.positionen.first().save()
    with pytest.raises(ValidationError):
        angebot.delete()
    # Ein weiterer POST auf die Ansicht ändert nichts am Angebot.
    client.post(
        reverse("angebote:bearbeiten", args=[angebot.pk]),
        formular(kunde, betreff="Geändert", aktion="speichern"),
    )
    angebot.refresh_from_db()
    assert angebot.betreff == "Neue Website"
    assert (
        client.post(reverse("angebote:loeschen", args=[angebot.pk])).status_code == 404
    )


def test_unvollstaendig_bleibt_entwurf(client, kunde):
    antwort = client.post(reverse("angebote:neu"), formular(kunde), follow=True)
    angebot = Angebot.objects.get()
    assert angebot.ist_entwurf
    assert angebot.nummer == ""
    assert "Ihre Firmendaten" in antwort.text


def test_entwurf_vorschau_und_loeschen(client, firma, kunde):
    antwort = client.post(reverse("angebote:neu"), formular(kunde, aktion="vorschau"))
    angebot = Angebot.objects.get()
    assert antwort.url.endswith("?vorschau=1")
    seite = client.get(antwort.url).text
    assert seite.count('src="data:image/png;base64,') == 1
    entwurf = client.get(reverse("angebote:pdf", args=[angebot.pk]))
    assert entwurf["Content-Type"] == "application/pdf"
    assert (
        "Angebot (Entwurf)"
        in PdfReader(BytesIO(entwurf.content)).pages[0].extract_text()
    )
    client.post(reverse("angebote:loeschen", args=[angebot.pk]))
    assert not Angebot.objects.exists()


def test_angenommen_dann_rechnung_erstellen(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde)
    client.post(
        reverse("angebote:antwort", args=[angebot.pk]), {"antwort": "angenommen"}
    )
    angebot.refresh_from_db()
    assert angebot.antwort == Angebot.Antwort.ANGENOMMEN
    assert angebot.antwort_am == date.today()
    assert (
        "Rechnung erstellen"
        in client.get(reverse("angebote:bearbeiten", args=[angebot.pk])).text
    )

    antwort = client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    rechnung = Rechnung.objects.get()
    assert antwort.url == reverse("invoicing:bearbeiten", args=[rechnung.pk])
    assert rechnung.ist_entwurf
    assert rechnung.kontakt == kunde
    assert rechnung.betreff == "Neue Website"
    assert rechnung.steuerfall == angebot.steuerfall
    assert "Angebot 260001 vom 30.10.2026" in rechnung.kopftext
    assert [
        (p.bezeichnung, p.beschreibung, p.menge, p.einheit, p.preis)
        for p in rechnung.positionen.all()
    ] == [
        ("Webdesign", "- Startseite\n- Galerie", Decimal("12"), "Std.", Decimal("80")),
        ("Wartung", "", Decimal("1"), "Pauschale", Decimal("146.64")),
    ]
    assert rechnung.summen()[2] == angebot.brutto
    angebot.refresh_from_db()
    assert angebot.rechnung == rechnung

    editor = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk])).text
    assert "Angebot 260001" in editor
    assert "Leistungszeitraum ein" in editor

    # Ein zweiter Klick legt keine zweite Rechnung an.
    erneut = client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    assert erneut.url == reverse("invoicing:bearbeiten", args=[rechnung.pk])
    assert Rechnung.objects.count() == 1
    # Mit Rechnung lässt sich die Zusage nicht mehr zurücknehmen.
    client.post(reverse("angebote:antwort", args=[angebot.pk]), {"antwort": ""})
    angebot.refresh_from_db()
    assert angebot.antwort == Angebot.Antwort.ANGENOMMEN


def test_rechnung_direkt_vermerkt_zusage(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde)
    client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    angebot.refresh_from_db()
    assert angebot.antwort == Angebot.Antwort.ANGENOMMEN
    # Wird der Rechnungsentwurf gelöscht, lässt sich eine neue Rechnung erstellen.
    client.post(reverse("invoicing:loeschen", args=[angebot.rechnung.pk]))
    angebot.refresh_from_db()
    assert angebot.rechnung is None
    client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    assert Rechnung.objects.count() == 1


def test_abgelehnt_und_zuruecknehmen(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde)
    url = reverse("angebote:antwort", args=[angebot.pk])
    client.post(url, {"antwort": "abgelehnt"})
    angebot.refresh_from_db()
    assert angebot.stand == "abgelehnt"
    client.post(reverse("angebote:rechnung_erstellen", args=[angebot.pk]))
    assert not Rechnung.objects.exists()
    client.post(url, {"antwort": ""})
    angebot.refresh_from_db()
    assert angebot.antwort == ""
    assert angebot.antwort_am is None
    assert client.post(url, {"antwort": "vielleicht"}).status_code == 404


def test_abgelaufen_und_auf_der_uebersicht(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde, datum=str(date.today()))
    start = client.get(reverse("core:start")).text
    assert "Offene Angebote" in start
    assert f"Angebot {angebot.nummer} vom" in start
    assert angebot.stand == "offen"

    Angebot.objects.filter(pk=angebot.pk).update(
        datum=date.today() - timedelta(days=31)
    )
    angebot.refresh_from_db()
    assert angebot.abgelaufen
    assert angebot.stand == "abgelaufen"
    assert "Abgelaufen" in client.get(reverse("core:start")).text

    client.post(
        reverse("angebote:antwort", args=[angebot.pk]), {"antwort": "abgelehnt"}
    )
    assert "Offene Angebote" not in client.get(reverse("core:start")).text


def test_kopieren_fuer_geaenderte_fassung(client, firma, kunde):
    original = fertiges_angebot(client, kunde)
    antwort = client.post(reverse("angebote:kopieren", args=[original.pk]))
    kopie = Angebot.objects.exclude(pk=original.pk).get()
    assert antwort.url == reverse("angebote:bearbeiten", args=[kopie.pk])
    assert kopie.ist_entwurf
    assert kopie.datum == date.today()
    assert kopie.betreff == original.betreff
    assert kopie.positionen.count() == 2


def test_liste_mit_umschalter(client, firma, kunde):
    fertiges_angebot(client, kunde)
    liste = client.get(reverse("angebote:liste")).text
    assert "260001" in liste
    assert "Muster Bäckerei GmbH" in liste
    assert 'aria-current="page">Angebote' in liste
    rechnungen = client.get(reverse("invoicing:liste")).text
    assert 'aria-current="page">Rechnungen' in rechnungen
    assert reverse("angebote:neu") in rechnungen


def test_versand_mit_pdf_anhang(client, firma, kunde, monkeypatch):
    firma.mail_server = "smtp.muster.test"
    firma.save()
    monkeypatch.setattr(versand, "SmtpVersand", lambda **_: locmem.EmailBackend())
    angebot = fertiges_angebot(client, kunde)
    seite = client.get(reverse("angebote:bearbeiten", args=[angebot.pk])).text
    assert "Es gilt bis zum 29.11.2026" in seite
    client.post(
        reverse("angebote:bearbeiten", args=[angebot.pk]),
        {
            "an": "buchhaltung@baeckerei.test",
            "betreff": "Angebot 260001",
            "text": "Anbei.",
            "kopie": "on",
        },
    )
    nachricht = mail.outbox[0]
    assert nachricht.attachments[0].filename == "Angebot-260001.pdf"
    angebot.refresh_from_db()
    assert angebot.versendet_an == "buchhaltung@baeckerei.test"
    assert angebot.stand == "versendet"


def test_position_gesperrt_nach_fertigstellen(client, firma, kunde):
    angebot = fertiges_angebot(client, kunde)
    with pytest.raises(ValidationError):
        Position.objects.create(angebot=angebot, nr=3, bezeichnung="Nachtrag")
