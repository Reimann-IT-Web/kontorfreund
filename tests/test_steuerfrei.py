"""Steuerfreie Leistungen und Auswahl der Umsatzsteuer (Spezifikation B-4) – erfundene Daten."""

from datetime import date
from io import BytesIO

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse
from pypdf import PdfReader

from angebote.models import Angebot
from auftraege.models import Auftragsbestaetigung
from auswertungen import buch
from auswertungen.models import Datev
from contacts.models import Kontakt
from core import umsatz
from core.models import Firmendaten
from dokumentation import fassungen
from dokumentation.models import Fassung
from invoicing.models import Rechnung

pytestmark = pytest.mark.django_db

HINWEIS = "Umsatzsteuerfrei nach § 4 Nr. 21 UStG"


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster Fortbildung"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.email = "post@muster.test"
    f.iban = "DE02120300000000202051"
    f.umsatzsteuer = Firmendaten.Umsatzsteuer.STEUERFREI
    f.steuerfrei_hinweis = HINWEIS
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Betreuungsverein Muster e. V.",
        strasse="Lindenweg 4",
        plz="55116",
        ort="Mainz",
        email="buero@verein.test",
    )


def formular(kunde, aktion="festschreiben", **mehr):
    return {
        "kontakt": kunde.pk,
        "datum": "2026-10-29",
        "leistung_von": "2026-10-01",
        "zahlungsziel": "14",
        "steuerfall": "steuerfrei",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Mit freundlichen Grüßen",
        "bezeichnung": ["Fortbildung Betreuungsrecht"],
        "beschreibung": [""],
        "menge": ["1"],
        "einheit": [""],
        "preis": ["450,00"],
        "aktion": aktion,
        **mehr,
    }


def festschreiben(client, kunde, **mehr):
    client.post(reverse("invoicing:neu"), formular(kunde, **mehr))
    return Rechnung.objects.latest("pk")


def pdf(settings, beleg):
    return PdfReader(BytesIO((settings.DATA_DIR / beleg.datei).read_bytes()))


def seitentext(settings, beleg):
    return " ".join(pdf(settings, beleg).pages[0].extract_text().split())


def einstellungen(firma, **mehr):
    werte = {
        f: getattr(firma, f)
        for f in ("name", "strasse", "plz", "ort", "steuernummer", "email", "iban")
    }
    return {
        **werte,
        "mail_port": "587",
        "mail_verschluesselung": "starttls",
        **mehr,
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("kleinunternehmer", "erwartet"),
    [(True, "kleinunternehmer"), (False, "regel")],
)
def test_umstellung_behaelt_die_bisherige_wahl(kleinunternehmer, erwartet):
    alt = [("core", "0007_firmendaten_zahlungstext")]
    executor = MigrationExecutor(connection)
    executor.migrate(alt)
    apps = executor.loader.project_state(alt).apps
    apps.get_model("core", "Firmendaten").objects.create(
        pk=1, name="Muster IT", kleinunternehmer=kleinunternehmer
    )

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())

    firma = Firmendaten.laden()
    assert firma.umsatzsteuer == erwartet
    assert firma.kleinunternehmer is kleinunternehmer
    assert firma.steuerfrei_hinweis == ""


def test_einstellungen_zeigen_die_auswahl(client, firma):
    seite = client.get(reverse("core:einstellungen")).text

    assert "Umsatzsteuer auf Ihren Belegen" in seite
    for wahl in ("kleinunternehmer", "regel", "steuerfrei"):
        assert f'value="{wahl}"' in seite
    assert "Grenzen von 25.000 € und 100.000 €" in seite
    assert HINWEIS in seite


def test_steuerfrei_verlangt_einen_hinweis(client, firma):
    antwort = client.post(
        reverse("core:einstellungen"),
        einstellungen(firma, umsatzsteuer="steuerfrei", steuerfrei_hinweis="  "),
    )

    assert antwort.status_code == 200
    assert "welcher Hinweis auf steuerfreien Belegen" in antwort.text
    assert Firmendaten.laden().steuerfrei_hinweis == HINWEIS


def test_kleinunternehmer_braucht_keinen_hinweis(client, firma):
    antwort = client.post(
        reverse("core:einstellungen"),
        einstellungen(firma, umsatzsteuer="kleinunternehmer", steuerfrei_hinweis=""),
    )

    assert antwort.status_code == 302
    gespeichert = Firmendaten.laden()
    assert gespeichert.kleinunternehmer
    assert gespeichert.steuerfrei_hinweis == ""


@pytest.mark.parametrize(
    ("wahl", "erwartet"),
    [
        ("steuerfrei", "steuerfrei"),
        ("kleinunternehmer", "kleinunternehmer"),
        ("regel", "regel"),
    ],
)
def test_neue_belege_nehmen_die_wahl_der_firma(client, firma, wahl, erwartet):
    firma.umsatzsteuer = wahl
    firma.save()

    for adresse in ("invoicing:neu", "angebote:neu", "auftraege:neu"):
        form = client.get(reverse(adresse)).context["form"]
        assert form["steuerfall"].value() == erwartet, adresse


def test_steuerfreie_rechnung_in_pdf_und_xml(client, firma, kunde, settings):
    rechnung = festschreiben(client, kunde)

    assert not rechnung.ist_entwurf
    assert rechnung.beleg["steuerhinweis"] == HINWEIS
    text = seitentext(settings, rechnung)
    assert HINWEIS in text
    assert "Umsatzsteuer 19 %" not in text
    assert "450,00 €" in text
    xml = pdf(settings, rechnung).attachments["factur-x.xml"][0].decode()
    assert "<ram:CategoryCode>E</ram:CategoryCode>" in xml
    assert f"<ram:ExemptionReason>{HINWEIS}</ram:ExemptionReason>" in xml
    assert "ExemptionReasonCode" not in xml
    assert '<ram:TaxTotalAmount currencyID="EUR">0.00</ram:TaxTotalAmount>' in xml


def test_ohne_hinweis_kein_festschreiben(client, firma, kunde):
    firma.umsatzsteuer = Firmendaten.Umsatzsteuer.KLEINUNTERNEHMER
    firma.steuerfrei_hinweis = ""
    firma.save()

    antwort = client.post(reverse("invoicing:neu"), formular(kunde), follow=True)

    rechnung = Rechnung.objects.get()
    assert rechnung.ist_entwurf
    assert "Noch nicht vollständig: Hinweis auf die Steuerbefreiung" in antwort.text
    # Die Prüfliste im Editor nennt den Weg in die Einstellungen.
    assert "data-steuerfrei-fehlt" in antwort.text
    assert 'data-steuerfrei=""' in antwort.text


def test_storno_und_korrektur_behalten_den_hinweis(client, firma, kunde, settings):
    original = festschreiben(client, kunde)
    zweite = festschreiben(client, kunde)
    # Der Hinweis in den Firmendaten ändert sich danach oder fehlt ganz.
    firma.steuerfrei_hinweis = ""
    firma.save()

    client.post(reverse("invoicing:stornieren", args=[original.pk]))
    storno = Rechnung.objects.get(storno_zu=original)
    client.post(reverse("invoicing:korrigieren", args=[zweite.pk]))
    entwurf = Rechnung.objects.get(korrektur_zu=zweite)
    editor = client.get(reverse("invoicing:bearbeiten", args=[entwurf.pk])).text
    client.post(
        reverse("invoicing:bearbeiten", args=[entwurf.pk]),
        formular(kunde, menge=["-0,5"]),
    )
    korrektur = Rechnung.objects.get(korrektur_zu=zweite)

    assert f'data-steuerfrei="{HINWEIS}"' in editor
    for beleg in (storno, korrektur):
        assert not beleg.ist_entwurf
        assert beleg.beleg["steuerhinweis"] == HINWEIS
        assert HINWEIS in seitentext(settings, beleg)


def test_steuerfreie_rechnungen_zaehlen_nicht_zur_grenze(client, firma, kunde):
    festschreiben(client, kunde)
    assert umsatz.umsatz(2026) == 0

    festschreiben(client, kunde, steuerfall="kleinunternehmer")
    assert umsatz.umsatz(2026) == 450


def test_hinweise_zur_grenze_nur_fuer_kleinunternehmer(client, firma):
    assert "Kleinunternehmergrenze" not in client.get(reverse("core:start")).text

    firma.umsatzsteuer = Firmendaten.Umsatzsteuer.KLEINUNTERNEHMER
    firma.save()
    assert "Kleinunternehmergrenze" in client.get(reverse("core:start")).text


def test_angebot_und_auftrag_mit_hinweis(client, firma, kunde, settings):
    gemeinsam = {
        "kontakt": kunde.pk,
        "datum": "2026-10-30",
        "steuerfall": "steuerfrei",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Mit freundlichen Grüßen",
        "bezeichnung": ["Fortbildung Betreuungsrecht"],
        "beschreibung": [""],
        "menge": ["1"],
        "einheit": [""],
        "preis": ["450,00"],
        "aktion": "fertigstellen",
    }
    client.post(reverse("angebote:neu"), {**gemeinsam, "bindefrist": "30"})
    client.post(reverse("auftraege:neu"), gemeinsam)

    for beleg in (Angebot.objects.get(), Auftragsbestaetigung.objects.get()):
        assert beleg.nummer, beleg
        assert beleg.beleg["steuerhinweis"] == HINWEIS
        assert HINWEIS in seitentext(settings, beleg)


def test_angebot_ohne_hinweis_bleibt_entwurf(client, firma, kunde):
    firma.steuerfrei_hinweis = ""
    firma.save()

    antwort = client.post(
        reverse("angebote:neu"),
        {
            "kontakt": kunde.pk,
            "datum": "2026-10-30",
            "bindefrist": "30",
            "steuerfall": "steuerfrei",
            "bezeichnung": ["Fortbildung"],
            "beschreibung": [""],
            "menge": ["1"],
            "einheit": [""],
            "preis": ["450,00"],
            "aktion": "fertigstellen",
        },
        follow=True,
    )

    assert not Angebot.objects.get().nummer
    assert "Hinweis auf die Steuerbefreiung" in antwort.text


@pytest.mark.parametrize(("skr", "konto"), [("03", 8100), ("04", 4100)])
def test_datev_erloeskonto(skr, konto):
    datev = Datev.laden()
    datev.kontenrahmen = skr
    assert datev.erloeskonto(Rechnung.Steuerfall.STEUERFREI) == konto
    datev.erloes_steuerfrei = 8110
    assert datev.erloeskonto(Rechnung.Steuerfall.STEUERFREI) == 8110


def test_ausgangsbuch_nennt_steuerfrei(client, firma, kunde):
    festschreiben(client, kunde)

    ((zeile, _),) = buch.zeilen(date(2026, 1, 1), date(2026, 12, 31))
    assert zeile.steuer == "steuerfrei"


def test_verfahrensdokumentation_nennt_den_hinweis(firma):
    text = str(fassungen.entwurf(Fassung.Art.VERFAHREN))

    assert f"Steuerfreie Leistungen nach § 4 UStG mit dem Hinweis „{HINWEIS}“" in text
    assert "Kleinunternehmer" not in text
