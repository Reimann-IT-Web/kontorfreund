"""Mehrere Firmen, jede mit eigenem Datenordner.

Jede Firma hat eigene Adressen, Belege, Nummernkreise, Benutzer und Datensicherung;
die Bücher zweier Firmen mischen sich nie. Die erste Firma liegt direkt im
Hauptordner, damit eine bestehende Installation bleibt, wie sie ist, jede weitere
in <Hauptordner>/firmen/<Nummer>. firmen.json im Hauptordner merkt sich, welche
zuletzt offen war.

Ohne Django, weil das Startprogramm (kontorfreund.py) den Ordner wählt, bevor Django
lädt. Zum Wechseln beendet sich der Server mit WECHSELN, und das Startprogramm
startet ihn mit der gewählten Firma neu.
"""

import json
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

UNTERORDNER = "firmen"
DATEI = "firmen.json"
# Rückgabewert des Servers: mit der Firma aus firmen.json neu starten.
WECHSELN = 75


@dataclass
class Firma:
    kennung: str  # leer für die erste Firma im Hauptordner
    ordner: Path
    name: str

    @property
    def nummer(self):
        return self.kennung or "1"

    @property
    def anzeigename(self):
        return self.name or f"Firma {self.nummer}"

    @property
    def leer(self):
        """Noch kein Konto angelegt, also auch nichts erfasst. Im Zweifel nicht leer."""
        try:
            return not _lesen(self.ordner, "SELECT COUNT(*) FROM konten_benutzer")
        except sqlite3.Error:
            return False


def ordner(haupt, kennung):
    return Path(haupt) / UNTERORDNER / kennung if kennung else Path(haupt)


def _lesen(ordner, sql):
    """Erster Wert der Abfrage, nur lesend; None, wenn es die Datenbank nicht gibt."""
    datei = Path(ordner) / "db.sqlite3"
    if not datei.is_file():
        return None
    with closing(sqlite3.connect(f"{datei.as_uri()}?mode=ro", uri=True)) as db:
        zeile = db.execute(sql).fetchone()
    return zeile[0] if zeile else None


def _abfrage(ordner, sql):
    """Wie _lesen, aber None auch, wenn es die Tabelle noch nicht gibt."""
    try:
        return _lesen(ordner, sql)
    except sqlite3.Error:
        return None


def _weitere(haupt):
    basis = Path(haupt) / UNTERORDNER
    if not basis.is_dir():
        return []
    return sorted(
        (p.name for p in basis.iterdir() if p.is_dir() and p.name.isdigit()), key=int
    )


def alle(haupt):
    return [
        Firma(
            kennung,
            ordner(haupt, kennung),
            _abfrage(
                ordner(haupt, kennung), "SELECT name FROM core_firmendaten WHERE id = 1"
            )
            or "",
        )
        for kennung in ["", *_weitere(haupt)]
    ]


def mehrere(haupt):
    return bool(_weitere(haupt))


def aktiv(haupt):
    try:
        kennung = json.loads((Path(haupt) / DATEI).read_text(encoding="utf-8"))["aktiv"]
    except (OSError, ValueError, KeyError, TypeError):
        return ""
    return kennung if kennung in _weitere(haupt) else ""


def waehlen(haupt, kennung):
    datei = Path(haupt) / DATEI
    tmp = datei.with_name(datei.name + ".tmp")
    tmp.write_text(json.dumps({"aktiv": kennung}), encoding="utf-8")
    os.replace(tmp, datei)


def anlegen(haupt):
    """Leeren Ordner für eine weitere Firma anlegen; Datenbank und Konto entstehen
    beim ersten Öffnen."""
    basis = Path(haupt) / UNTERORDNER
    basis.mkdir(mode=0o700, exist_ok=True)
    kennung = str(max(map(int, _weitere(haupt)), default=1) + 1)
    (basis / kennung).mkdir(mode=0o700)
    return kennung


def entfernen(haupt, kennung):
    """Nur eine weitere Firma, die gerade nicht offen ist und in der noch niemand ein
    Konto angelegt hat."""
    firma = Firma(kennung, ordner(haupt, kennung), "")
    if kennung not in _weitere(haupt) or kennung == aktiv(haupt) or not firma.leer:
        raise ValueError("Diese Firma lässt sich nicht entfernen.")
    shutil.rmtree(firma.ordner)


def umgebung(haupt, kennung):
    """Umgebungsvariablen, mit denen Kontorfreund diese Firma öffnet (config/settings.py)."""
    return {
        "APP_HAUPTORDNER": str(haupt),
        "APP_FIRMA": kennung,
        "APP_DATA_DIR": str(ordner(haupt, kennung)),
    }


def benachrichtigt(ordner):
    """Ob die Firma Benachrichtigungen per SMS eingeschaltet hat (App benachrichtigungen)."""
    return bool(
        _abfrage(
            ordner, "SELECT aktiv FROM benachrichtigungen_einstellung WHERE id = 1"
        )
    )
