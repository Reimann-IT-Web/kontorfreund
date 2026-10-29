import pytest

from contacts.models import Kontakt

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "pfad",
    [
        "/",
        "/adressen/",
        "/adressen/neu/",
        "/rechnungen/neu/",
        "/einstellungen/",
        "/artikel/",
    ],
)
def test_seite_laedt(client, pfad):
    response = client.get(pfad)

    assert response.status_code == 200
    assert "Kontorfreund (Kleinunternehmen)" in response.text


def test_unbekannter_bereich(client):
    assert client.get("/gibt-es-nicht/").status_code == 404


def test_csp_ohne_inline(client):
    csp = client.get("/").headers["Content-Security-Policy"]

    assert "default-src 'self'" in csp
    assert "unsafe-inline" not in csp


def test_start_ohne_daten_zeigt_erste_schritte(client):
    response = client.get("/")

    assert "Erste Schritte" in response.text
    assert Kontakt.objects.count() == 0


def test_rechnung_mit_vorgewaehltem_empfaenger(client):
    kontakt = Kontakt.objects.create(art="firma", firmenname="Fahrschule Kaya")

    response = client.get("/rechnungen/neu/", {"empfaenger": kontakt.pk})

    assert response.context["empfaenger"] == kontakt.pk
    assert "Fahrschule Kaya (K-0001)" in response.text
