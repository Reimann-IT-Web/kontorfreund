import pytest
from django.urls import reverse

from core.models import Firmendaten

pytestmark = pytest.mark.django_db

GUELTIGE_IBAN = "DE89 3704 0044 0532 0130 00"


def test_firmendaten_speichern(client):
    response = client.post(
        reverse("core:einstellungen"),
        {
            "name": "IT-Service Muster",
            "strasse": "Gartenweg 1",
            "plz": "55116",
            "ort": "Mainz",
            "steuernummer": "26/123/45678",
            "umsatzsteuer": "kleinunternehmer",
            "iban": GUELTIGE_IBAN,
            "mail_port": "587",
            "mail_verschluesselung": "starttls",
        },
    )

    firma = Firmendaten.laden()
    assert response.status_code == 302
    assert firma.vollstaendig
    assert firma.iban == "DE89370400440532013000"


def test_iban_mit_falscher_pruefziffer(client):
    response = client.post(
        reverse("core:einstellungen"), {"name": "X", "iban": GUELTIGE_IBAN[:-1] + "1"}
    )

    assert "Prüfziffer" in response.text


def test_ohne_steuernummer_unvollstaendig():
    firma = Firmendaten.laden()
    firma.name, firma.strasse, firma.plz, firma.ort = "X", "Weg 1", "55116", "Mainz"

    assert not firma.vollstaendig
