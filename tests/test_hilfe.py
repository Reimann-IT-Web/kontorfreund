"""Hilfe: Übersicht mit häufigen Fragen und eine Anleitung je Bereich."""

import re

import pytest
from django.urls import reverse

from core.hilfe import THEMEN
from konten.models import Benutzer


def seite(client, *args):
    name = "core:hilfe_thema" if args else "core:hilfe"
    antwort = client.get(reverse(name, args=args))
    assert antwort.status_code == 200
    return antwort.content.decode()


def test_uebersicht_verlinkt_alle_themen(client):
    html = seite(client)
    for t in THEMEN:
        assert reverse("core:hilfe_thema", args=[t["slug"]]) in html
    assert "Häufige Fragen" in html
    # In der Seitenleiste ist die Hilfe als aktuelle Seite markiert.
    assert re.search(r'href="/hilfe/" aria-current="page"', html)


@pytest.mark.parametrize("thema", THEMEN, ids=[t["slug"] for t in THEMEN])
def test_jede_anleitung(client, thema):
    html = seite(client, thema["slug"])
    assert f"<h1>{thema['titel']}</h1>" in html
    assert html.count("<h2") >= 2


def test_blaettern(client):
    erste = seite(client, THEMEN[0]["slug"])
    assert "Vorheriges Thema" not in erste
    assert f"Nächstes Thema</span>{THEMEN[1]['titel']}" in erste
    letzte = seite(client, THEMEN[-1]["slug"])
    assert f"Vorheriges Thema</span>{THEMEN[-2]['titel']}" in letzte
    assert "Nächstes Thema" not in letzte


def test_spruenge_zu_abschnitten_haben_ein_ziel(client):
    seiten = [seite(client)] + [seite(client, t["slug"]) for t in THEMEN]
    spruenge = {
        treffer
        for html in seiten
        for treffer in re.findall(r'href="(/hilfe/[^"#]+)#([^"]+)"', html)
    }
    assert spruenge
    for pfad, anker in spruenge:
        assert f'id="{anker}"' in client.get(pfad).content.decode(), (pfad, anker)


def test_themen_in_der_suche(client):
    html = seite(client, "erste-schritte")
    assert (
        f'<a href="{reverse("core:hilfe_thema", args=["rechnungen"])}">'
        "<span>Hilfe: Rechnungen</span>"
    ) in html


def test_unbekanntes_thema(client):
    antwort = client.get(reverse("core:hilfe_thema", args=["gibt-es-nicht"]))
    assert antwort.status_code == 404


@pytest.mark.django_db
def test_auch_fuer_mitarbeiter(anonym):
    anonym.force_login(
        Benutzer.objects.create_user(
            "mitarbeiter@muster.test", name="Mia", rolle=Benutzer.Rolle.MITARBEITER
        )
    )
    assert "Häufige Fragen" in seite(anonym)
    assert "<h1>Rechnungen</h1>" in seite(anonym, "rechnungen")
