"""Installationspaket (Spezifikation D-3): Startprogramm, Version, Selbsttest."""

import tomllib
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse

import kontorfreund


def test_version_wie_in_pyproject():
    pyproject = tomllib.loads(
        (Path(settings.BASE_DIR) / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["version"] == settings.VERSION


def test_version_auf_der_hilfeseite(client):
    seite = client.get(reverse("core:platzhalter", args=["hilfe"]))
    assert f"Kontorfreund {settings.VERSION}" in seite.content.decode()


@pytest.mark.parametrize(
    ("plattform", "umgebung", "erwartet"),
    [
        ("win32", {"LOCALAPPDATA": "C:/Nutzer/Lokal"}, Path("C:/Nutzer/Lokal")),
        ("linux", {"XDG_DATA_HOME": "/home/max/.daten"}, Path("/home/max/.daten")),
        ("darwin", {}, Path.home() / "Library" / "Application Support"),
    ],
)
def test_daten_liegen_im_benutzerordner(monkeypatch, plattform, umgebung, erwartet):
    monkeypatch.setattr(kontorfreund.sys, "platform", plattform)
    for name in ("LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    for name, wert in umgebung.items():
        monkeypatch.setenv(name, wert)
    assert kontorfreund.datenordner() == erwartet / "Kontorfreund"


@pytest.mark.django_db
def test_selbsttest_laesst_keine_daten_zurueck(capsys):
    from contacts.models import Kontakt
    from invoicing.models import Rechnung

    call_command("selbsttest")
    assert "Selbsttest bestanden." in capsys.readouterr().out
    assert not Kontakt.objects.exists()
    assert not Rechnung.objects.exists()
