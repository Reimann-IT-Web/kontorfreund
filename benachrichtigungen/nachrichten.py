"""Was über Telegram kommt und wann.

- Tagesübersicht, einmal am Tag ab der eingestellten Uhrzeit: heute fällige
  Wiedervorlagen, wie viele überfällig sind, Rechnungen, die neu überfällig sind,
  Rechnungen, für die das nächste Mahnschreiben fällig ist (je Stufe einmal; verschickt
  wird es nicht, das tut der Nutzer in den offenen Posten), neue Rechnungsentwürfe aus
  Verträgen (B-10) und Eingangsrechnungen, die bald zu zahlen sind. Steht nichts an,
  kommt nichts.
- Termine: Wiedervorlagen mit Uhrzeit, die eingestellte Zeit vorher.
- Ablage: sobald die tägliche Prüfung eine Datei neu als fehlend oder verändert findet.

Ohne Namen von Kunden und Lieferanten, denn mit Telegram gibt es keinen Vertrag zur
Auftragsverarbeitung. Gemeldet merkt sich jede Meldung; schlägt das Senden fehl,
kommt sie in der nächsten Runde wieder. Läuft Kontorfreund zur Uhrzeit nicht, kommt
die Übersicht beim Start.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from archive.models import Pruefung
from core.models import Firmendaten
from core.templatetags.kf import euro
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from vertraege import abrechnen
from wiedervorlagen.models import Wiedervorlage
from zahlungen import mahnen
from zahlungen.models import Mahnstufe

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
    posten = mahnen.posten()
    zu_mahnen = [
        (r, stufe)
        for r, stufe in mahnen.vorschlaege(posten, Mahnstufe.alle(), heute)
        if not _gemeldet("mahnstufe", f"{r.pk}:{stufe.stufe}")
    ]
    rechnungen = [
        r for r in posten if r.ueberfaellig and not _gemeldet("rechnung", str(r.pk))
    ]
    # Steht eine Rechnung schon unter „Zu mahnen“, nicht noch einmal als nicht bezahlt.
    gemahnt = {r.pk for r, _ in zu_mahnen}
    nicht_bezahlt = [r for r in rechnungen if r.pk not in gemahnt]
    vertragsentwuerfe = [
        r
        for r in Rechnung.objects.filter(
            vertrag__isnull=False, status=Rechnung.Status.ENTWURF
        )
        .select_related("vertrag")
        .order_by("pk")
        if not _gemeldet("entwurf", str(r.pk))
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
    if nicht_bezahlt:
        zeilen.append(
            "Nicht bezahlt: "
            + _aufzaehlen(
                [f"Rechnung {r.nummer} {euro(r.offen)}" for r in nicht_bezahlt]
            )
        )
    if zu_mahnen:
        zeilen.append(
            "Zu mahnen: "
            + _aufzaehlen(
                [f"Rechnung {r.nummer} {euro(r.offen)} ({s})" for r, s in zu_mahnen]
            )
        )
    if vertragsentwuerfe:
        zeilen.append(
            "Neue Entwürfe: "
            + _aufzaehlen(
                [f"{r.vertrag} {euro(r.summen()[2])}" for r in vertragsentwuerfe]
            )
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
        + [("mahnstufe", f"{r.pk}:{s.stufe}") for r, s in zu_mahnen]
        + [("entwurf", str(r.pk)) for r in vertragsentwuerfe]
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


def ablage():
    """Abweichungen, die die letzte Prüfung der Ablage neu gefunden hat, einmal."""
    letzte = Pruefung.letzte()
    if not letzte or _gemeldet("ablage", str(letzte.pk)):
        return None
    neu = [b["beleg"] for b in letzte.befunde if b["neu"]]
    if not neu:
        return None
    return Nachricht(
        f"{_kopf()}: Abgelegte Belege fehlen oder sind verändert: {_aufzaehlen(neu)}. "
        "Näheres in Kontorfreund unter Ablage.",
        [("ablage", str(letzte.pk))],
    )


def erinnern(jetzt=None):
    """Fällige Nachrichten senden; das Startprogramm ruft das alle fünf Minuten auf."""
    einstellung = Einstellung.laden()
    if not einstellung.bereit:
        return
    jetzt = jetzt or timezone.localtime()
    # Erst die fälligen Entwürfe anlegen, damit die Übersicht sie nennt.
    abrechnen.faellige(jetzt.date())
    for nachricht in [
        *termine(einstellung, jetzt),
        tagesuebersicht(einstellung, jetzt),
        ablage(),
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
