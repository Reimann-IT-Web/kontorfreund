"""Installationspaket (Spezifikation D-3): Startprogramm, Version, Selbsttest."""

import runpy
import sys
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


def test_version_und_urheber_auf_der_hilfeseite(client):
    seite = client.get(reverse("core:hilfe")).content.decode()
    assert (
        f"Kontorfreund {settings.VERSION} · entwickelt von Reimann IT &amp; Web"
        in seite
    )
    assert "AGPL-3.0" in seite


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
    ausgabe = capsys.readouterr().out
    assert "in Ordnung: Datensicherung verschlüsseln und wiederherstellen" in ausgabe
    assert "Selbsttest bestanden." in ausgabe
    assert not Kontakt.objects.exists()
    assert not Rechnung.objects.exists()
    # Die Probe der Datensicherung lief in einem eigenen Ordner.
    assert not (settings.DATA_DIR / "datensicherung.json").exists()
    assert not (settings.DATA_DIR / "sicherung").exists()


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows schützt den Benutzerordner."
)
def test_datenordner_nur_fuer_den_benutzer(monkeypatch, tmp_path):
    ordner = tmp_path / "Kontorfreund"
    monkeypatch.setenv("APP_DATA_DIR", str(ordner))
    runpy.run_path(str(Path(settings.BASE_DIR) / "config" / "settings.py"))
    assert ordner.stat().st_mode & 0o777 == 0o700
