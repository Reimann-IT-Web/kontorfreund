"""Unmittelbarer Datenzugriff für die Betriebsprüfung (§ 147 Abs. 6 AO, Spezifikation D-6).

Der Prüfer sieht dieselben Tabellen wie im Datenpaket (`auswertungen.pruefer`), dazu das
Rechnungsausgangsbuch und das Änderungsprotokoll, nur für den Prüfungszeitraum. Er
filtert und sortiert sie und öffnet die Belege. Ändern kann er nichts: Das verhindert
`konten.rechte.nur_lesen` für jede Anfrage eines Prüfers.
"""

from dataclasses import astuple, dataclass
from datetime import datetime
from pathlib import Path

from django.db.models import Min
from django.utils import timezone

from archive.models import Altbeleg
from auswertungen import buch, pruefer
from auswertungen.pruefer import BETRAG, DATUM, GANZ, MENGE, TEXT, Tabelle
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from protokoll.models import Eintrag

# Spalten mit dem Pfad einer Belegdatei und mit Prüfsummen.
DATEIEN = {"PDF", "XML", "Datei"}
RECHTS = {BETRAG, MENGE, GANZ}


@dataclass
class Ansicht:
    name: str
    tabelle: Tabelle
    fuss: list | None = None


def jahre():
    """Vom ersten Jahr mit Belegen bis heute."""
    erste = [
        d.year
        for d in (
            Rechnung.objects.filter(status=Rechnung.Status.FESTGESCHRIEBEN).aggregate(
                d=Min("datum")
            )["d"],
            Altbeleg.objects.aggregate(d=Min("datum"))["d"],
            Eingangsrechnung.objects.aggregate(d=Min("datum"))["d"],
        )
        if d
    ]
    heute = timezone.localdate().year
    return list(range(min([*erste, heute]), heute + 1))


def _ausgangsbuch(von, bis):
    zeilen = [z for z, _ in buch.zeilen(von, bis)]
    tabelle = Tabelle(
        "ausgangsbuch",
        "Rechnungsausgangsbuch",
        "Rechnungen, Stornos und Korrekturen mit Zahlungsstand, dazu die umsatzwirksamen "
        "Belege aus dem früheren Programm",
        [(name, art, "") for name, art in buch.SPALTEN],
        [list(astuple(z)) for z in zeilen],
    )
    return Ansicht(
        "ausgangsbuch", tabelle, buch.tabelle(zeilen)[-1] if zeilen else None
    )


def _protokoll(von, bis):
    eintraege = Eintrag.objects.filter(zeit__date__range=(von, bis)).order_by(
        "zeit", "pk"
    )
    tabelle = Tabelle(
        "protokoll",
        "Änderungsprotokoll",
        "Jede Anlage, Änderung und Löschung im Zeitraum mit Zeitpunkt, Benutzer, altem "
        "und neuem Wert, dazu Anmeldungen",
        [
            ("Zeit", DATUM, ""),
            ("Wer", TEXT, ""),
            ("Aktion", TEXT, ""),
            ("Art", TEXT, ""),
            ("Objekt", TEXT, "Nummer des Datensatzes"),
            ("Beschreibung", TEXT, ""),
            ("Änderungen", TEXT, "Feld: alter Wert → neuer Wert"),
        ],
        [
            [e.zeit, e.wer, e.get_aktion_display(), e.art, e.objekt_id, e.beschreibung]
            + ["; ".join(f"{f}: {alt} → {neu}" for f, alt, neu in e.aenderungen)]
            for e in eintraege
        ],
    )
    return Ansicht("protokoll", tabelle)


def ansichten(von, bis):
    """Alle Tabellen des Zeitraums und die Pfade der Belegdateien darin."""
    alle, belege = pruefer.tabellen(von, bis)
    return [
        _ausgangsbuch(von, bis),
        *(Ansicht(Path(t.datei).stem, t) for t in alle),
        _protokoll(von, bis),
    ], set(belege)


def anzeige(wert, art):
    if isinstance(wert, datetime):
        return f"{timezone.localtime(wert):%d.%m.%Y %H:%M}"
    return pruefer._wert(wert, art)


def sortieren(zeilen, spalte, absteigend=False):
    """Leere Werte zuletzt (absteigend zuerst); Datum und Beträge nach Wert, nicht Text."""

    def schluessel(zeile):
        wert = zeile[spalte]
        leer = wert is None or wert == ""
        return leer, 0 if leer else wert

    return sorted(zeilen, key=schluessel, reverse=absteigend)


def filtern(zeilen, spalten, suche):
    suche = suche.casefold()

    def text(zeile):
        paare = zip(zeile, spalten, strict=True)
        return " ".join(anzeige(w, art) for w, (_, art, _) in paare).casefold()

    return [z for z in zeilen if suche in text(z)]
