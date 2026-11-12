"""Hinweis auf neue Versionen (Spezifikation D-7) – ohne echte Anfrage an GitHub."""

import json
import sys
import urllib.error
from datetime import date, timedelta
from io import BytesIO

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core import updates
from dokumentation import fassungen, inhalt
from dokumentation.models import Fassung
from konten.models import Benutzer

pytestmark = pytest.mark.django_db

# Vor dem Ersetzen in tests/conftest.py gemerkt.
ECHTE_SUCHE = updates.bei_bedarf
NEU = "9.0.0"
PAKETE = [
    f"Kontorfreund-Setup-{NEU}.exe",
    f"Kontorfreund-{NEU}-windows-portabel.zip",
    f"Kontorfreund-{NEU}-macos-arm64.tar.gz",
    f"Kontorfreund-{NEU}-linux-x86_64.tar.gz",
    "Kontorfreund-Setup.exe",
]


def release(tag=f"v{NEU}", body=None, pakete=PAKETE):
    return {
        "tag_name": tag,
        "published_at": "2026-11-20T10:00:00Z",
        "body": body
        if body is not None
        else "- Neu: Serienrechnungen.\n- Besser: `Einstellungen` mit **Updates**,\n  "
        "auch für alle Firmen.",
        "assets": [{"name": n} for n in pakete],
    }


class GitHub:
    """Steht für urlopen; `antwort` ist ein Release, Bytes oder eine Ausnahme."""

    def __init__(self):
        self.anfragen = []
        self.antwort = release()

    def __call__(self, anfrage, timeout):
        self.anfragen.append(anfrage)
        if isinstance(self.antwort, Exception):
            raise self.antwort
        if isinstance(self.antwort, bytes):
            return BytesIO(self.antwort)
        return BytesIO(json.dumps(self.antwort).encode())


@pytest.fixture
def github(monkeypatch):
    attrappe = GitHub()
    monkeypatch.setattr(updates, "_oeffnen", attrappe)
    return attrappe


@pytest.fixture
def mitarbeiter():
    benutzer = Benutzer.objects.create_user(
        "mia@muster.test", name="Mia Muster", rolle=Benutzer.Rolle.MITARBEITER
    )
    c = Client()
    c.force_login(benutzer)
    return c


def test_ohne_zustimmung_wird_nicht_gesucht(client, github):
    seite = client.get(reverse("core:start")).text

    assert updates.suchen() is None
    assert not updates.faellig()
    assert "Soll Kontorfreund einmal am Tag nachsehen" in seite
    assert github.anfragen == []


def test_ja_auf_der_uebersicht_sucht_sofort(client, github, settings):
    antwort = client.post(
        reverse("core:updates"), {"aktion": "ja", "zurueck": "start"}, follow=True
    )

    assert antwort.redirect_chain[-1][0] == reverse("core:start")
    assert updates.suchen() is True
    assert f"Kontorfreund {NEU} ist erschienen" in antwort.text
    assert "Soll Kontorfreund einmal am Tag nachsehen" not in antwort.text
    assert (settings.HAUPTORDNER / "updates.json").is_file()
    assert len(github.anfragen) == 1


def test_nein_sucht_nie(client, github):
    antwort = client.post(
        reverse("core:updates"), {"aktion": "nein", "zurueck": "start"}, follow=True
    )

    assert updates.suchen() is False
    assert not updates.faellig()
    assert "sucht nicht nach neuen Versionen" in antwort.text
    assert "Soll Kontorfreund einmal am Tag nachsehen" not in antwort.text
    assert github.anfragen == []


def test_anfrage_traegt_keine_kennung(github, settings):
    updates.pruefen()

    (anfrage,) = github.anfragen
    assert anfrage.full_url == updates.ABFRAGE
    assert anfrage.get_method() == "GET"
    assert anfrage.data is None
    kopf = " ".join(f"{k}: {v}" for k, v in anfrage.header_items())
    assert settings.VERSION not in kopf
    assert anfrage.get_header("User-agent") == "Kontorfreund"


def test_einmal_am_tag(github):
    updates.festlegen(True)
    assert updates.faellig()

    updates.pruefen()
    assert not updates.faellig()

    gestern = (timezone.now() - timedelta(hours=25)).isoformat()
    updates._aendern(gesucht=gestern, versucht=gestern)
    assert updates.faellig()

    # Ohne Netz erst nach einer Stunde wieder.
    github.antwort = urllib.error.URLError("offline")
    with pytest.raises(updates.Fehler):
        updates.pruefen()
    assert not updates.faellig()
    vorhin = (timezone.now() - timedelta(hours=2)).isoformat()
    updates._aendern(versucht=vorhin)
    assert updates.faellig()


def test_suche_im_hintergrund(github, monkeypatch):
    class SofortThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(updates.threading, "Thread", SofortThread)
    monkeypatch.setattr(updates, "_naechster_blick", 0.0)

    ECHTE_SUCHE()
    assert github.anfragen == []  # nicht zugestimmt

    updates.festlegen(True)
    monkeypatch.setattr(updates, "_naechster_blick", 0.0)
    ECHTE_SUCHE()
    assert len(github.anfragen) == 1
    assert updates.hinweis()["version"] == NEU

    # Höchstens alle zehn Minuten ein Blick.
    updates._aendern(gesucht="", versucht="")
    ECHTE_SUCHE()
    assert len(github.anfragen) == 1


def test_middleware_nur_nach_anmeldung(client, anonym, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(updates, "bei_bedarf", lambda: aufrufe.append(1))

    anonym.get(reverse("konten:anmelden"))
    assert aufrufe == []
    client.get(reverse("core:start"))
    assert aufrufe == [1]


def test_seite_zeigt_neuerungen_und_paket(client, github, monkeypatch):
    monkeypatch.setattr(updates, "art", lambda: "windows")
    client.post(reverse("core:updates"), {"aktion": "jetzt"})

    seite = client.get(reverse("core:updates")).text

    assert f"Kontorfreund {NEU} ist erschienen" in seite
    assert "Veröffentlicht am 20.11.2026" in seite
    assert "<li>Neu: Serienrechnungen.</li>" in seite
    assert "<li>Besser: Einstellungen mit Updates, auch für alle Firmen.</li>" in seite
    assert (
        f'href="{updates.PROJEKT}/releases/download/v{NEU}/Kontorfreund-Setup-{NEU}.exe"'
        in seite
    )
    assert "starten Sie das neue Installationsprogramm" in seite


@pytest.mark.parametrize(
    ("portabel", "frozen", "plattform", "art", "paket"),
    [
        (True, True, "win32", "portabel", f"Kontorfreund-{NEU}-windows-portabel.zip"),
        (False, True, "win32", "windows", f"Kontorfreund-Setup-{NEU}.exe"),
        (False, True, "darwin", "macos", f"Kontorfreund-{NEU}-macos-arm64.tar.gz"),
        (False, True, "linux", "linux", f"Kontorfreund-{NEU}-linux-x86_64.tar.gz"),
        (False, False, "linux", "quellcode", ""),
    ],
)
def test_paket_passt_zur_installation(
    github, settings, monkeypatch, portabel, frozen, plattform, art, paket
):
    settings.PORTABEL = portabel
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "platform", plattform)
    updates.pruefen()

    neu = updates.hinweis()

    assert updates.art() == art
    assert neu["paket"] == paket
    assert neu["download"] == (
        f"{updates.PROJEKT}/releases/download/v{NEU}/{paket}" if paket else ""
    )
    assert neu["seite"] == f"{updates.PROJEKT}/releases/tag/v{NEU}"


def test_ohne_passendes_paket_nur_die_seite(client, github, monkeypatch):
    monkeypatch.setattr(updates, "art", lambda: "macos")
    github.antwort = release(pakete=[f"Kontorfreund-Setup-{NEU}.exe"])
    updates.pruefen()

    seite = client.get(reverse("core:updates")).text

    assert updates.hinweis()["download"] == ""
    assert "herunterladen" not in seite
    assert f'href="{updates.PROJEKT}/releases/tag/v{NEU}"' in seite
    assert "ersetzen Sie damit den bisherigen Ordner" in seite


@pytest.mark.parametrize("tag", ["v0.0.1", "SELBST"])
def test_keine_neuere_version(client, github, settings, tag):
    github.antwort = release(tag=f"v{settings.VERSION}" if tag == "SELBST" else tag)

    antwort = client.post(reverse("core:updates"), {"aktion": "jetzt"}, follow=True)

    assert updates.hinweis() is None
    assert f"Sie haben die neueste Version, Kontorfreund {settings.VERSION}." in (
        antwort.text
    )
    assert "Zuletzt gesucht am" in antwort.text
    assert "ist erschienen" not in client.get(reverse("core:start")).text


def test_fehler_wird_gezeigt(client, github):
    github.antwort = urllib.error.URLError("offline")

    antwort = client.post(reverse("core:updates"), {"aktion": "jetzt"}, follow=True)

    assert "Keine Verbindung zu GitHub" in antwort.text
    assert "Die letzte Suche hat nicht geklappt" in antwort.text


@pytest.mark.parametrize(
    "antwort",
    [
        b"kein json",
        b"[]",
        json.dumps(release(tag="v9.0.0<script>")).encode(),
        b" " * (updates.HOECHSTENS + 1),
        urllib.error.HTTPError(updates.ABFRAGE, 302, "Found", {}, None),
    ],
)
def test_unerwartete_antwort(github, antwort):
    github.antwort = antwort

    with pytest.raises(updates.Fehler):
        updates.pruefen()

    assert updates.hinweis() is None
    assert updates.stand()["fehler"]


def test_neuerungen_sind_schlichter_text(client, github):
    github.antwort = release(body="- <script>alert(1)</script> **fett**")
    updates.pruefen()

    seite = client.get(reverse("core:updates")).text

    assert "<script>alert(1)</script>" not in seite
    assert "&lt;script&gt;alert(1)&lt;/script&gt; fett" in seite


def test_kaputte_datei_stoert_nicht(client, settings):
    (settings.HAUPTORDNER / "updates.json").write_text("{kaputt", encoding="utf-8")

    assert updates.stand() == {}
    assert client.get(reverse("core:start")).status_code == 200
    assert client.get(reverse("core:updates")).status_code == 200


def test_nur_fuer_den_inhaber(mitarbeiter, github):
    updates.pruefen()

    assert mitarbeiter.get(reverse("core:updates")).status_code == 403
    assert (
        mitarbeiter.post(reverse("core:updates"), {"aktion": "ja"}).status_code == 403
    )
    seite = mitarbeiter.get(reverse("core:start")).text
    assert "ist erschienen" not in seite
    assert "Soll Kontorfreund einmal am Tag nachsehen" not in seite
    assert updates.suchen() is None


def test_hinweis_in_der_kopfleiste_jeder_seite(client, mitarbeiter, github):
    link = f'href="{reverse("core:updates")}"'
    assert "update-hinweis" not in client.get(reverse("contacts:liste")).text

    updates.pruefen()
    for seite in ("contacts:liste", "invoicing:liste", "core:start"):
        text = client.get(reverse(seite)).text
        assert f"Update {NEU}</span>" in text
        assert f'class="btn btn-sm update-hinweis topbar-end" {link}' in text
    # Mitarbeiter installieren nicht und sehen ihn deshalb nicht.
    assert "update-hinweis" not in mitarbeiter.get(reverse("contacts:liste")).text


def test_kein_hinweis_ohne_neuere_version(client, github, settings):
    github.antwort = release(tag=f"v{settings.VERSION}")
    updates.pruefen()
    assert "update-hinweis" not in client.get(reverse("core:start")).text


def test_suchen_von_der_uebersicht(client, mitarbeiter, github):
    seite = client.get(reverse("core:start")).text
    assert 'name="aktion" value="jetzt"' in seite
    assert (
        'name="aktion" value="jetzt"' not in mitarbeiter.get(reverse("core:start")).text
    )

    antwort = client.post(
        reverse("core:updates"), {"aktion": "jetzt", "zurueck": "start"}, follow=True
    )
    assert antwort.redirect_chain == [(reverse("core:start"), 302)]
    assert f"Kontorfreund {NEU} ist erschienen." in antwort.text
    assert f"Update {NEU}</span>" in antwort.text
    # Auch ohne tägliche Suche: Gesucht wird nur auf diesen Klick.
    assert updates.suchen() is None
    assert len(github.anfragen) == 1


def test_einstellungen_und_suche_fuehren_zur_seite(client):
    assert reverse("core:updates") in client.get(reverse("core:einstellungen")).text
    seite = client.get(reverse("core:updates")).text
    assert "Installiert ist Kontorfreund" in seite
    assert "Einschalten" in seite


def test_dokumentation_nennt_die_suche():
    assert inhalt.UPDATE_SUCHE not in str(fassungen.entwurf(Fassung.Art.VERFAHREN))

    updates.festlegen(True)

    assert "nur die IP-Adresse" in str(fassungen.entwurf(Fassung.Art.VERFAHREN))
    assert "Abfrage bei GitHub" in str(fassungen.entwurf(Fassung.Art.DATENSCHUTZ))


def test_datum_der_veroeffentlichung(github):
    updates.pruefen()
    assert updates.hinweis()["datum"] == date(2026, 11, 20)
