import pytest
from django.test import Client

from konten.models import Benutzer


@pytest.fixture(autouse=True)
def datenordner(tmp_path, settings):
    """Kein Test schreibt in den echten Datenordner, auch keine Sicherung."""
    settings.DATA_DIR = tmp_path
    settings.HAUPTORDNER = tmp_path


@pytest.fixture
def inhaber(db):
    return Benutzer.objects.create_user(
        "inhaber@muster.test", name="Max Muster", rolle=Benutzer.Rolle.INHABER
    )


@pytest.fixture
def client(client, inhaber):
    """Als Inhaber angemeldet; die Anmeldung selbst prüfen Tests mit `anonym`."""
    client.force_login(inhaber)
    return client


@pytest.fixture
def anonym():
    return Client()
