from io import BytesIO

import pytest
from django.test import Client
from PIL import Image, ImageDraw

from archive import pruefung
from konten.models import Benutzer


@pytest.fixture(autouse=True)
def datenordner(tmp_path, settings):
    """Kein Test schreibt in den echten Datenordner, auch keine Sicherung."""
    settings.DATA_DIR = tmp_path
    settings.HAUPTORDNER = tmp_path


@pytest.fixture(autouse=True)
def ohne_taegliche_pruefung(monkeypatch):
    """Die tägliche Prüfung der Ablage liefe sonst nach Anfragen in einem eigenen Thread."""
    monkeypatch.setattr(pruefung, "bei_bedarf", lambda: None)


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
def unterschrift():
    """PNG mit durchsichtigem Grund, wie eine freigestellte Unterschrift."""
    bild = Image.new("RGBA", (300, 80), (0, 0, 0, 0))
    ImageDraw.Draw(bild).line(
        [(10, 60), (80, 20), (150, 60), (290, 20)], fill=(0, 0, 0, 255), width=4
    )
    ausgabe = BytesIO()
    bild.save(ausgabe, format="PNG")
    return ausgabe.getvalue()


@pytest.fixture
def anonym():
    return Client()
