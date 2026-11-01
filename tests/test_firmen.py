"""Mehrere Firmen, jede mit eigenem Datenordner (core/firmen.py) – mit erfundenen Daten."""

import runpy
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.urls import reverse

import kontorfreund
from backups import sicherung
from core import firmen
from core import views as core_views
from konten.models import Benutzer


def firmendaten(ordner, name, konten=1):
    """Datenbank einer Firma, so weit firmen.py sie liest."""
    ordner.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(ordner / "db.sqlite3")) as db:
        db.execute("CREATE TABLE core_firmendaten (id INTEGER PRIMARY KEY, name TEXT)")
        db.execute("INSERT INTO core_firmendaten VALUES (1, ?)", [name])
        db.execute("CREATE TABLE konten_benutzer (id INTEGER PRIMARY KEY)")
        db.executemany(
            "INSERT INTO konten_benutzer VALUES (?)", [(i,) for i in range(konten)]
        )
        db.commit()


@pytest.fixture
def neustart(settings, monkeypatch):
    """Wie unter dem Startprogramm; statt den Server zu beenden, nur mitschreiben."""
    settings.NEUSTART = True
    beendet = []
    monkeypatch.setattr(core_views, "neu_starten", lambda: beendet.append(True))
    return beendet


def test_erste_firma_bleibt_im_hauptordner(tmp_path):
    assert firmen.aktiv(tmp_path) == ""
    assert [(f.nummer, f.ordner) for f in firmen.alle(tmp_path)] == [("1", tmp_path)]
    assert not firmen.mehrere(tmp_path)


def test_anlegen_waehlen_und_namen(tmp_path):
    firmendaten(tmp_path, "Muster IT")
    assert firmen.anlegen(tmp_path) == "2"
    assert firmen.anlegen(tmp_path) == "3"
    firmendaten(tmp_path / "firmen" / "2", "Beispiel GmbH")
    (tmp_path / "firmen" / "notizen").mkdir()  # fremde Ordner zählen nicht
    assert [(f.nummer, f.anzeigename) for f in firmen.alle(tmp_path)] == [
        ("1", "Muster IT"),
        ("2", "Beispiel GmbH"),
        ("3", "Firma 3"),
    ]
    firmen.waehlen(tmp_path, "2")
    assert firmen.aktiv(tmp_path) == "2"
    assert firmen.umgebung(tmp_path, "2") == {
        "APP_HAUPTORDNER": str(tmp_path),
        "APP_FIRMA": "2",
        "APP_DATA_DIR": str(tmp_path / "firmen" / "2"),
    }
    # Fehlt der Ordner, öffnet die erste Firma.
    firmen.waehlen(tmp_path, "9")
    assert firmen.aktiv(tmp_path) == ""


def test_nur_eine_leere_firma_laesst_sich_entfernen(tmp_path):
    firmen.anlegen(tmp_path)
    firmen.anlegen(tmp_path)
    firmendaten(tmp_path / "firmen" / "2", "", konten=1)
    for kennung in ("", "2", "7"):
        with pytest.raises(ValueError):
            firmen.entfernen(tmp_path, kennung)
    firmen.waehlen(tmp_path, "3")
    with pytest.raises(ValueError):
        firmen.entfernen(tmp_path, "3")  # gerade offen
    firmen.waehlen(tmp_path, "")
    firmen.entfernen(tmp_path, "3")
    assert [f.nummer for f in firmen.alle(tmp_path)] == ["1", "2"]


def test_unlesbare_datenbank_gilt_nicht_als_leer(tmp_path):
    ordner = tmp_path / "firmen" / "2"
    ordner.mkdir(parents=True)
    (ordner / "db.sqlite3").write_bytes(b"keine Datenbank")
    assert not firmen.Firma("2", ordner, "").leer


def test_startprogramm_startet_mit_der_neuen_firma(monkeypatch, tmp_path):
    firmen.anlegen(tmp_path)
    gestartet = []
    codes = iter([firmen.WECHSELN, 0])

    class Server:
        def __init__(self, befehl, env):
            gestartet.append(
                (befehl[-1], env["APP_DATA_DIR"], env.get("APP_KEIN_BROWSER"))
            )
            firmen.waehlen(tmp_path, "2")  # wie die Seite „Firmen“

        def wait(self):
            return next(codes)

    monkeypatch.setattr(kontorfreund.subprocess, "Popen", Server)
    monkeypatch.setattr(kontorfreund, "erinnern", lambda haupt: None)
    monkeypatch.setattr(kontorfreund.signal, "signal", lambda *args: None)
    monkeypatch.delenv("APP_KEIN_BROWSER", raising=False)
    assert kontorfreund.betreiben(tmp_path, hintergrund=False) == 0
    # Den Browser öffnet nur der erste Start.
    assert gestartet == [
        ("--server", str(tmp_path), None),
        ("--server", str(tmp_path / "firmen" / "2"), "1"),
    ]


def test_eigenes_cookie_je_firma(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "firmen" / "2"))
    monkeypatch.setenv("APP_HAUPTORDNER", str(tmp_path))
    monkeypatch.setenv("APP_FIRMA", "2")
    werte = runpy.run_path(
        str(Path(django_settings.BASE_DIR) / "config" / "settings.py")
    )
    assert werte["SESSION_COOKIE_NAME"] == "sessionid-2"
    assert werte["HAUPTORDNER"] == tmp_path
    assert django_settings.SESSION_COOKIE_NAME == "sessionid"


@pytest.mark.django_db(transaction=True)
def test_sicherungen_tragen_die_firma_im_namen(settings):
    sicherung.einrichten("Pferd Batterie Heftklammer")
    erste, _ = sicherung.sichern()
    settings.FIRMA = "2"
    zweite, _ = sicherung.sichern()
    assert zweite.name.startswith("kontorfreund-firma2-")
    # Jede Firma sieht nur ihre eigenen, auch im selben Ordner.
    assert [e["pfad"] for e in sicherung.liste()] == [zweite]
    settings.FIRMA = ""
    assert [e["pfad"] for e in sicherung.liste()] == [erste]


def test_anlegen_und_oeffnen(client, tmp_path, neustart):
    seite = client.get(reverse("core:firmen")).content.decode()
    assert "Weitere Firma anlegen" in seite and "Geöffnet" in seite
    antwort = client.post(reverse("core:firma_anlegen"))
    seite = antwort.content.decode()
    assert "Neue Firma wird geöffnet" in seite and 'data-firma="2"' in seite
    assert firmen.aktiv(tmp_path) == "2" and neustart == [True]
    # Die Seitenleiste bietet den Wechsel an, sobald es zwei gibt.
    assert reverse("core:firmen") in client.get(reverse("core:start")).content.decode()


def test_ohne_startprogramm_erst_beim_naechsten_start(client, tmp_path):
    antwort = client.post(reverse("core:firma_anlegen"), follow=True)
    assert "beim nächsten Start" in antwort.content.decode()
    assert firmen.aktiv(tmp_path) == "2"


def test_wechseln_vor_der_anmeldung(anonym, inhaber, settings, tmp_path, neustart):
    firmen.anlegen(tmp_path)
    firmen.waehlen(tmp_path, "2")
    settings.FIRMA = "2"
    anmelden = anonym.get(reverse("konten:anmelden")).content.decode()
    assert "Andere Firma öffnen" in anmelden
    assert "Daten:" not in anonym.get(reverse("core:firmen")).content.decode()
    antwort = anonym.post(reverse("core:firma_oeffnen"), {"firma": ""})
    assert "Firma 1 wird geöffnet" in antwort.content.decode()
    assert firmen.aktiv(tmp_path) == "" and neustart == [True]
    assert anonym.get(reverse("core:firma_offen")).content == b"2"


def test_falsche_oder_offene_firma(client, neustart):
    antwort = client.post(reverse("core:firma_oeffnen"), {"firma": "5"})
    assert antwort.status_code == 404
    antwort = client.post(reverse("core:firma_oeffnen"), {"firma": ""})
    assert antwort.url == reverse("core:start") and neustart == []


def test_im_netzwerk_nur_angemeldet(db, anonym, settings):
    settings.NETZWERK = True
    assert anonym.get(reverse("core:firmen")).url.startswith(reverse("konten:anmelden"))


def test_mitarbeiter_legt_keine_firma_an(db, anonym, tmp_path):
    anonym.force_login(
        Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    )
    assert anonym.post(reverse("core:firma_anlegen")).status_code == 403
    assert not firmen.mehrere(tmp_path)


def test_leere_firma_entfernen(client, tmp_path):
    firmen.anlegen(tmp_path)
    seite = client.get(reverse("core:firmen")).content.decode()
    assert "Entfernen" in seite
    client.post(reverse("core:firma_entfernen"), {"firma": "2"})
    assert not firmen.mehrere(tmp_path)
    antwort = client.post(reverse("core:firma_entfernen"), {"firma": ""}, follow=True)
    assert "noch niemand ein Konto" in antwort.content.decode()


def test_startprogramm_erinnert_jede_eingeschaltete_firma(monkeypatch, tmp_path):
    firmen.anlegen(tmp_path)
    firmen.anlegen(tmp_path)
    eingeschaltet = tmp_path / "firmen" / "2"
    monkeypatch.setattr(
        firmen, "benachrichtigt", lambda ordner: ordner == eingeschaltet
    )
    aufrufe, pausen = [], []

    class Ende(Exception):
        pass

    def warten(sekunden):
        pausen.append(sekunden)
        if len(pausen) > 1:
            raise Ende

    monkeypatch.setattr(kontorfreund.time, "sleep", warten)
    monkeypatch.setattr(
        kontorfreund.subprocess,
        "run",
        lambda befehl, env, **weitere: aufrufe.append((befehl[-1], env["APP_FIRMA"])),
    )
    with pytest.raises(Ende):
        kontorfreund.erinnern(tmp_path)
    assert aufrufe == [("erinnern", "2")]
    assert pausen == [30, kontorfreund.TAKT]
