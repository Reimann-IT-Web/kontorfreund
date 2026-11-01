"""Was über Telegram kommt und wann.

- Tagesübersicht, einmal am Tag ab der eingestellten Uhrzeit: heute fällige
  Wiedervorlagen, wie viele überfällig sind, Rechnungen, die neu überfällig sind, und
  Eingangsrechnungen, die bald zu zahlen sind. Steht nichts an, kommt nichts.
- Termine: Wiedervorlagen mit Uhrzeit, die eingestellte Zeit vorher.

Ohne Namen von Kunden und Lieferanten, denn mit Telegram gibt es keinen Vertrag zur
Auftragsverarbeitung. Gemeldet merkt sich jede Meldung; schlägt das Senden fehl,
kommt sie in der nächsten Runde wieder. Läuft Kontorfreund zur Uhrzeit nicht, kommt
die Übersicht beim Start.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from core.models import Firmendaten
from core.templatetags.kf import euro
from eingang.models import Eingangsrechnung
from wiedervorlagen.models import Wiedervorlage
from zahlungen import mahnen

from . import telegram
from .models import Einstellung, Gemeldet

# Eingangsrechnungen so viele Tage vor der Fälligkeit melden.
VORHER = 3
# Höchstens so viele Einträge je Zeile, damit die Nachricht kurz bleibt.
HOECHSTENS = 3


@dataclass
class Nachricht:
    text: str  # leer: nichts zu senden, nur als gemeldet merken
    meldungen: list  # (anlass, schluessel) für Gemeldet


def _gemeldet(anlass, schluessel):
    return Gemeldet.objects.filter(anlass=anlass, schluessel=schluessel).exists()


def _aufzaehlen(eintraege):
    rest = len(eintraege) - HOECHSTENS
    return "; ".join(eintraege[:HOECHSTENS]) + (
        f" und {rest} weitere" if rest > 0 else ""
    )


def _aufgabe(w):
    return f"{w.uhrzeit:%H:%M} {w.titel}" if w.uhrzeit else w.titel


def _offen(einstellung):
    if einstellung.empfaenger:
        return Wiedervorlage.offen_fuer(einstellung.empfaenger)
    return Wiedervorlage.objects.filter(erledigt_am__isnull=True)


def _kopf():
    return Firmendaten.laden().name or "Kontorfreund"


def tagesuebersicht(einstellung, jetzt):
    heute = jetzt.date()
    if jetzt.time() < einstellung.uhrzeit or _gemeldet("tag", heute.isoformat()):
        return None
    offen = _offen(einstellung)
    aufgaben = [_aufgabe(w) for w in offen.filter(faellig=heute)]
    ueberfaellig = offen.filter(faellig__lt=heute).count()
    rechnungen = [
        r
        for r in mahnen.posten()
        if r.ueberfaellig and not _gemeldet("rechnung", str(r.pk))
    ]
    eingang = [
        e
        for e in Eingangsrechnung.objects.filter(
            faellig__gte=heute, faellig__lte=heute + timedelta(days=VORHER)
        ).order_by("faellig")
        if not _gemeldet("eingang", str(e.pk))
    ]
    zeilen = []
    if aufgaben:
        zeilen.append(f"Heute: {_aufzaehlen(aufgaben)}")
    if ueberfaellig:
        zeilen.append(
            f"Überfällig: {ueberfaellig} Wiedervorlage{'n' if ueberfaellig > 1 else ''}"
        )
    if rechnungen:
        zeilen.append(
            "Nicht bezahlt: "
            + _aufzaehlen([f"Rechnung {r.nummer} {euro(r.offen)}" for r in rechnungen])
        )
    if eingang:
        zeilen.append(
            "Zu zahlen: "
            + _aufzaehlen(
                [
                    f"Nr. {e.nummer} {euro(e.zahlbetrag)} bis {e.faellig:%d.%m.}"
                    for e in eingang
                ]
            )
        )
    return Nachricht(
        f"{_kopf()}, {heute:%d.%m.}:\n" + "\n".join(zeilen) if zeilen else "",
        [("tag", heute.isoformat())]
        + [("rechnung", str(r.pk)) for r in rechnungen]
        + [("eingang", str(e.pk)) for e in eingang],
    )


def termine(einstellung, jetzt):
    if not einstellung.vorlauf:
        return []
    heute = jetzt.date()
    nachrichten = []
    for w in _offen(einstellung).filter(faellig=heute, uhrzeit__isnull=False):
        beginn = timezone.make_aware(datetime.combine(heute, w.uhrzeit))
        schluessel = f"{w.pk}:{heute.isoformat()}:{w.uhrzeit:%H%M}"
        if beginn - timedelta(
            minutes=einstellung.vorlauf
        ) <= jetzt < beginn and not _gemeldet("termin", schluessel):
            nachrichten.append(
                Nachricht(f"{_kopf()}: {_aufgabe(w)}", [("termin", schluessel)])
            )
    return nachrichten


def erinnern(jetzt=None):
    """Fällige Nachrichten senden; das Startprogramm ruft das alle fünf Minuten auf."""
    einstellung = Einstellung.laden()
    if not einstellung.bereit:
        return
    jetzt = jetzt or timezone.localtime()
    for nachricht in [
        *termine(einstellung, jetzt),
        tagesuebersicht(einstellung, jetzt),
    ]:
        if nachricht is None:
            continue
        if nachricht.text:
            try:
                telegram.senden(
                    einstellung.bot_schluessel, einstellung.chat, nachricht.text
                )
            except telegram.Fehler as fehler:
                # Nur den Stand, ohne Eintrag im Änderungsprotokoll.
                Einstellung.objects.filter(pk=1).update(
                    fehler=str(fehler), fehler_am=timezone.now()
                )
                return
            Einstellung.objects.filter(pk=1).update(
                gesendet_am=timezone.now(), fehler=""
            )
        for anlass, schluessel in nachricht.meldungen:
            Gemeldet.objects.get_or_create(anlass=anlass, schluessel=schluessel)
