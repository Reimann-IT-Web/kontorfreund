"""Aufbewahrungsfristen (Spezifikation D-1): was wie lange aufbewahrt werden muss.

Rechnungen und andere Buchungsbelege 8 Jahre (§ 147 Abs. 3 AO, § 14b UStG), Handels- und
Geschäftsbriefe wie Angebote, Auftragsbestätigungen und Mahnungen 6 Jahre, jeweils ab
Ende des Kalenderjahres. Danach dürfen sie weg, und die DSGVO verlangt, personenbezogene
Daten nicht länger als nötig zu speichern. Einmal im Jahr schlägt die Übersicht vor, was
abgelaufen ist (`hinweis`); gelöscht wird erst, wenn der Inhaber auf der Seite
„Aufbewahrungsfristen“ bestätigt. Die Entscheidung steht im Protokoll (Aktion `fristen`)
und gilt bis zum Jahresende.

`entfernen` löscht Belege auch für die Löschung auf Verlangen (contacts/datenschutz.py).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from angebote.models import Angebot
from auftraege.models import Auftragsbestaetigung
from contacts.models import Kontakt
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from protokoll.erfassen import eintragen, schwaerzen
from protokoll.models import Eintrag
from zahlungen.models import Mahnung, Zahlung

from .models import Altbeleg

BUCHUNGSBELEG, GESCHAEFTSBRIEF = 8, 6
# Rechnungen, Angebote und Auftragsbestätigungen nennen ihn gleich.
ENTWURF = Rechnung.Status.ENTWURF
# Beim Löschen zuerst, was andere schützt (PROTECT); Zahlungen gehen mit ihrer Rechnung.
REIHENFOLGE = [
    Auftragsbestaetigung,
    Angebot,
    Mahnung,
    Zahlung,
    Rechnung,
    Altbeleg,
    Eingangsrechnung,
]
ABGELAUFEN = "geschwärzt, Aufbewahrungsfrist abgelaufen"


def dateien(objekt):
    """Pfade der abgelegten Dateien eines Belegs im Datenordner."""
    return [p for p in (getattr(objekt, f, "") for f in ("datei", "xml_datei")) if p]


@dataclass
class Beleg:
    art: str
    nummer: str
    datum: date
    betrag: Decimal | None
    jahre: int
    objekt: models.Model
    # Adresse oder Empfänger, für die Übersicht
    name: str = ""

    @property
    def aufbewahren_bis(self):
        return date(self.datum.year + self.jahre, 12, 31)

    @property
    def dateien(self):
        return dateien(self.objekt)


def _name(kontakt):
    return kontakt.anzeigename if kontakt else ""


def belege(kontakt=None):
    """Was aufbewahrt werden muss, zu einer Adresse oder alles, nach Datum.
    Entwürfe gehören nicht dazu."""

    def von(abfrage, feld="kontakt"):
        return abfrage.filter(**{feld: kontakt}) if kontakt else abfrage

    alle = [
        Beleg(
            r.bezeichnung,
            r.nummer,
            r.datum,
            r.brutto,
            BUCHUNGSBELEG,
            r,
            _name(r.kontakt),
        )
        for r in von(Rechnung.objects.exclude(status=ENTWURF).select_related("kontakt"))
    ]
    alle += [
        Beleg(
            m.bezeichnung,
            m.rechnung.nummer,
            m.datum,
            m.gesamt,
            GESCHAEFTSBRIEF,
            m,
            _name(m.rechnung.kontakt),
        )
        for m in von(
            Mahnung.objects.select_related("rechnung__kontakt"), "rechnung__kontakt"
        )
    ]
    for art, modell in (
        ("Angebot", Angebot),
        ("Auftragsbestätigung", Auftragsbestaetigung),
    ):
        alle += [
            Beleg(
                art, a.nummer, a.datum, a.brutto, GESCHAEFTSBRIEF, a, _name(a.kontakt)
            )
            for a in von(
                modell.objects.exclude(status=ENTWURF).select_related("kontakt")
            )
        ]
    alle += [
        Beleg(
            a.get_art_display(),
            a.nummer,
            a.datum,
            a.betrag,
            BUCHUNGSBELEG if a.art in a.UMSATZWIRKSAM else GESCHAEFTSBRIEF,
            a,
            _name(a.kontakt) or a.empfaenger.split("\n")[0],
        )
        for a in von(Altbeleg.objects.select_related("kontakt"))
    ]
    alle += [
        Beleg(
            "Eingangsrechnung",
            e.nummer,
            e.datum,
            e.brutto,
            BUCHUNGSBELEG,
            e,
            e.lieferant,
        )
        for e in von(Eingangsrechnung.objects.all())
    ]
    return sorted(alle, key=lambda b: (b.datum, b.nummer))


def frist(alle):
    """Bis wann Belege aufbewahrt werden müssen; None ohne Belege."""
    return max((b.aufbewahren_bis for b in alle), default=None)


def loeschbar(alle):
    ende = frist(alle)
    return ende is None or ende < date.today()


def _geschuetzt_durch(objekt):
    """Was gelöscht sein muss, bevor dieser Beleg weg darf."""
    if isinstance(objekt, Rechnung):
        return [
            *objekt.mahnungen.all(),
            *Rechnung.objects.filter(Q(storno_zu=objekt) | Q(korrektur_zu=objekt)),
        ]
    if isinstance(objekt, Angebot):
        return list(Auftragsbestaetigung.objects.filter(angebot=objekt))
    return []


def abgelaufen():
    """Belege, deren Frist abgelaufen ist, ohne die, auf die noch ein aufzubewahrender
    Beleg verweist (Mahnung, Storno, Korrektur, Auftragsbestätigung)."""
    heute = date.today()
    alle = [b for b in belege() if b.aufbewahren_bis < heute]
    weg = {b.objekt for b in alle}
    while gesperrt := {
        o for o in weg if any(s not in weg for s in _geschuetzt_durch(o))
    }:
        weg -= gesperrt
    return [b for b in alle if b.objekt in weg]


def _mehrzahl(art, n):
    if n == 1:
        return f"1 {art}"
    return f"{n} {art}{'e' if art.endswith('ot') else 'en'}"


def gruppen(alle):
    """Die abgelaufenen Belege nach Jahr: Jahr, Belege, Anzahl je Art als Text."""
    jahre = {}
    for b in alle:
        jahre.setdefault(b.datum.year, []).append(b)
    return [
        {
            "jahr": jahr,
            "belege": liste,
            "arten": ", ".join(
                _mehrzahl(art, n)
                for art, n in Counter(
                    "Mahnung" if isinstance(b.objekt, Mahnung) else b.art for b in liste
                ).most_common()
            ),
        }
        for jahr, liste in sorted(jahre.items())
    ]


def entscheidung(jahr=None):
    """Was der Inhaber in diesem Jahr zu den abgelaufenen Belegen entschieden hat."""
    return Eintrag.objects.filter(
        aktion=Eintrag.Aktion.FRISTEN, zeit__year=jahr or timezone.localdate().year
    ).first()


def gesperrt_abgelaufen():
    """Gesperrte Adressen (Art. 18 DSGVO), deren Belege nicht mehr aufbewahrt werden
    müssen: Die Personen haben die Löschung verlangt."""
    return [
        k
        for k in Kontakt.objects.filter(gesperrt_am__isnull=False)
        if loeschbar(belege(k))
    ]


def naechste():
    """(Datum, Anzahl) der Belege, deren Frist als nächste endet; None ohne Belege."""
    heute = date.today()
    offen = [b.aufbewahren_bis for b in belege() if b.aufbewahren_bis >= heute]
    if not offen:
        return None
    ende = min(offen)
    return ende, offen.count(ende)


def hinweis():
    """Für die Übersicht, solange in diesem Jahr nicht entschieden ist: (abgelaufene
    Belege, gesperrte Adressen zum Löschen); None, wenn nichts ansteht."""
    if entscheidung():
        return None
    anzahl = (len(abgelaufen()), len(gesperrt_abgelaufen()))
    return anzahl if any(anzahl) else None


def wegraeumen(pfade):
    """Dateien löschen und leer gewordene Ordner im Archiv mit."""
    basis = Path(settings.DATA_DIR)
    archiv = basis / "archiv"
    for pfad in pfade:
        datei = basis / pfad
        datei.unlink(missing_ok=True)
        ordner = datei.parent
        while (
            ordner != archiv
            and ordner.is_relative_to(archiv)
            and ordner.is_dir()
            and not any(ordner.iterdir())
        ):
            ordner.rmdir()
            ordner = ordner.parent


def entfernen(objekte):
    """Belege und Entwürfe löschen, über Abfragen, denn ihr delete() verweigert das
    grundsätzlich. Rechnungen absteigend, damit Stornos und Korrekturen vor dem Original
    gehen; Zahlungen mit ihrer Rechnung. Die Dateien verschwinden nach dem Commit.
    Gibt alles Gelöschte zurück, mit seiner Nummer fürs Schwärzen."""
    objekte = list(objekte)
    objekte += Zahlung.objects.filter(
        rechnung__in=[o for o in objekte if isinstance(o, Rechnung)]
    )
    objekte.sort(key=lambda o: (REIHENFOLGE.index(type(o)), -o.pk))
    for o in objekte:
        type(o).objects.filter(pk=o.pk).delete()
    pfade = [p for o in objekte for p in dateien(o)]
    transaction.on_commit(lambda: wegraeumen(pfade))
    return objekte


def vermerken(text):
    eintragen(Eintrag.Aktion.FRISTEN, beschreibung=text)


@transaction.atomic
def loeschen(jahre):
    """Die abgelaufenen Belege dieser Jahre löschen und zurückgeben."""
    weg = [b for b in abgelaufen() if b.datum.year in jahre]
    schwaerzen(entfernen(b.objekt for b in weg), ABGELAUFEN)
    return weg
