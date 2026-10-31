"""Umsatzgrenzen der Kleinunternehmerregelung (§ 19 UStG, Spezifikation B-4) – erfundene Daten."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from archive.models import Altbeleg
from contacts.models import Kontakt
from core import umsatz
from core.models import Firmendaten
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
    f.kleinunternehmer = True
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Muster GmbH", strasse="Lindenweg 4", plz="55116", ort="Mainz"
    )


def umsatz_bisher(betrag, jahr=2026):
    Altbeleg.objects.create(
        art=Altbeleg.Art.RECHNUNG,
        nummer=f"{jahr}-{betrag}",
        datum=date(jahr, 3, 1),
        absender="Muster IT",
        betrag=Decimal(betrag),
        sha256=f"{jahr}{betrag}".ljust(64, "0"),
    )


def rechnung(
    client, kunde, preis, aktion="festschreiben", steuerfall="kleinunternehmer"
):
    return client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": "2026-10-29",
            "leistung_von": "2026-10-01",
            "zahlungsziel": "14",
            "steuerfall": steuerfall,
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["1"],
            "einheit": ["Pauschale"],
            "preis": [preis],
            "aktion": aktion,
        },
        follow=True,
    )


def test_umsatz_aus_altbelegen_und_rechnungen(client, firma, kunde):
    umsatz_bisher("1000.00")
    umsatz_bisher("500.00", jahr=2025)
    rechnung(client, kunde, "2.000,00")
    assert umsatz.umsatz(2026) == Decimal("3000.00")
    assert umsatz.umsatz(2025) == Decimal("500.00")


@pytest.mark.parametrize(
    ("bisher", "dazu", "erwartet"),
    [
        ("10000.00", "0", None),
        ("19000.00", "1000", "80 % von 25.000,00"),
        ("26000.00", "0", "Ab 2027 gilt die Kleinunternehmerregelung"),
        ("79000.00", "1000", "80 % von 100.000,00"),
        ("99000.00", "2000", "Schon dieser Umsatz unterliegt der Regelbesteuerung"),
    ],
)
def test_hinweise_ab_80_prozent(bisher, dazu, erwartet):
    umsatz_bisher(bisher)
    texte = umsatz.hinweise(2026, Decimal(dazu))
    if erwartet is None:
        assert texte == []
    else:
        assert len(texte) == 1 and erwartet in texte[0].replace("\xa0", " ")


def test_vorjahr_ueber_25000(firma):
    umsatz_bisher("25000.01", jahr=2025)
    (text,) = umsatz.hinweise(2026)
    assert "Damit gilt die Kleinunternehmerregelung 2026 nicht" in text


def test_warnung_im_editor_und_nach_dem_festschreiben(client, firma, kunde):
    umsatz_bisher("19000.00")
    antwort = rechnung(client, kunde, "1.500,00", aktion="speichern")
    assert "Mit dieser Rechnung erreicht Ihr Umsatz 2026" in antwort.content.decode()

    entwurf = Rechnung.objects.get()
    antwort = client.post(
        reverse("invoicing:bearbeiten", args=[entwurf.pk]),
        {
            "kontakt": kunde.pk,
            "datum": "2026-10-29",
            "leistung_von": "2026-10-01",
            "zahlungsziel": "14",
            "steuerfall": "kleinunternehmer",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["1"],
            "einheit": ["Pauschale"],
            "preis": ["1.500,00"],
            "aktion": "festschreiben",
        },
        follow=True,
    )
    seite = antwort.content.decode()
    assert "ist festgeschrieben" in seite
    assert "Ihr Umsatz 2026 erreicht" in seite
    assert (
        "Kleinunternehmergrenze" in client.get(reverse("core:start")).content.decode()
    )
    assert (
        "Ihr Umsatz 2026 erreicht" in client.get(reverse("core:start")).content.decode()
    )


def test_ueber_100000_nur_mit_umsatzsteuer(client, firma, kunde):
    umsatz_bisher("99500.00")
    antwort = rechnung(client, kunde, "1.000,00")
    assert "Sie muss deshalb Umsatzsteuer ausweisen" in antwort.content.decode()
    assert Rechnung.objects.get().ist_entwurf

    rechnung(client, kunde, "1.000,00", steuerfall="regel")
    assert Rechnung.objects.filter(status=Rechnung.Status.FESTGESCHRIEBEN).count() == 1
