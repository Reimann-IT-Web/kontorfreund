"""Fassungen der Dokumente: setzen, ablegen und vermerken, was sich geändert hat.

Eine neue Fassung entsteht nur, wenn der Inhalt (`inhalt.py`) von der letzten abweicht;
sonst gilt die abgelegte weiter. Datum, Nummer und die Liste der Fassungen stehen nur im
PDF, nicht im verglichenen Inhalt.
"""

import hashlib
import json
import re
from pathlib import Path

import typst
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import Firmendaten
from invoicing.beleg import SCHRIFTEN

from . import inhalt
from .models import Fassung

VORLAGE = Path(__file__).parent / "typst" / "dokument.typ"
ORDNER = Path("archiv") / "dokumentation"
# Wo der Druck nicht umbrechen soll: „Art. 18“, „§ 14b“, „25.000 €“, „8 Jahre“, „EN 16931“.
BINDEN = re.compile(
    r"(§|Art\.|Abs\.|Rz\.|lit\.|Nr\.|EN) (?=\S)"
    r"|(\d) (?=€|%|Tage|Stunden|Minuten|Jahre|Zeichen|[A-Z]{2})"
)

# Je Dokument: Inhalt, Titel, Untertitel, Einleitung.
DOKUMENTE = {
    Fassung.Art.VERFAHREN: (
        inhalt.verfahren,
        "Verfahrensdokumentation",
        "nach den GoBD für Rechnungen, Belege und ihre Aufbewahrung",
        [
            "Diese Dokumentation beschreibt, wie das Unternehmen Rechnungen und andere "
            "Belege erstellt, empfängt, aufbewahrt und schützt, so dass ein "
            "sachverständiger Dritter die Abläufe in angemessener Zeit nachvollziehen "
            "kann (GoBD Rz. 151 ff.).",
            "Die Teile zum Programm hat Kontorfreund aus seinen Einstellungen erstellt; "
            "die eingerückten Angaben zum Betrieb stammen vom Inhaber. Ändert sich etwas, "
            "entsteht eine neue Fassung, und die früheren bleiben erhalten.",
        ],
    ),
    Fassung.Art.DATENSCHUTZ: (
        inhalt.datenschutz,
        "Verzeichnis von Verarbeitungstätigkeiten",
        "nach Art. 30 DSGVO, mit den technischen und organisatorischen Maßnahmen nach "
        "Art. 32 DSGVO",
        [
            "Das Verzeichnis führt auf, welche personenbezogenen Daten das Unternehmen "
            "wofür verarbeitet, an wen sie gehen, wann sie gelöscht werden und wie sie "
            "geschützt sind.",
            "Die Verarbeitungen in Kontorfreund und seine Schutzmaßnahmen hat das Programm "
            "selbst eingetragen; die eingerückten Angaben stammen vom Inhaber.",
        ],
    ),
}


def _schluessel(abschnitte):
    """{(Abschnitt, Teil): Blöcke} und {(Abschnitt, Teil): nummerierter Titel}."""
    bloecke, titel = {}, {}
    for i, a in enumerate(abschnitte, 1):
        for j, t in enumerate(a["teile"], 1):
            bloecke[a["titel"], t["titel"]] = t["bloecke"]
            titel[a["titel"], t["titel"]] = f"{i}.{j} {t['titel']}"
    return bloecke, titel


def aenderungen(alt, neu):
    """Nummerierte Titel der Teile, die neu oder anders sind oder wegfallen."""
    vorher, _ = _schluessel(alt)
    nachher, titel = _schluessel(neu)
    return [titel[k] for k, b in nachher.items() if vorher.get(k) != b] + [
        f"{k[1]} (entfallen)" for k in vorher if k not in nachher
    ]


def offen(abschnitte):
    """Wie viele Fragen der Inhaber noch beantworten muss."""
    return sum(
        "offen" in b for a in abschnitte for t in a["teile"] for b in t["bloecke"]
    )


def _nummeriert(abschnitte):
    return [
        {
            "titel": f"{i} {a['titel']}",
            "teile": [
                {**t, "titel": f"{i}.{j} {t['titel']}"}
                for j, t in enumerate(a["teile"], 1)
            ],
        }
        for i, a in enumerate(abschnitte, 1)
    ]


def druckdaten(fassung, frueher):
    _, titel, untertitel, einleitung = DOKUMENTE[fassung.art]
    firma = Firmendaten.laden()
    datum = f"{timezone.localtime(fassung.erstellt):%d.%m.%Y}"
    verlauf = inhalt.teil(
        "Bisherige und geltende Fassung",
        inhalt.tabelle(
            ["Fassung", "Datum", "Programm", "Erstellt von", "Geändert"],
            [
                [
                    str(f.nummer),
                    f"{timezone.localtime(f.erstellt):%d.%m.%Y}",
                    f.version,
                    str(f.erstellt_von or ""),
                    "\n".join(f.aenderungen) or "erste Fassung",
                ]
                for f in [*frueher, fassung]
            ],
            breit=[4],
        ),
        inhalt.absatz(
            "Alle Fassungen liegen in Kontorfreund unter Einstellungen › Dokumentation, "
            "in der Ablage mit Prüfsumme und damit in jeder Datensicherung."
        ),
    )
    return {
        "titel": titel,
        "untertitel": untertitel,
        "firma": firma.name,
        "kopf": [
            [name, inhalt.zeilen(wert)]
            for name, wert in (
                ("Unternehmen", firma.name),
                ("Fassung", f"{fassung.nummer} vom {datum}"),
                ("Programm", inhalt.programm()),
                ("Erstellt von", str(fassung.erstellt_von or "")),
            )
            if wert
        ],
        "einleitung": einleitung,
        "abschnitte": _nummeriert(
            [
                *fassung.inhalt,
                inhalt.abschnitt("Fassungen dieser Dokumentation", verlauf),
            ]
        ),
        "fuss": f"{titel} · {firma.name} · Fassung {fassung.nummer} vom {datum}"
        if firma.name
        else f"{titel} · Fassung {fassung.nummer} vom {datum}",
    }


def _binden(wert):
    if isinstance(wert, str):
        return BINDEN.sub(lambda m: (m[1] or m[2]) + " ", wert)
    if isinstance(wert, list):
        return [_binden(w) for w in wert]
    if isinstance(wert, dict):
        return {k: _binden(w) for k, w in wert.items()}
    return wert


def setzen(druck):
    return typst.compile(
        str(VORLAGE),
        font_paths=[str(SCHRIFTEN)],
        ignore_system_fonts=True,
        sys_inputs={"daten": json.dumps(_binden(druck))},
        pdf_standards="a-3b",
    )


def entwurf(art):
    """Der Inhalt, wie er jetzt wäre, mit gleichem Aufbau wie in einer gespeicherten Fassung."""
    return json.loads(json.dumps(DOKUMENTE[art][0]()))


def geltende(art, benutzer=None):
    """Die geltende Fassung; weicht der Inhalt ab, wird zuerst eine neue abgelegt."""
    abschnitte = entwurf(art)
    frueher = list(Fassung.objects.filter(art=art).order_by("nummer"))
    letzte = frueher[-1] if frueher else None
    daten = Path(settings.DATA_DIR)
    if letzte and letzte.inhalt == abschnitte and (daten / letzte.datei).is_file():
        return letzte
    fassung = Fassung(
        art=art,
        nummer=letzte.nummer + 1 if letzte else 1,
        erstellt_von=benutzer,
        version=settings.VERSION,
        inhalt=abschnitte,
        aenderungen=aenderungen(letzte.inhalt, abschnitte) if letzte else [],
    )
    pdf = setzen(druckdaten(fassung, frueher))
    relativ = ORDNER / f"{art}-fassung-{fassung.nummer}.pdf"
    ziel = daten / relativ
    ziel.parent.mkdir(parents=True, exist_ok=True)
    # Nie überschreiben: Gleichzeitig eine zweite Fassung mit derselben Nummer scheitert hier.
    with ziel.open("xb") as f:
        f.write(pdf)
    fassung.datei = relativ.as_posix()
    fassung.sha256 = hashlib.sha256(pdf).hexdigest()
    try:
        with transaction.atomic():
            fassung.save()
    except BaseException:
        ziel.unlink(missing_ok=True)
        raise
    return fassung
