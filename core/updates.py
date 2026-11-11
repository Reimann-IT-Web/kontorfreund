"""Hinweis auf neue Versionen (Spezifikation D-7).

Gesucht wird nur, wenn der Inhaber zugestimmt hat (`suchen`): höchstens einmal am Tag,
angestoßen nach einer angemeldeten Anfrage wie die Sicherung (`bei_bedarf`, Middleware
`core.middleware.update_suche`), oder jederzeit per Knopf (`pruefen`). Die Abfrage geht
an die öffentliche Schnittstelle von GitHub, wo die Pakete liegen. Sie trägt weder
Version noch Kennung; GitHub sieht nur die IP-Adresse.

Die Antwort gilt als fremder Text: Die Version muss aussehen wie 1.2.3, die Neuerungen
werden schlichter Text, und Links baut Kontorfreund selbst aus Version und Paketnamen.

Wahl und letztes Ergebnis liegen in `<Hauptordner>/updates.json`, also einmal für alle
Firmen und nicht in der Datenbank: Es geht um das Programm, nicht um eine Firma.
Installiert wird nichts; der Inhaber lädt das passende Paket (`paket`) und installiert
wie bisher.
"""

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

PROJEKT = "https://github.com/Reimann-IT-Web/kontorfreund"
ABFRAGE = "https://api.github.com/repos/Reimann-IT-Web/kontorfreund/releases/latest"
# Die Antwort ist wenige Kilobyte groß; mehr wird nicht gelesen.
HOECHSTENS = 1024 * 1024
TAEGLICH = timedelta(days=1)
# Ohne Netz nicht nach jeder Anfrage erneut versuchen.
NOCHMAL = timedelta(hours=1)
VERSION = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")
# Pakete eines Release nach Art der Installation (siehe .github/workflows/paket.yml).
PAKETE = {
    "windows": "Kontorfreund-Setup-{}.exe",
    "portabel": "Kontorfreund-{}-windows-portabel.zip",
    "macos": "Kontorfreund-{}-macos-arm64.tar.gz",
    "linux": "Kontorfreund-{}-linux-x86_64.tar.gz",
}

_sperre = threading.Lock()
_naechster_blick = 0.0


class _OhneUmleitung(urllib.request.HTTPRedirectHandler):
    """Eine Umleitung wäre eine Antwort von woanders; sie gilt als Fehler (ASVS 15.3.2)."""

    def redirect_request(self, *args, **kwargs):
        return None


_oeffnen = urllib.request.build_opener(_OhneUmleitung).open


class Fehler(Exception):
    pass


def _datei():
    return settings.HAUPTORDNER / "updates.json"


def stand():
    """Wahl des Inhabers und letztes Ergebnis; leer, solange niemand gefragt wurde."""
    try:
        daten = json.loads(_datei().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.exception("updates.json ist unlesbar")
        return {}
    return daten if isinstance(daten, dict) else {}


def _aendern(**werte):
    with _sperre:
        pfad = _datei()
        tmp = pfad.with_name(pfad.name + ".tmp")
        tmp.write_text(json.dumps({**stand(), **werte}, indent=2), encoding="utf-8")
        os.replace(tmp, pfad)


def suchen():
    """True oder False nach der Entscheidung des Inhabers, None vorher."""
    wahl = stand().get("suchen")
    return wahl if isinstance(wahl, bool) else None


def festlegen(ja):
    _aendern(suchen=bool(ja))


def version(text):
    """(1, 2, 3) aus „1.2.3“ oder „v1.2.3“, sonst None."""
    treffer = VERSION.fullmatch(str(text).strip())
    return tuple(int(t) for t in treffer.groups()) if treffer else None


def zeit(text):
    try:
        wert = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return wert if timezone.is_aware(wert) else None


def _vorbei(wann, abstand):
    # Geht die Uhr nach, gilt ein Zeitpunkt in der Zukunft als vorbei.
    return wann is None or not timedelta(0) <= timezone.now() - wann < abstand


def faellig():
    s = stand()
    return (
        s.get("suchen") is True
        and _vorbei(zeit(s.get("gesucht")), TAEGLICH)
        and _vorbei(zeit(s.get("versucht")), NOCHMAL)
    )


def neuerungen(text):
    """Die Punkte aus dem Änderungsprotokoll des Release als schlichter Text."""
    if not isinstance(text, str):
        return []
    punkte = []
    for zeile in text[:HOECHSTENS].splitlines():
        zeile = zeile.strip()
        if zeile.startswith(("- ", "* ")):
            punkte.append(zeile[2:].strip())
        elif zeile and punkte:
            punkte[-1] += " " + zeile
        elif zeile:
            punkte.append(zeile)
    return [re.sub(r"\*\*|`", "", p)[:2000] for p in punkte[:30]]


def _auswerten(daten):
    if not isinstance(daten, dict):
        raise ValueError(daten)
    nummer = version(daten.get("tag_name", ""))
    if nummer is None:
        raise ValueError(daten.get("tag_name"))
    try:
        datum = date.fromisoformat(str(daten.get("published_at"))[:10]).isoformat()
    except ValueError:
        datum = ""
    assets = daten.get("assets")
    return {
        "version": ".".join(map(str, nummer)),
        "datum": datum,
        "neuerungen": neuerungen(daten.get("body")),
        "pakete": sorted(
            {
                a["name"]
                for a in (assets if isinstance(assets, list) else [])
                if isinstance(a, dict) and isinstance(a.get("name"), str)
            }
        ),
    }


def _abfragen():
    # Fester Rechner im Code; nur das Nötigste im Kopf, keine Version, keine Kennung.
    anfrage = urllib.request.Request(  # noqa: S310
        ABFRAGE,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Kontorfreund"},
    )
    try:
        with _oeffnen(anfrage, timeout=10) as antwort:
            roh = antwort.read(HOECHSTENS + 1)
    except urllib.error.HTTPError as fehler:
        if fehler.code in (403, 429):
            raise Fehler(
                "GitHub nimmt gerade keine Anfragen an. Bitte später noch einmal suchen."
            ) from None
        raise Fehler(f"GitHub hat mit Fehler {fehler.code} geantwortet.") from None
    except OSError:
        raise Fehler("Keine Verbindung zu GitHub. Ist der Rechner online?") from None
    try:
        if len(roh) > HOECHSTENS:
            raise ValueError("zu groß")
        return _auswerten(json.loads(roh))
    except ValueError:
        raise Fehler("GitHub hat unerwartet geantwortet.") from None


def pruefen():
    """Jetzt suchen und das Ergebnis speichern; ein Fehler wird gespeichert und geworfen."""
    jetzt = timezone.now().isoformat()
    try:
        neueste = _abfragen()
    except Fehler as fehler:
        _aendern(versucht=jetzt, fehler=str(fehler))
        raise
    _aendern(versucht=jetzt, gesucht=jetzt, fehler="", neueste=neueste)


def bei_bedarf():
    """Höchstens alle zehn Minuten nachsehen, ob die tägliche Suche fällig ist."""
    global _naechster_blick
    if time.monotonic() < _naechster_blick:
        return
    _naechster_blick = time.monotonic() + 600
    if faellig():
        threading.Thread(target=_taeglich, name="Update-Suche", daemon=True).start()


def _taeglich():
    try:
        if faellig():
            pruefen()
    except Fehler:
        pass  # Steht in updates.json und auf der Seite Updates.
    except Exception:
        logger.exception("Suche nach neuen Versionen fehlgeschlagen")


def art():
    """Wie Kontorfreund hier läuft; danach richten sich Paket und Anleitung."""
    if settings.PORTABEL:
        return "portabel"
    if not getattr(sys, "frozen", False):
        return "quellcode"
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def hinweis():
    """Die neuere Version mit Neuerungen und Links, sonst None."""
    neueste = stand().get("neueste")
    if not isinstance(neueste, dict):
        return None
    nummer = version(neueste.get("version", ""))
    if nummer is None or nummer <= (version(settings.VERSION) or (0, 0, 0)):
        return None
    text = ".".join(map(str, nummer))
    paket = PAKETE.get(art(), "").format(text)
    if paket not in (neueste.get("pakete") or []):
        paket = ""
    try:
        datum = date.fromisoformat(neueste.get("datum"))
    except (TypeError, ValueError):
        datum = None
    return {
        "version": text,
        "datum": datum,
        "neuerungen": [
            p for p in (neueste.get("neuerungen") or []) if isinstance(p, str)
        ],
        "seite": f"{PROJEKT}/releases/tag/v{text}",
        "paket": paket,
        "download": f"{PROJEKT}/releases/download/v{text}/{paket}" if paket else "",
    }
