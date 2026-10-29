"""Verschlüsselte Datensicherung (Spezifikation 05, D-2).

Eine Sicherung enthält die Datenbank und alle Dateien unter <DATA_DIR>/archiv. Aufbau,
damit sie sich auch ohne Kontorfreund öffnen lässt:

    MAGIC | Länge des Kopfs (4 Byte, big endian) | Kopf (JSON) | verschlüsselte Blöcke

Der Kopf bleibt lesbar, damit die Wiederherstellung Datum und Umfang schon vor dem
Kennwort zeigen kann; er enthält nur Anzahlen, keine Namen oder Beträge. Die Blöcke
ergeben ein ZIP-Archiv (db.sqlite3, archiv/…, inhalt.json), verschlüsselt mit
AES-256-GCM in Stücken zu 1 MiB. Schlüssel: scrypt über das Kennwort mit den Werten aus
kopf["kdf"]. Nonce je Block: die 7 Byte aus kopf["nonce"], die Blocknummer (4 Byte, big
endian) und ein Byte, das nur beim letzten Block 1 ist. MAGIC, Länge und Kopf sind als
zusätzliche Daten mit authentifiziert; eine gekürzte oder veränderte Datei fällt auf.
"""

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from django.conf import settings
from django.core.management import call_command
from django.db import DatabaseError, connection, connections
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from archive.models import Altbeleg
from contacts.models import Kontakt
from invoicing.models import Rechnung

logger = logging.getLogger(__name__)

MAGIC = b"KFSICH01"
BLOCK = 1 << 20
TAG = 16
# Werte, die OWASP für scrypt empfiehlt: 128 MiB Speicher, etwa eine Viertelsekunde.
KDF = {"name": "scrypt", "n": 1 << 17, "r": 8, "p": 1}
AUFBEWAHREN = 14
WARNEN_NACH = timedelta(days=7)
NAME = re.compile(r"kontorfreund-(\d{4}-\d{2}-\d{2}-\d{6})(?:-(\d+))?\.sicherung")
ANLAESSE = {
    "taeglich": "Täglich",
    "manuell": "Von Hand",
    "update": "Vor einem Update",
    "wiederherstellung": "Vor einer Wiederherstellung",
}
ORTE = {"hier": "Dieser Rechner", "ziel": "Zweiter Speicherort"}

FEHLER_SCHREIBEN = "Die letzte Sicherung konnte nicht geschrieben werden. Ist auf dem Rechner genug Platz frei?"
ZIEL_FEHLT = (
    "Der zweite Speicherort war nicht erreichbar. Ist die Platte angeschlossen?"
)
BESCHAEDIGT = "Die Sicherung ist beschädigt oder unvollständig."

# Eine Sicherung zur Zeit. RLock, weil die tägliche Sicherung die Sperre schon hält,
# wenn sie sichern() aufruft.
_sperre = threading.RLock()
_naechste_pruefung = 0.0


class SicherungFehler(Exception):
    """Fehler mit einem Text, der sich so dem Nutzer zeigen lässt."""


class FalschesKennwort(SicherungFehler):
    pass


def _b64(daten):
    return base64.b64encode(daten).decode()


def _ableiten(kennwort, kdf):
    return Scrypt(
        salt=base64.b64decode(kdf["salz"]),
        length=32,
        n=kdf["n"],
        r=kdf["r"],
        p=kdf["p"],
    ).derive(kennwort.encode())


def _nonce(praefix, nr, letzter):
    return praefix + nr.to_bytes(4, "big") + bytes([letzter])


def _zeit(text):
    return datetime.fromisoformat(text) if text else None


# ---------- Einstellungen dieser Installation ----------


def _konfig_pfad():
    return Path(settings.DATA_DIR) / "datensicherung.json"


def konfig():
    """Einstellungen und Schlüssel dieser Installation.

    Sie liegen neben der Datenbank, nicht in ihr, und kommen deshalb nie in eine
    Sicherung. Der Schlüssel steht hier, damit die tägliche Sicherung ohne Kennwort
    läuft; wer diesen Ordner lesen kann, hat ohnehin die Datenbank.
    """
    pfad = _konfig_pfad()
    if not pfad.is_file():
        return {}
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except ValueError:
        logger.exception("Einstellungen der Datensicherung sind unlesbar")
        return {}


def _aendern(**werte):
    with _sperre:
        pfad = _konfig_pfad()
        neu = {**konfig(), **werte}
        tmp = pfad.with_name(pfad.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(neu, f, indent=2)
        os.replace(tmp, pfad)


def eingerichtet():
    return "schluessel" in konfig()


def einrichten(kennwort):
    """Schlüssel für neue Sicherungen aus dem Kennwort ableiten.

    Ältere Sicherungen bleiben mit ihrem bisherigen Kennwort verschlüsselt.
    """
    kdf = {**KDF, "salz": _b64(os.urandom(16))}
    _aendern(kdf=kdf, schluessel=_b64(_ableiten(kennwort, kdf)))


def einstellen(ziel, aufbewahren):
    _aendern(ziel=ziel, aufbewahren=aufbewahren)


def zustand():
    """Stand für Seitenleiste und Übersicht; liest nur die Einstellungen, keine Ordner."""
    k = konfig()
    zuletzt, ziel_zuletzt = _zeit(k.get("zuletzt")), _zeit(k.get("ziel_zuletzt"))
    # Gemessen an der letzten Sicherung hier: Ruht das Programm, ändert sich auch nichts.
    ziel_veraltet = bool(k.get("ziel") and zuletzt) and (
        not ziel_zuletzt or zuletzt - ziel_zuletzt > WARNEN_NACH
    )
    if "schluessel" not in k:
        warnung = "Noch nicht eingerichtet"
    elif k.get("fehler"):
        warnung = "Letzte Sicherung fehlgeschlagen"
    elif ziel_veraltet:
        warnung = "Zweiter Speicherort nicht erreicht"
    else:
        warnung = ""
    return {
        "eingerichtet": "schluessel" in k,
        "zuletzt": zuletzt,
        "ziel": k.get("ziel", ""),
        "ziel_zuletzt": ziel_zuletzt,
        "ziel_fehler": k.get("ziel_fehler", ""),
        "fehler": k.get("fehler", ""),
        "aufbewahren": k.get("aufbewahren", AUFBEWAHREN),
        "warnung": warnung,
    }


# ---------- Automatisch ----------


def faellig():
    zuletzt = _zeit(konfig().get("zuletzt"))
    return zuletzt is None or timezone.localdate(zuletzt) < timezone.localdate()


def hat_daten():
    return any(_umfang(0).values())


def bei_bedarf():
    """Höchstens alle zehn Minuten prüfen und die tägliche Sicherung anstoßen."""
    global _naechste_pruefung
    if time.monotonic() < _naechste_pruefung:
        return
    _naechste_pruefung = time.monotonic() + 600
    if eingerichtet() and faellig():
        threading.Thread(target=_taeglich, name="Datensicherung", daemon=True).start()


def _taeglich():
    if not _sperre.acquire(blocking=False):
        return
    try:
        if faellig() and hat_daten():
            sichern("taeglich")
    except Exception:
        logger.exception("Tägliche Sicherung fehlgeschlagen")
    finally:
        _sperre.release()
        connection.close()


def vor_update(sender, plan=None, using="default", **kwargs):
    """Vor Migrationen den bisherigen Stand sichern (Spezifikation 05, D-2 und D-3)."""
    # Nur eine Datenbankdatei, nie die Testdatenbank im Arbeitsspeicher.
    datei = Path(connections[using].settings_dict["NAME"])
    if plan and eingerichtet() and datei.is_file():
        sichern("update")


# ---------- Sichern ----------


class _Verschluesselt:
    """Nimmt den Klartext des ZIP-Archivs an und schreibt ihn blockweise verschlüsselt."""

    def __init__(self, datei, schluessel, kopf):
        roh = json.dumps(kopf, ensure_ascii=False).encode()
        self.aad = MAGIC + len(roh).to_bytes(4, "big") + roh
        self.datei, self.aes = datei, AESGCM(schluessel)
        self.praefix = base64.b64decode(kopf["nonce"])
        self.puffer, self.nr = bytearray(), 0
        datei.write(self.aad)

    def write(self, daten):
        self.puffer += daten
        # Ein voller Block geht erst hinaus, wenn noch etwas folgt: Der letzte ist markiert.
        while len(self.puffer) > BLOCK:
            self._block(self.puffer[:BLOCK], letzter=False)
            del self.puffer[:BLOCK]
        return len(daten)

    def flush(self):
        """zipfile ruft flush() auf; geschrieben wird blockweise."""

    def abschliessen(self):
        self._block(self.puffer, letzter=True)

    def _block(self, klar, letzter):
        nonce = _nonce(self.praefix, self.nr, letzter)
        self.datei.write(self.aes.encrypt(nonce, bytes(klar), self.aad))
        self.nr += 1


def sicherungsordner():
    return Path(settings.DATA_DIR) / "sicherung"


def _dateiname(zeit):
    return f"kontorfreund-{zeit:%Y-%m-%d-%H%M%S}"


def _freier_name(ordner, zeit):
    basis = _dateiname(zeit)
    pfad, nr = ordner / f"{basis}.sicherung", 2
    while pfad.exists():
        pfad, nr = ordner / f"{basis}-{nr}.sicherung", nr + 1
    return pfad


def _umfang(dateien):
    def zahl(abfrage):
        try:
            return abfrage.count()
        except DatabaseError:  # Tabelle fehlt noch, etwa vor dem ersten Update
            return 0

    entwuerfe = Rechnung.objects.filter(status=Rechnung.Status.ENTWURF)
    return {
        "adressen": zahl(Kontakt.objects.all()),
        "rechnungen": zahl(Rechnung.objects.exclude(status=Rechnung.Status.ENTWURF)),
        "entwuerfe": zahl(entwuerfe),
        "altbelege": zahl(Altbeleg.objects.all()),
        "dateien": dateien,
    }


def _archivdateien():
    archiv = Path(settings.DATA_DIR) / "archiv"
    return (
        sorted(p for p in archiv.rglob("*") if p.is_file()) if archiv.is_dir() else []
    )


def umfang_jetzt():
    return _umfang(len(_archivdateien()))


def geschaetzte_groesse():
    """Ungefähre Größe einer Sicherung: Belege plus Datenbank."""
    db = Path(settings.DATA_DIR) / "db.sqlite3"
    return sum(p.stat().st_size for p in _archivdateien()) + (
        db.stat().st_size if db.is_file() else 0
    )


def _datenbank():
    """Momentaufnahme der Datenbank; geht auch, während das Programm sie benutzt."""
    connection.ensure_connection()
    kopie = sqlite3.connect(":memory:")
    try:
        connection.connection.backup(kopie)
        return kopie.serialize()
    finally:
        kopie.close()


def _einpacken(z, pfad, name):
    """Datei unkomprimiert ins Archiv legen (Belege sind meist schon PDF), mit SHA-256."""
    info = zipfile.ZipInfo.from_file(pfad, name)
    info.compress_type = zipfile.ZIP_STORED
    pruef = hashlib.sha256()
    with pfad.open("rb") as quelle, z.open(info, "w") as ziel:
        while stueck := quelle.read(BLOCK):
            pruef.update(stueck)
            ziel.write(stueck)
    return pruef.hexdigest()


def _schreiben(anlass, k):
    daten = Path(settings.DATA_DIR)
    hier = sicherungsordner()
    hier.mkdir(parents=True, exist_ok=True)
    dateien = _archivdateien()
    jetzt = timezone.localtime()
    kopf = {
        "format": 1,
        "programm": f"{settings.PRODUCT_NAME} ({settings.PRODUCT_EDITION})",
        "erstellt": jetzt.isoformat(timespec="seconds"),
        "anlass": anlass,
        "umfang": _umfang(len(dateien)),
        "kdf": k["kdf"],
        "nonce": _b64(os.urandom(7)),
    }
    migrationen = sorted(MigrationRecorder(connection).applied_migrations())
    inhalt = {"migrationen": [f"{a}.{n}" for a, n in migrationen], "dateien": {}}
    ziel = _freier_name(hier, jetzt)
    tmp = ziel.with_name(ziel.name + ".tmp")
    try:
        with tmp.open("wb") as roh:
            aus = _Verschluesselt(roh, base64.b64decode(k["schluessel"]), kopf)
            with zipfile.ZipFile(aus, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("db.sqlite3", _datenbank())
                for pfad in dateien:
                    name = pfad.relative_to(daten).as_posix()
                    inhalt["dateien"][name] = _einpacken(z, pfad, name)
                z.writestr("inhalt.json", json.dumps(inhalt, indent=2))
            aus.abschliessen()
        os.replace(tmp, ziel)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return ziel


def _sicherungen(ordner):
    """Sicherungsdateien eines Ordners, älteste zuerst; ein fehlender Ordner hat keine."""
    try:
        dateien = [p for p in ordner.iterdir() if NAME.fullmatch(p.name)]
    except OSError:
        return []
    return sorted(dateien, key=_reihenfolge)


def _reihenfolge(pfad):
    treffer = NAME.fullmatch(pfad.name)
    return treffer[1], int(treffer[2] or 1)


def _aufraeumen(ordner, behalten):
    for alt in _sicherungen(ordner)[:-behalten]:
        alt.unlink(missing_ok=True)


def _kopieren(datei, ordner, behalten):
    if not ordner.is_dir():
        raise FileNotFoundError(ordner)
    tmp = ordner / (datei.name + ".tmp")
    shutil.copyfile(datei, tmp)
    os.replace(tmp, ordner / datei.name)
    _aufraeumen(ordner, behalten)


def sichern(anlass="manuell"):
    """Sicherung schreiben, zum zweiten Speicherort kopieren und alte aufräumen.

    Gibt die neue Datei zurück und einen Hinweis, falls der zweite Speicherort fehlte.
    """
    with _sperre:
        k = konfig()
        behalten = k.get("aufbewahren", AUFBEWAHREN)
        try:
            datei = _schreiben(anlass, k)
        except Exception:
            _aendern(fehler=FEHLER_SCHREIBEN)
            raise
        _aufraeumen(datei.parent, behalten)
        jetzt = timezone.now().isoformat(timespec="seconds")
        werte, hinweis = {"zuletzt": jetzt, "fehler": ""}, ""
        if ziel := k.get("ziel"):
            try:
                _kopieren(datei, Path(ziel), behalten)
            except OSError as fehler:
                logger.warning("Zweiter Speicherort nicht erreichbar: %s", fehler)
                hinweis = ZIEL_FEHLT
            else:
                werte["ziel_zuletzt"] = jetzt
            werte["ziel_fehler"] = hinweis
        _aendern(**werte)
        return datei, hinweis


# ---------- Ansehen ----------


def _orte():
    orte = {"hier": sicherungsordner()}
    if ziel := konfig().get("ziel"):
        orte["ziel"] = Path(ziel)
    return orte


def finden(ort, name):
    ordner = _orte().get(ort)
    if ordner and NAME.fullmatch(name) and (ordner / name).is_file():
        return ordner / name
    return None


def eintrag(pfad):
    """Angaben zu einer Sicherungsdatei aus ihrem lesbaren Kopf."""
    e = {"name": pfad.name, "pfad": pfad, "groesse": pfad.stat().st_size, "kopf": None}
    try:
        e["kopf"] = kopf_lesen(pfad)
    except (OSError, SicherungFehler):
        return e
    e["erstellt"] = _zeit(e["kopf"]["erstellt"])
    e["anlass"] = ANLAESSE.get(e["kopf"]["anlass"], "")
    return e


def liste():
    """Alle Sicherungen, neueste zuerst; liegt eine an beiden Orten, steht sie einmal da."""
    gefunden = {}
    for ort, ordner in _orte().items():
        for pfad in _sicherungen(ordner):
            if pfad.name not in gefunden:
                gefunden[pfad.name] = {**eintrag(pfad), "ort": ort, "orte": []}
            gefunden[pfad.name]["orte"].append(ORTE[ort])
    return sorted(
        gefunden.values(), key=lambda e: _reihenfolge(e["pfad"]), reverse=True
    )


def kopf_lesen(pfad):
    """Lesbaren Kopf einer Sicherung prüfen und zurückgeben; braucht kein Kennwort."""
    with open(pfad, "rb") as f:
        return _kopf(f)[0]


def _kopf(f):
    """Kopf und die Bytes, die als zusätzliche Daten authentifiziert sind."""
    anfang = f.read(len(MAGIC) + 4)
    if anfang[: len(MAGIC)] != MAGIC:
        raise SicherungFehler("Das ist keine Sicherung von Kontorfreund.")
    laenge = int.from_bytes(anfang[len(MAGIC) :], "big")
    roh = f.read(laenge) if laenge <= 1 << 16 else b""
    try:
        kopf = json.loads(roh)
        kdf = kopf["kdf"]
        _zeit(kopf["erstellt"])
        # Grenzen, damit eine fremde Datei nicht beliebig viel Speicher verlangt.
        gueltig = (
            kopf["format"] == 1
            and kdf["name"] == "scrypt"
            and 128 * kdf["n"] * kdf["r"] <= 1 << 28
            and kdf["p"] <= 4
            and len(base64.b64decode(kopf["nonce"])) == 7
            and isinstance(kopf["umfang"], dict)
        )
    except (ValueError, KeyError, TypeError):
        gueltig = False
    if not gueltig:
        raise SicherungFehler(
            "Diese Sicherung lässt sich nicht lesen. Stammt sie aus einer neueren Version von Kontorfreund?"
        )
    return kopf, anfang + roh


def einlesen(datei):
    """Hochgeladene Sicherung, etwa von einem anderen Rechner, hier ablegen."""
    kopf, _ = _kopf(datei)
    datei.seek(0)
    hier = sicherungsordner()
    hier.mkdir(parents=True, exist_ok=True)
    zeit = timezone.localtime(_zeit(kopf["erstellt"]))
    vorhanden = hier / f"{_dateiname(zeit)}.sicherung"
    if vorhanden.is_file() and vorhanden.stat().st_size == datei.size:
        return vorhanden
    ziel = _freier_name(hier, zeit)
    with ziel.open("xb") as aus:
        for stueck in datei.chunks():
            aus.write(stueck)
    return ziel


# ---------- Wiederherstellen ----------


def _entschluesseln(quelle, schluessel, kopf, aad, ziel):
    aes, praefix = AESGCM(schluessel), base64.b64decode(kopf["nonce"])
    stueck, nr = quelle.read(BLOCK + TAG), 0
    while True:
        naechstes = quelle.read(BLOCK + TAG)
        try:
            ziel.write(aes.decrypt(_nonce(praefix, nr, not naechstes), stueck, aad))
        except InvalidTag:
            if nr == 0:
                raise FalschesKennwort(
                    "Das Kennwort passt nicht zu dieser Sicherung."
                ) from None
            raise SicherungFehler(BESCHAEDIGT) from None
        if not naechstes:
            return
        stueck, nr = naechstes, nr + 1


def _passt_zur_version(migrationen):
    loader = MigrationLoader(None, ignore_no_migrations=True)
    if not set(migrationen) <= {f"{a}.{n}" for a, n in loader.disk_migrations}:
        raise SicherungFehler(
            "Diese Sicherung stammt aus einer neueren Version von Kontorfreund. "
            "Bitte aktualisieren Sie zuerst das Programm."
        )


def _als_sqlite(db):
    """Datenbank aus der Sicherung im Arbeitsspeicher öffnen und prüfen."""
    kopie = sqlite3.connect(":memory:")
    try:
        kopie.deserialize(db)
        ok = kopie.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        kopie.close()
        raise SicherungFehler(BESCHAEDIGT)
    return kopie


def _auspacken(z, name, sha, neu):
    ziel = (neu / name.removeprefix("archiv/")).resolve()
    if not name.startswith("archiv/") or neu.resolve() not in ziel.parents:
        raise SicherungFehler(BESCHAEDIGT)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    pruef = hashlib.sha256()
    with z.open(name) as quelle, ziel.open("wb") as aus:
        while stueck := quelle.read(BLOCK):
            pruef.update(stueck)
            aus.write(stueck)
    if pruef.hexdigest() != sha:
        raise SicherungFehler(BESCHAEDIGT)


def _vorbereiten(klar, neu):
    """Archiv prüfen und die Belege nach `neu` auspacken; gibt die Datenbank zurück."""
    try:
        with zipfile.ZipFile(klar) as z:
            inhalt = json.loads(z.read("inhalt.json"))
            _passt_zur_version(inhalt["migrationen"])
            db = z.read("db.sqlite3")
            _als_sqlite(db).close()
            neu.mkdir()
            for name, sha in inhalt["dateien"].items():
                _auspacken(z, name, sha, neu)
    except (zipfile.BadZipFile, KeyError, ValueError) as fehler:
        raise SicherungFehler(BESCHAEDIGT) from fehler
    return db


def _einspielen(db):
    quelle = _als_sqlite(db)
    try:
        connection.ensure_connection()
        quelle.backup(connection.connection)
    finally:
        quelle.close()


def _tauschen(archiv, neu):
    alt = archiv.with_name("archiv.alt")
    shutil.rmtree(alt, ignore_errors=True)
    if archiv.exists():
        archiv.rename(alt)
    neu.rename(archiv)
    shutil.rmtree(alt, ignore_errors=True)


def wiederherstellen(pfad, kennwort):
    """Sicherung einspielen, nachdem der aktuelle Stand gesichert ist.

    Gibt den Kopf der Sicherung und die Datei mit dem vorherigen Stand zurück.
    """
    daten = Path(settings.DATA_DIR)
    neu = daten / "archiv.neu"
    shutil.rmtree(neu, ignore_errors=True)
    with _sperre, tempfile.TemporaryFile(dir=daten) as klar:
        with open(pfad, "rb") as f:
            kopf, aad = _kopf(f)
            schluessel = _ableiten(kennwort, kopf["kdf"])
            _entschluesseln(f, schluessel, kopf, aad, klar)
        # Erst alles prüfen und auspacken, dann den aktuellen Stand anfassen.
        try:
            db = _vorbereiten(klar, neu)
        except Exception:
            shutil.rmtree(neu, ignore_errors=True)
            raise
        if not eingerichtet():
            # Neuer Rechner: Die tägliche Sicherung läuft mit demselben Kennwort weiter.
            _aendern(kdf=kopf["kdf"], schluessel=_b64(schluessel))
        vorher, _ = sichern("wiederherstellung")
        _einspielen(db)
        _tauschen(daten / "archiv", neu)
    # Eine ältere Sicherung bekommt die Änderungen der aktuellen Version.
    call_command("migrate", interactive=False, verbosity=0)
    return kopf, vorher
