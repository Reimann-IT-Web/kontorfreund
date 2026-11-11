"""Suche mit Strg+K (Spezifikation G-2) und Suche in der Adressliste."""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from angebote.models import Angebot
from auftraege.models import Auftragsbestaetigung
from contacts.models import Kontakt
from invoicing.models import Rechnung

pytestmark = pytest.mark.django_db


@pytest.fixture
def betreuung():
    """Eine von vielen Firmen gleichen Namens, erkennbar nur an der Person."""
    Kontakt.objects.create(art="firma", firmenname="Betreuung", ort="Mainz")
    return Kontakt.objects.create(
        art="firma",
        firmenname="Betreuung",
        anrede="Frau",
        vorname="Lena",
        nachname="Brandt",
        strasse="Rosengasse 7",
        plz="55232",
        ort="Alzey",
    )


def suchindex(client):
    return client.get("/").context["suchindex"]


def test_adresse_mit_ansprechpartner_und_strasse(client, betreuung):
    assert {
        "titel": "Betreuung",
        "info": "K-0002 · Lena Brandt · Rosengasse 7 · Alzey",
        "url": f"{reverse('contacts:liste')}?q=K-0002&offen={betreuung.pk}",
    } in suchindex(client)


def test_belege_mit_empfaenger(client, betreuung):
    Rechnung.objects.create(
        kontakt=betreuung,
        status=Rechnung.Status.FESTGESCHRIEBEN,
        nummer="260002",
        datum=date(2026, 11, 11),
    )
    entwurf = Rechnung.objects.create(kontakt=None, datum=date(2026, 11, 12))
    angebot = Angebot.objects.create(kontakt=betreuung, datum=date(2026, 10, 1))
    auftrag = Auftragsbestaetigung.objects.create(
        kontakt=betreuung, datum=date(2026, 10, 2)
    )

    index = suchindex(client)

    rechnung = next(e for e in index if e["titel"] == "Rechnung 260002")
    assert rechnung["info"] == "Betreuung · Lena Brandt · Alzey · 11.11.2026"
    assert {
        "titel": "Rechnung (Entwurf)",
        "info": "12.11.2026",
        "url": reverse("invoicing:bearbeiten", args=[entwurf.pk]),
    } in index
    assert {
        "titel": "Angebot (Entwurf)",
        "info": "Betreuung · Lena Brandt · Alzey · 01.10.2026",
        "url": reverse("angebote:bearbeiten", args=[angebot.pk]),
    } in index
    assert {
        "titel": "Auftragsbestätigung (Entwurf)",
        "info": "Betreuung · Lena Brandt · Alzey · 02.10.2026",
        "url": reverse("auftraege:bearbeiten", args=[auftrag.pk]),
    } in index


def test_stornorechnung_heisst_so(client, betreuung):
    original = Rechnung.objects.create(
        kontakt=betreuung, status=Rechnung.Status.FESTGESCHRIEBEN, nummer="260001"
    )
    Rechnung.objects.create(
        kontakt=betreuung,
        status=Rechnung.Status.FESTGESCHRIEBEN,
        nummer="260002",
        storno_zu=original,
    )

    titel = [e["titel"] for e in suchindex(client)]

    assert "Rechnung 260001" in titel and "Stornorechnung 260002" in titel


def test_belege_gesperrter_adressen_fehlen(client, betreuung):
    Rechnung.objects.create(kontakt=betreuung)
    Kontakt.objects.filter(pk=betreuung.pk).update(
        gesperrt_am=timezone.now(), archiviert=True
    )

    index = suchindex(client)

    assert not any("Brandt" in e["info"] for e in index)


def test_neueste_belege_je_art(client, betreuung, monkeypatch):
    from core import context_processors

    monkeypatch.setattr(context_processors, "BELEGE_IM_INDEX", 2)
    for tag in (1, 2, 3):
        Rechnung.objects.create(kontakt=betreuung, datum=date(2026, 11, tag))

    daten = [
        e["info"][-10:] for e in suchindex(client) if e["titel"] == "Rechnung (Entwurf)"
    ]

    assert daten == ["03.11.2026", "02.11.2026"]


def test_suche_fuehrt_in_alle_adressen(client, betreuung):
    html = client.get("/").text

    assert f'data-palette-alle="{reverse("contacts:liste")}"' in html
    assert "In allen Adressen suchen" in html


def test_adressliste_findet_strasse_und_ansprechpartner(client, betreuung):
    def treffer(q):
        return list(client.get(reverse("contacts:liste"), {"q": q}).context["kontakte"])

    assert treffer("rosengass") == [betreuung]
    assert treffer("Brandt") == [betreuung]


def test_empfaengerauswahl_unterscheidet_gleiche_namen(client, betreuung):
    for pfad in ("invoicing:neu", "angebote:neu", "auftraege:neu"):
        html = client.get(reverse(pfad)).text

        assert ">Betreuung – Lena Brandt, Alzey (K-0002)</option>" in html
        assert ">Betreuung – Mainz (K-0001)</option>" in html
