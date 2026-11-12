"""Installationspaket (Spezifikation D-3): Startprogramm, Version, Selbsttest."""

import os
import re
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


def test_jede_eigene_app_kommt_ins_paket():
    """PyInstaller findet die Apps nur über die Liste in der Spec-Datei."""
    spec = (Path(settings.BASE_DIR) / "packaging" / "kontorfreund.spec").read_text(
        encoding="utf-8"
    )
    liste = re.search(r"APPS = \[(.*?)\]", spec, re.S).group(1)
    im_paket = set(re.findall(r'"([a-z_]+)"', liste))
    eigene = {
        app.split(".")[0]
        for app in settings.INSTALLED_APPS
        if (Path(settings.BASE_DIR) / app.split(".")[0]).is_dir()
    }
    assert eigene <= im_paket


def test_version_und_urheber_auf_der_hilfeseite(client):
    seite = client.get(reverse("core:hilfe")).content.decode()
    assert (
        f"Kontorfreund {settings.VERSION} · entwickelt von Reimann IT &amp; Web"
        in seite
    )
    assert "AGPL-3.0" in seite


def test_internetadresse_steht_im_installer_unter_dem_quellcode():
    ordner = Path(settings.BASE_DIR) / "packaging" / "windows"
    texte = (ordner / "texte.isl").read_text(encoding="utf-8-sig")
    skript = (ordner / "kontorfreund.iss").read_text(encoding="utf-8")

    assert "QuellcodeAdresse=https://github.com/Reimann-IT-Web/kontorfreund\n" in texte
    assert "InternetAdresse=https://it-lsg-reimann.de\n" in texte
    assert skript.index("LinkZeile('QuellcodeName'") < skript.index(
        "LinkZeile('InternetName'"
    )


def test_speicherort_ist_waehlbar_und_programme_ist_die_vorgabe():
    skript = (
        Path(settings.BASE_DIR) / "packaging" / "windows" / "kontorfreund.iss"
    ).read_text(encoding="utf-8")

    assert "DefaultDirName={autopf}\\Kontorfreund\n" in skript
    assert "WizardForm.DirBrowseButton.OnClick" in skript


def test_fruehere_installation_wird_ersetzt_und_laeuft_ohne_erhoehte_rechte():
    skript = (
        Path(settings.BASE_DIR) / "packaging" / "windows" / "kontorfreund.iss"
    ).read_text(encoding="utf-8")

    kennung = re.search(r"^AppId=\{(\{[0-9A-F-]+\})$", skript, re.MULTILINE).group(1)
    assert f"\\Uninstall\\{kennung}_is1'" in skript
    # Der Pfad steht unter HKCU, jedes Programm des Benutzers kann ihn ändern.
    assert "ExecAsOriginalUser(Programm," in skript
    assert "Exec(Programm," not in skript
    # Erst entfernen, wenn das neue Programm liegt: Ein Abbruch ließe sonst keines übrig.
    assert "ssPostInstall then\n    FruehereErsetzen" in skript
    assert "function PrepareToInstall" not in skript


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


@pytest.fixture
def programm(monkeypatch, tmp_path):
    """Ein gepacktes Programm in tmp_path/Kontorfreund, wie es PyInstaller baut."""
    ordner = tmp_path / "Kontorfreund"
    ordner.mkdir()
    monkeypatch.setattr(kontorfreund.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        kontorfreund.sys, "executable", str(ordner / "Kontorfreund.exe")
    )
    return ordner


def test_portabel_liegen_die_daten_neben_dem_programm(programm):
    assert not kontorfreund.portabel()
    assert kontorfreund.datenordner() != programm / "Daten"
    (programm / "portabel.txt").write_text("portabel", encoding="utf-8")
    assert kontorfreund.portabel()
    assert kontorfreund.datenordner() == programm / "Daten"


def test_portabel_startet_mit_dem_ordner_daten(monkeypatch, programm):
    (programm / "portabel.txt").write_text("portabel", encoding="utf-8")
    umgebung = {
        k: v
        for k, v in os.environ.items()
        if k not in {"APP_HAUPTORDNER", "APP_DATA_DIR", "APP_FIRMA", "APP_PORTABEL"}
    }
    monkeypatch.setattr(kontorfreund.os, "environ", umgebung)
    monkeypatch.setattr(kontorfreund.sys, "argv", ["Kontorfreund", "--server"])
    monkeypatch.setattr(kontorfreund, "server", lambda: None)
    kontorfreund.main()
    assert umgebung["APP_PORTABEL"] == "1"
    assert umgebung["APP_DATA_DIR"] == str(programm / "Daten")


def test_portabel_eigenes_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "firmen" / "2"))
    monkeypatch.setenv("APP_HAUPTORDNER", str(tmp_path))
    monkeypatch.setenv("APP_FIRMA", "2")
    monkeypatch.setenv("APP_PORTABEL", "1")
    werte = runpy.run_path(str(Path(settings.BASE_DIR) / "config" / "settings.py"))
    assert werte["SESSION_COOKIE_NAME"] == "sessionid-portabel-2"
    monkeypatch.delenv("APP_FIRMA")
    werte = runpy.run_path(str(Path(settings.BASE_DIR) / "config" / "settings.py"))
    assert werte["SESSION_COOKIE_NAME"] == "sessionid-portabel"


def test_portabel_ohne_start_beim_anmelden(settings, programm, monkeypatch):
    from benachrichtigungen import autostart

    monkeypatch.setattr(autostart.sys, "platform", "win32")
    assert autostart.moeglich()
    settings.PORTABEL = True
    assert not autostart.moeglich()


@pytest.mark.django_db
def test_hilfe_nennt_den_ordner_der_portablen_fassung(client, settings, tmp_path):
    ordner = tmp_path / "Kontorfreund" / "Daten"
    seite = client.get(reverse("core:hilfe")).content.decode()
    assert "%LOCALAPPDATA%" in seite
    assert "portable Fassung" not in seite
    settings.PORTABEL = True
    settings.HAUPTORDNER = ordner
    seite = client.get(reverse("core:hilfe")).content.decode()
    assert f"<code>{ordner}</code>" in seite
    assert "%LOCALAPPDATA%" not in seite
    assert "neue portable Fassung in einen neuen Ordner" in seite
    assert "neue Installationsprogramm" not in seite


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
