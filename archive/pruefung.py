"""Tägliche Prüfung der abgelegten Dateien (Spezifikation B-9).

Jede Datei, die Kontorfreund ablegt (Rechnungen samt XML, Angebote,
Auftragsbestätigungen, Mahnungen, Altbelege, Eingangsrechnungen), hat ihre
SHA-256-Prüfsumme in der Datenbank. `pruefen` vergleicht alle und speichert das
Ergebnis als `Pruefung`; was fehlt oder abweicht, zeigen Seitenleiste, Übersicht und
Ablage, bis eine spätere Prüfung die Datei wieder in Ordnung findet. Jede neue
Abweichung kommt ins Änderungsprotokoll und per Telegram (`nachrichten.ablage`).
`zurueckholen` legt die Originale aus den Datensicherungen zurück.

Einmal am Tag angestoßen wie die tägliche Sicherung, nach einer Anfrage
(`middleware`), und vom Befehl `erinnern`, damit sie auch läuft, wenn Kontorfreund
nur im Hintergrund läuft.
"""

import hashlib
import logging
import threading
import time
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.urls import reverse
from django.utils import timezone

from angebote.models import Angebot
from auftraege.models import Auftragsbestaetigung
from backups import sicherung
from dokumentation.models import Fassung
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from protokoll.erfassen import eintragen
from protokoll.models import Eintrag
from zahlungen.models import Mahnung

from .models import Altbeleg, Pruefung

logger = logging.getLogger(__name__)

FEHLT = "fehlt"
VERAENDERT = "veraendert"
# So steht es im Änderungsprotokoll.
VORFALL = {
    FEHLT: "fehlt oder lässt sich nicht lesen",
    VERAENDERT: "außerhalb von Kontorfreund verändert",
}

_sperre = threading.Lock()
_naechste_pruefung = 0.0


def _dateien():
    """(Beleg, Bezeichnung, Adresse der Ansicht, Datei, Prüfsumme) je abgelegter Datei."""
    for r in Rechnung.objects.exclude(datei=""):
        url = reverse("invoicing:bearbeiten", args=[r.pk])
        yield r, str(r), url, r.datei, r.sha256
        if r.xml_datei:
            yield r, f"{r} (XML)", url, r.xml_datei, r.xml_sha256
    for a in Angebot.objects.exclude(datei=""):
        yield a, str(a), reverse("angebote:bearbeiten", args=[a.pk]), a.datei, a.sha256
    for a in Auftragsbestaetigung.objects.exclude(datei=""):
        yield a, str(a), reverse("auftraege:bearbeiten", args=[a.pk]), a.datei, a.sha256
    for m in Mahnung.objects.select_related("rechnung"):
        yield m, str(m), reverse("zahlungen:mahnung", args=[m.pk]), m.datei, m.sha256
    for b in Altbeleg.objects.all():
        url = f"{reverse('archive:liste')}?q={b.nummer}"
        yield b, f"{b} (Altprogramm)", url, b.datei, b.sha256
    for e in Eingangsrechnung.objects.all():
        url = reverse("eingang:anzeigen", args=[e.pk])
        yield e, f"Eingangsrechnung {e.nummer}", url, e.datei, e.sha256
    for f in Fassung.objects.all():
        yield f, str(f), reverse("dokumentation:seite"), f.datei, f.sha256


def _zustand(datei, sha256):
    try:
        with (Path(settings.DATA_DIR) / datei).open("rb") as f:
            gleich = hashlib.file_digest(f, "sha256").hexdigest() == sha256
    except OSError:
        return FEHLT
    return None if gleich else VERAENDERT


def pruefen():
    """Alle abgelegten Dateien prüfen; Abweichungen, die neu sind, ins Protokoll."""
    with _sperre:
        vorher = Pruefung.letzte()
        bekannt = (
            {(b["datei"], b["zustand"]): b["seit"] for b in vorher.befunde}
            if vorher
            else {}
        )
        heute = timezone.localdate().isoformat()
        # Die Prüfsummen dauern; dabei hält keine Transaktion die Datenbank gesperrt,
        # sonst scheitern gleichzeitige Schreibzugriffe mit „database is locked“.
        dateien = list(_dateien())
        befunde, neu = [], []
        for beleg, bezeichnung, url, datei, sha256 in dateien:
            if not (zustand := _zustand(datei, sha256)):
                continue
            seit = bekannt.get((datei, zustand))
            befunde.append(
                {
                    "beleg": bezeichnung,
                    "url": url,
                    "datei": datei,
                    "zustand": zustand,
                    "seit": seit or heute,
                    "neu": seit is None,
                }
            )
            if seit is None:
                neu.append((beleg, datei, zustand))
        # Protokoll und Ergebnis zusammen, sonst stünde eine Abweichung beim nächsten
        # Mal noch einmal im Protokoll.
        with transaction.atomic():
            for beleg, datei, zustand in neu:
                eintragen(Eintrag.Aktion.ABLAGE, beleg, [[datei, "", VORFALL[zustand]]])
            return Pruefung.objects.create(anzahl=len(dateien), befunde=befunde)


def zurueckholen():
    """Was die letzte Prüfung fand, aus den Sicherungen zurückholen und neu prüfen.

    Gibt die zurückgeholten Dateien, den Ordner mit veränderten Fassungen (oder None)
    und die neue Prüfung zurück.
    """
    letzte = Pruefung.letzte()
    offen = {b["datei"] for b in letzte.befunde} if letzte else set()
    belege = {
        datei: (beleg, sha256)
        for beleg, _, _, datei, sha256 in _dateien()
        if datei in offen
    }
    geholt, beiseite = sicherung.zurueckholen(
        {datei: sha256 for datei, (_, sha256) in belege.items()}
    )
    for datei, erstellt in geholt.items():
        wann = f"{timezone.localtime(erstellt):%d.%m.%Y, %H:%M} Uhr"
        eintragen(
            Eintrag.Aktion.ZURUECK,
            belege[datei][0],
            [[datei, "", f"aus der Sicherung vom {wann}"]],
        )
    return geholt, beiseite, pruefen()


def faellig():
    letzte = Pruefung.letzte()
    return not letzte or timezone.localdate(letzte.zeit) < timezone.localdate()


def bei_bedarf():
    """Höchstens alle zehn Minuten nachsehen und die tägliche Prüfung anstoßen."""
    global _naechste_pruefung
    if time.monotonic() < _naechste_pruefung:
        return
    _naechste_pruefung = time.monotonic() + 600
    if faellig():
        threading.Thread(target=_taeglich, name="Belegprüfung", daemon=True).start()


def _taeglich():
    try:
        if faellig():
            pruefen()
    except Exception:
        logger.exception("Prüfung der Ablage fehlgeschlagen")
    finally:
        connection.close()
