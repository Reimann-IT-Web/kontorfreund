"""Ort zur Postleitzahl in Adressen und Firmendaten."""

import pytest
from django.urls import reverse

from contacts import plz


def test_orte():
    assert plz.orte("55116") == (["Mainz"], "Mainz")
    assert plz.orte(" 10115 ") == (["Berlin"], "Berlin")
    # Ein paar Straßen von Ober-Olm haben die PLZ von Nieder-Olm; der Ort ist trotzdem klar.
    orte, ort = plz.orte("55268")
    assert (orte[0], ort) == ("Nieder-Olm", "Nieder-Olm")
    assert "Ober-Olm" in orte
    # Neun Gemeinden teilen sich die PLZ: Der Nutzer wählt.
    orte, ort = plz.orte("55270")
    assert ort == ""
    assert {"Essenheim", "Ober-Olm", "Zornheim", "Klein-Winternheim"} <= set(orte)
    assert plz.orte("00000") == ([], "")
    assert plz.orte("abc") == ([], "")


def test_datei_nennt_quelle_und_lizenz():
    zeilen = plz.DATEI.read_text(encoding="utf-8").splitlines()[:5]
    kopf = " ".join(z.removeprefix("# ") for z in zeilen)
    assert "© OpenStreetMap-Mitwirkende" in kopf
    assert "Open Database License" in kopf


@pytest.mark.django_db
def test_abfrage(client, anonym):
    adresse = reverse("contacts:orte")
    assert client.get(adresse, {"plz": "06108"}).json() == {
        "orte": ["Halle (Saale)"],
        "ort": "Halle (Saale)",
    }
    assert client.get(adresse, {"plz": "5511"}).json() == {"orte": [], "ort": ""}
    assert anonym.get(adresse, {"plz": "55116"}).status_code == 302


@pytest.mark.django_db
def test_formulare_fuellen_den_ort(client):
    for seite in (reverse("contacts:neu"), reverse("core:einstellungen")):
        html = client.get(seite).content.decode()
        assert f'data-plz="{reverse("contacts:orte")}"' in html
        assert "data-ort" in html
