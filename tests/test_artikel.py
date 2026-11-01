"""Artikel und Leistungen (Spezifikation B-1) – mit erfundenen Daten."""

from decimal import Decimal

import pytest
from django.urls import reverse

from artikel.models import Artikel

pytestmark = pytest.mark.django_db


def anlegen(client, **daten):
    return client.post(
        reverse("artikel:neu"),
        {
            "bezeichnung": "Stundensatz Gartenpflege",
            "beschreibung": "",
            "einheit": "Std.",
            "preis": "45,00",
            **daten,
        },
    )


def test_artikel_anlegen_und_aendern(client):
    antwort = anlegen(
        client,
        bezeichnung="Pflegevertrag halbjährlich",
        beschreibung="- Rasen mähen\n- Hecke schneiden",
        einheit="Pauschale",
        preis="1.250,50",
    )

    assert antwort.url == reverse("artikel:liste")
    artikel = Artikel.objects.get()
    assert artikel.artikelnummer == "A-0001"
    assert artikel.preis == Decimal("1250.50")
    liste = client.get(reverse("artikel:liste")).text
    assert "Pflegevertrag halbjährlich" in liste and "1.250,50" in liste

    seite = reverse("artikel:bearbeiten", args=[artikel.pk])
    assert 'value="1250,50"' in client.get(seite).text
    client.post(
        seite,
        {"bezeichnung": artikel.bezeichnung, "einheit": "Pauschale", "preis": "1300"},
    )
    artikel.refresh_from_db()
    assert artikel.preis == Decimal("1300.00") and artikel.beschreibung == ""


@pytest.mark.parametrize("preis", ["-5", "zehn", ""])
def test_ungueltiger_preis(client, preis):
    antwort = anlegen(client, preis=preis)

    assert antwort.status_code == 200
    assert not Artikel.objects.exists()


def test_rechnung_bietet_nur_aktive_artikel_an(client):
    leer = client.get(reverse("invoicing:neu")).text
    assert "data-artikel-menue" not in leer and "unter <a" in leer
    anlegen(client, bezeichnung="Stundensatz Gartenpflege", preis="45")
    anlegen(client, bezeichnung="Alter Stundensatz", preis="40")
    alt = Artikel.objects.get(bezeichnung="Alter Stundensatz")
    client.post(reverse("artikel:aktiv", args=[alt.pk]), follow=True)

    seite = client.get(reverse("invoicing:neu")).text

    assert 'data-bezeichnung="Stundensatz Gartenpflege"' in seite
    assert 'data-einheit="Std." data-preis="45,00"' in seite
    assert "Alter Stundensatz" not in seite
    # In der Liste stehen inaktive Artikel nur unter „inaktiv“.
    assert alt not in client.get("/artikel/").context["artikel"]
    assert list(client.get("/artikel/", {"inaktiv": "1"}).context["artikel"]) == [alt]


def test_auswahl_beim_tippen_der_bezeichnung(client):
    seiten = [reverse(f"{app}:neu") for app in ("invoicing", "angebote", "auftraege")]
    for seite in seiten:
        assert 'list="artikel-liste"' not in client.get(seite).text
    anlegen(client, bezeichnung="Stundensatz Gartenpflege", preis="45")
    anlegen(client, bezeichnung="Alter Stundensatz", preis="40")
    alt = Artikel.objects.get(bezeichnung="Alter Stundensatz")
    client.post(reverse("artikel:aktiv", args=[alt.pk]), follow=True)

    for seite in seiten:
        html = client.get(seite).text
        # Jede Position, auch die Vorlage für neue, bietet die Artikel an.
        assert html.count('list="artikel-liste"') == 2
        assert (
            '<option value="Stundensatz Gartenpflege" data-beschreibung="" '
            'data-einheit="Std." data-preis="45,00">45,00' in html
        )
        assert 'value="Alter Stundensatz"' not in html


def test_artikel_suchen(client):
    anlegen(client, bezeichnung="Stundensatz Gartenpflege")
    anlegen(client, bezeichnung="Baumschnitt", beschreibung="bis 5 m Höhe")

    gartenpflege, baumschnitt = Artikel.objects.order_by("nummer")

    def treffer(q):
        return list(client.get("/artikel/", {"q": q}).context["artikel"])

    assert treffer("höhe") == [baumschnitt]
    assert treffer("A-0001") == treffer("1") == [gartenpflege]
    assert {
        "titel": "Baumschnitt",
        "info": "A-0002 · 45,00\xa0€ / Std.",
        "url": reverse("artikel:bearbeiten", args=[baumschnitt.pk]),
    } in client.get("/").context["suchindex"]
