"""Übernahme von Belegen aus den PDF-Dateien des Altprogramms.

Gelesen werden nur PDFs, die das Altprogramm erzeugt und in seiner Ablage
gespeichert hat. Dessen Datenbank wird bewusst nicht verwendet.
"""

import hashlib
import logging
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from pypdf import PdfReader

from contacts.models import Kontakt

from .models import Altbeleg

NUMMER = re.compile(r"^(Rechnung|Storno|Gutschrift|Angebot) Nr\.:\s*(\S+)\s*$", re.M)
DATUM = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
KUNDE = re.compile(r"^Kunden-Nr\.:\s*(\d+)", re.M)
BEZUG = re.compile(r"zu Rechnung Nr\.:\s*(\S+)")
SUMME = re.compile(r"^Gesamtsumme\s+(-?[\d.]+,\d{2})\s*€", re.M)
MAHNUNG = re.compile(r"^(\d\.\s*)?Mahnung\b|^Zahlungserinnerung\b", re.M)
ENTWURF = re.compile(r"-- ENTWURF --")
RUECKSENDEZEILE = re.compile(r"^(.+?) - .+? - \d{5} \S+")
PLZ_ORT = re.compile(r"^(\d{5})\s+(.+)$")
ANREDE = re.compile(r"^(Herrn?|Frau)\s+(.+)$")
# Anrede ohne Namen, ggf. mit Titeln („Frau“, „Frau Prof. Dr.“) – der Name folgt in der nächsten Zeile.
ANREDE_ALLEIN = re.compile(r"^(Herrn?|Frau)(\s+\S+\.)*$")

# Mitgelieferte Beispielbelege des Altprogramms gehören nicht zu den eigenen Daten.
BEISPIEL_ABSENDER = {"Musterfirma GmbH"}

ARTEN = {
    "Rechnung": Altbeleg.Art.RECHNUNG,
    "Storno": Altbeleg.Art.STORNO,
    "Gutschrift": Altbeleg.Art.GUTSCHRIFT,
    "Angebot": Altbeleg.Art.ANGEBOT,
}


class NichtUebernommen(Exception):
    """Datei ist kein übernehmbarer Beleg; die Nachricht nennt den Grund."""


@dataclass
class Beleg:
    art: str
    nummer: str
    datum: date
    absender: str
    kundennummer: int | None
    anschrift: dict
    empfaenger: str
    betrag: Decimal | None
    bezug: str
    pfad: Path
    sha256: str


@dataclass
class Bericht:
    belege: list = field(default_factory=list)
    uebersprungen: Counter = field(default_factory=Counter)
    doppelt: list = field(default_factory=list)
    abweichend: list = field(default_factory=list)
    unlesbar: list = field(default_factory=list)
    bereits_uebernommen: int = 0
    neue_kontakte: int = 0
    vorhandene_kontakte: int = 0
    anschrift_unsicher: list = field(default_factory=list)
    zusammengefuehrt: list = field(default_factory=list)

    def anzahl_je_art(self):
        return Counter((b.absender, b.art) for b in self.belege)

    def umsatz_je_jahr(self):
        summen = defaultdict(Decimal)
        for b in self.belege:
            if b.art in Altbeleg.UMSATZWIRKSAM and b.betrag is not None:
                summen[b.datum.year] += b.betrag
        return dict(sorted(summen.items()))


def pdf_text(pfad):
    # Warnungen zu eingebetteten Schriften betreffen nur die Darstellung, nicht den Text.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return "\n".join((seite.extract_text() or "") for seite in PdfReader(pfad).pages)


def _betrag(text):
    return Decimal(text.replace(".", "").replace(",", "."))


def anschrift_zerlegen(zeilen):
    """Anschriftblock (wie gedruckt) in Felder einer Adresse zerlegen."""
    zeilen = [z.strip() for z in zeilen if z.strip() and z.strip() != "Firma"]
    for i in range(len(zeilen) - 1):
        if ANREDE_ALLEIN.match(zeilen[i]):
            zeilen[i : i + 2] = [f"{zeilen[i]} {zeilen[i + 1]}"]
            break
    plz = ort = strasse = ""
    sicher = False
    if zeilen and (treffer := PLZ_ORT.match(zeilen[-1])):
        plz, ort = treffer.groups()
        zeilen = zeilen[:-1]
        if zeilen:
            strasse = zeilen.pop()
            sicher = True
    felder = {
        "art": Kontakt.Art.FIRMA,
        "firmenname": "",
        "zusatz": "",
        "anrede": "",
        "titel": "",
        "vorname": "",
        "nachname": "",
        "strasse": strasse,
        "plz": plz,
        "ort": ort,
    }
    person = next((i for i, z in enumerate(zeilen) if ANREDE.match(z)), None)
    if person is not None:
        anrede, name = ANREDE.match(zeilen.pop(person)).groups()
        teile = name.split()
        felder["anrede"] = "Frau" if anrede == "Frau" else "Herr"
        felder["titel"] = " ".join(t for t in teile[:-1] if t.endswith("."))
        felder["vorname"] = " ".join(t for t in teile[:-1] if not t.endswith("."))
        felder["nachname"] = teile[-1] if teile else ""
    if zeilen:
        felder["firmenname"] = zeilen[0]
        felder["zusatz"] = ", ".join(zeilen[1:])
    else:
        felder["art"] = Kontakt.Art.PERSON
    sicher = sicher and bool(felder["firmenname"] or felder["nachname"])
    return felder, sicher


def auslesen(text, pfad, sha256):
    """Beleg aus dem Text eines PDFs lesen; wirft NichtUebernommen mit Grund."""
    if MAHNUNG.search(text):
        raise NichtUebernommen("Mahnung")
    if not (nummer := NUMMER.search(text)):
        raise NichtUebernommen("kein Beleg")
    art = ARTEN[nummer.group(1)]
    if nummer.group(2) == "NEU" or ENTWURF.search(text):
        raise NichtUebernommen("Entwurf")
    if not (datum := DATUM.search(text, nummer.end())):
        raise NichtUebernommen("unlesbar: kein Datum")
    tag, monat, jahr = (int(t) for t in datum.groups())

    zeilen = text.splitlines()
    ruecksende = next(
        (i for i, z in enumerate(zeilen) if RUECKSENDEZEILE.match(z.strip())), None
    )
    if ruecksende is None:
        raise NichtUebernommen("unlesbar: keine Anschrift")
    anschrift, sicher = anschrift_zerlegen(zeilen[:ruecksende])
    anschrift["sicher"] = sicher

    summen = SUMME.findall(text)
    betrag = _betrag(summen[-1]) if summen else None
    if betrag is not None and art in (Altbeleg.Art.STORNO, Altbeleg.Art.GUTSCHRIFT):
        betrag = -abs(betrag)
    if betrag is None and art in Altbeleg.UMSATZWIRKSAM:
        raise NichtUebernommen("unlesbar: keine Gesamtsumme")

    kunde = KUNDE.search(text)
    bezug = BEZUG.search(text)
    return Beleg(
        art=art,
        nummer=nummer.group(2),
        datum=date(jahr, monat, tag),
        absender=RUECKSENDEZEILE.match(zeilen[ruecksende].strip()).group(1).strip(),
        kundennummer=int(kunde.group(1)) if kunde else None,
        anschrift=anschrift,
        empfaenger="\n".join(z.strip() for z in zeilen[:ruecksende] if z.strip()),
        betrag=betrag,
        bezug=bezug.group(1) if bezug else "",
        pfad=pfad,
        sha256=sha256,
    )


def pruefen(ordner, leser=pdf_text):
    """Alle PDFs lesen und einen Bericht erstellen, ohne etwas zu speichern."""
    bericht = Bericht()
    vorhanden = set(Altbeleg.objects.values_list("sha256", flat=True))
    gesehen = {}
    for pfad in sorted(Path(ordner).rglob("*.pdf")):
        sha256 = hashlib.sha256(pfad.read_bytes()).hexdigest()
        if sha256 in vorhanden:
            bericht.bereits_uebernommen += 1
            continue
        try:
            beleg = auslesen(leser(pfad), pfad, sha256)
        except NichtUebernommen as grund:
            text = str(grund)
            if text.startswith("unlesbar"):
                bericht.unlesbar.append((pfad.name, text))
            else:
                bericht.uebersprungen[text] += 1
            continue
        except Exception as fehler:  # beschädigte PDFs dürfen den Lauf nicht abbrechen
            bericht.unlesbar.append(
                (pfad.name, f"unlesbar: {fehler.__class__.__name__}")
            )
            continue
        if beleg.absender in BEISPIEL_ABSENDER:
            bericht.uebersprungen["Beispielbeleg des Altprogramms"] += 1
            continue
        schluessel = (beleg.absender, beleg.art, beleg.nummer)
        if erster := gesehen.get(schluessel):
            if (beleg.datum, beleg.betrag) == (erster.datum, erster.betrag):
                bericht.doppelt.append((pfad.name, erster.pfad.name))
                continue
            # Gleiche Nummer, andere Fassung: die jüngere gilt, beide werden gemeldet.
            bericht.abweichend.append((erster.pfad.name, pfad.name))
            if beleg.datum < erster.datum:
                continue
            bericht.belege.remove(erster)
        gesehen[schluessel] = beleg
        if not beleg.anschrift["sicher"]:
            bericht.anschrift_unsicher.append(pfad.name)
        bericht.belege.append(beleg)
    bericht.belege.sort(key=lambda b: (b.datum, b.nummer))
    return bericht


def _kontakt_fuer(beleg, cache):
    """Adresse zum Beleg finden oder anlegen; jüngste Anschrift und Nummer gewinnen."""
    felder = {k: v for k, v in beleg.anschrift.items() if k != "sicher"}
    entwurf = Kontakt(
        **felder,
        kategorie=Kontakt.Kategorie.KUNDE,
        notiz=f"Aus {beleg.absender or 'dem Altprogramm'} übernommen.",
    )
    name = entwurf.name_berechnen().casefold()
    # Das Altprogramm hat manchen Kunden später neu nummeriert; der Name verbindet beide.
    treffer = cache.get(beleg.kundennummer) or cache.get(name)
    if treffer:
        kontakt, angelegt = treffer
        if angelegt:
            for feld, wert in felder.items():
                setattr(kontakt, feld, wert)
            if (
                beleg.kundennummer
                and not Kontakt.objects.filter(nummer=beleg.kundennummer).exists()
            ):
                kontakt.nummer = beleg.kundennummer
            kontakt.save()
        neu = False
    else:
        kontakt = None
        nummer_frei = False
        if beleg.kundennummer:
            vorhanden = Kontakt.objects.filter(nummer=beleg.kundennummer).first()
            # Nur zuordnen, wenn auch der Name passt; sonst ist die Nummer zufällig belegt.
            if vorhanden and vorhanden.anzeigename.casefold() == name:
                kontakt = vorhanden
            nummer_frei = vorhanden is None
        neu = kontakt is None
        if neu:
            kontakt = entwurf
            if nummer_frei:
                kontakt.nummer = beleg.kundennummer
            kontakt.save()
        treffer = (kontakt, neu)
    cache[name] = treffer
    if beleg.kundennummer:
        cache[beleg.kundennummer] = treffer
    return kontakt, neu


def uebernehmen(bericht):
    """Belege aus einem geprüften Bericht speichern und die PDFs ins Archiv kopieren."""
    ziel = Path(settings.DATA_DIR) / "archiv" / "altbelege"
    cache = {}
    with transaction.atomic():
        for beleg in bericht.belege:
            kontakt, neu = _kontakt_fuer(beleg, cache)
            bericht.neue_kontakte += neu
            relativ = (
                Path(str(beleg.datum.year))
                / f"{beleg.art}-{beleg.nummer}-{beleg.sha256[:8]}.pdf"
            )
            (ziel / relativ).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(beleg.pfad, ziel / relativ)
            Altbeleg.objects.create(
                art=beleg.art,
                nummer=beleg.nummer,
                datum=beleg.datum,
                absender=beleg.absender,
                kontakt=kontakt,
                empfaenger=beleg.empfaenger,
                betrag=beleg.betrag,
                bezug=beleg.bezug,
                datei=(Path("archiv") / "altbelege" / relativ).as_posix(),
                sha256=beleg.sha256,
                originalname=beleg.pfad.name,
            )
    kontakte = {k.pk: k for k, _ in cache.values()}
    bericht.vorhandene_kontakte = len(kontakte) - bericht.neue_kontakte
    nummern = defaultdict(set)
    for schluessel, (kontakt, _) in cache.items():
        if isinstance(schluessel, int):
            nummern[kontakt.pk].add(schluessel)
    bericht.zusammengefuehrt = sorted(
        (kontakte[pk].anzeigename, sorted(alle))
        for pk, alle in nummern.items()
        if len(alle) > 1
    )
    return bericht
