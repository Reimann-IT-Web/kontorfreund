"""Probelauf und Übernahme eines Imports (Spezifikation M-6).

`pruefen` geht jede Zeile durch wie eine Eingabe im Formular (`KontaktForm`
bzw. `ArtikelForm`, also mit denselben Pflichtfeldern und Formaten) und teilt
sie ein: neu, mögliche Dublette oder Fehler. Dubletten wie beim Anlegen von
Hand (`contacts.views.moegliche_dubletten`): bei Adressen gleiche E-Mail-Adresse
oder gleicher Name am selben Ort, bei Artikeln gleiche Bezeichnung, jeweils
gegen den Bestand und die Zeilen davor. Dubletten werden übersprungen, außer
der Nutzer will sie trotzdem anlegen.

Werte, die Kontorfreund anders schreibt, werden umgesetzt: Art sowie Kunde,
Interessent und Lieferant auch im Plural oder englisch, Anrede (unbekannte
fallen mit Hinweis weg), Land als Ländercode, vierstellige deutsche PLZ, bei
denen Excel die Null vorn verloren hat, Hausnummer aus eigener Spalte, Einheit
(„Stk“, „h“) und Preis in deutscher oder englischer Schreibweise. Eine Nummer
aus der Datei gilt, wenn sie frei ist; die übrigen Zeilen bekommen die Nummern
danach. Mobiltelefon und Fax werden weitere Telefonnummern mit der Bezeichnung
„Mobil“ bzw. „Fax“; die Spalte mit weiteren Nummern und Adressen hat je Zeile
„Bezeichnung: Wert“ wie im Export der Adressliste, E-Mail-Adressen erkennt der
Import am „@“. Mehrere Kategorien trennt ein Komma oder Semikolon; unbekannte
legt die Übernahme an.

`uebernehmen` speichert in einer Transaktion, was der Probelauf dann ergibt.
Das Protokoll verzeichnet jede Anlage wie eine Eingabe von Hand.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from artikel.forms import ArtikelForm
from artikel.models import Artikel
from artikel.views import _nummer as artikelnummer
from contacts.forms import (
    HOECHSTENS_KATEGORIEN,
    KontaktForm,
    kategorien_protokollieren,
    kontaktwege_lesen,
    kontaktwege_speichern,
)
from contacts.forms import nummer_lesen as kundennummer
from contacts.models import Kategorie, Kontakt, Kontaktweg
from core.templatetags.kf import zahl
from invoicing.beleg import EINHEIT_CODE, LAND_CODE

WAHR = {"ja", "j", "x", "1", "wahr", "true", "yes", "y"}
ARTEN = {
    "firma": "firma",
    "unternehmen": "firma",
    "company": "firma",
    "person": "person",
    "privat": "person",
    "privatperson": "person",
    "privatkunde": "person",
    "verbraucher": "person",
}
KATEGORIEN = {
    "kunde": "kunde",
    "kunden": "kunde",
    "kundin": "kunde",
    "customer": "kunde",
    "interessent": "interessent",
    "interessenten": "interessent",
    "interessentin": "interessent",
    "lead": "interessent",
    "lieferant": "lieferant",
    "lieferanten": "lieferant",
    "lieferantin": "lieferant",
    "supplier": "lieferant",
}
ANREDEN = {
    "herr": "Herr",
    "herrn": "Herr",
    "hr.": "Herr",
    "mr": "Herr",
    "mr.": "Herr",
    "frau": "Frau",
    "fr.": "Frau",
    "mrs": "Frau",
    "mrs.": "Frau",
    "ms": "Frau",
    "ms.": "Frau",
}
# Steht oft in der Anrede einer Firma und ist dort nur ein Platzhalter.
OHNE_ANREDE = {"firma", "familie"}
LAENDER = {code: name for name, code in LAND_CODE.items() if name} | {
    "D": "Deutschland",
    "DEU": "Deutschland",
    "GERMANY": "Deutschland",
    "BRD": "Deutschland",
}
EINHEITEN = {e.casefold(): e for e in EINHEIT_CODE} | {
    "stk": "Stück",
    "stk.": "Stück",
    "st": "Stück",
    "st.": "Stück",
    "stck": "Stück",
    "stck.": "Stück",
    "pcs": "Stück",
    "piece": "Stück",
    "std": "Std.",
    "stunde": "Std.",
    "stunden": "Std.",
    "h": "Std.",
    "hour": "Std.",
    "tage": "Tag",
    "tg.": "Tag",
    "day": "Tag",
    "monate": "Monat",
    "mon.": "Monat",
    "month": "Monat",
    "pauschal": "Pauschale",
    "psch.": "Pauschale",
    "pausch.": "Pauschale",
}
# Deutsch: Punkte für Tausender, Komma vor den Cent. Englisch nur, wenn eindeutig.
DEUTSCH = re.compile(r"-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?")
ENGLISCH = re.compile(r"-?(\d{1,3}(,\d{3})+|\d+)\.\d{1,2}")
HOECHSTE_NUMMER = 999_999_999


@dataclass
class Bericht:
    neu: list = field(default_factory=list)  # Objekte, ungespeichert, mit Nummer
    dubletten: list = field(default_factory=list)  # (Zeile, Name, womit)
    fehler: list = field(default_factory=list)  # (Zeile, [Meldungen])
    hinweise: list = field(default_factory=list)  # (Zeile, Meldung)


def pruefen(imp):
    spalte = {
        feld: imp.spalten.index(titel)
        for feld, titel in imp.zuordnung.items()
        if titel in imp.spalten
    }
    zeilen = [
        (nr, {feld: werte[i] for feld, i in spalte.items()}) for nr, werte in imp.zeilen
    ]
    bericht = Bericht()
    if imp.ziel == "kontakte":
        _kontakte(imp, zeilen, bericht)
    else:
        _artikel(imp, zeilen, bericht)
    return bericht


def uebernehmen(imp):
    with transaction.atomic():
        bericht = pruefen(imp)
        for objekt in bericht.neu:
            objekt.save()
            if getattr(objekt, "weitere", None):
                kontaktwege_speichern(objekt, objekt.weitere)
            if getattr(objekt, "kategorien_wahl", None):
                for kategorie in objekt.kategorien_wahl:
                    if kategorie.pk is None:
                        kategorie.save()
                objekt.kategorien.set(objekt.kategorien_wahl)
                kategorien_protokollieren(objekt, "")
    return bericht


def _fehler(form):
    return [
        f"{form.fields[name].label}: {meldung}" if name in form.fields else meldung
        for name, meldungen in form.errors.items()
        for meldung in meldungen
    ]


def _nummer(roh, lesen, vergeben, hinweise, zeichen):
    """Nummer aus der Datei, wenn sie gültig und frei ist, sonst None mit Hinweis."""
    if not roh:
        return None
    nummer = lesen(roh)
    if not nummer or nummer > HOECHSTE_NUMMER:
        hinweise.append(
            f"Die Nummer „{roh}“ übernimmt Kontorfreund nicht; es vergibt eine neue."
        )
        return None
    if nummer in vergeben:
        hinweise.append(
            f"Die Nummer {zeichen}-{nummer:04d} ist schon vergeben; es gibt eine neue."
        )
        return None
    return nummer


def _nummern_vergeben(bericht, vergeben):
    hoechste = max(vergeben, default=0)
    for objekt in bericht.neu:
        if objekt.nummer is None:
            hoechste += 1
            objekt.nummer = hoechste


# ---------- Adressen ----------


def _kontakte(imp, zeilen, bericht):
    namen, emails = {}, {}
    for k in Kontakt.objects.filter(gesperrt_am__isnull=True).only(
        "nummer", "anzeigename", "ort", "email"
    ):
        namen[(k.anzeigename.casefold(), k.ort.casefold())] = f"{k.kundennummer} {k}"
        if k.email:
            emails[k.email.casefold()] = f"{k.kundennummer} {k}"
    for w in Kontaktweg.objects.filter(
        art=Kontaktweg.Art.EMAIL, kontakt__gesperrt_am__isnull=True
    ).select_related("kontakt"):
        emails.setdefault(w.wert.casefold(), f"{w.kontakt.kundennummer} {w.kontakt}")
    vergeben = set(Kontakt.objects.values_list("nummer", flat=True))
    kategorien = {k.name.casefold(): k for k in Kategorie.objects.all()}
    for wort, kennung in KATEGORIEN.items():
        kategorien.setdefault(wort, Kategorie.vorgabe(kennung))
    angekuendigt = set()
    for nr, roh in zeilen:
        meldungen, hinweise = [], []
        daten = _kontakt_daten(roh, meldungen, hinweise)
        form = KontaktForm(data=daten)
        meldungen += [] if form.is_valid() else _fehler(form)
        weitere, fehler = kontaktwege_lesen(*_kontaktwege(roh))
        meldungen += fehler
        wahl = _kategorien(roh.get("kategorie", ""), kategorien, meldungen)
        if meldungen:
            bericht.fehler.append((nr, meldungen))
            continue
        kontakt = form.instance
        kontakt.weitere = weitere
        kontakt.kategorien_wahl = wahl or [k for k in [imp.kategorie] if k]
        kontakt.anzeigename = kontakt.name_berechnen()
        name = (kontakt.anzeigename.casefold(), kontakt.ort.casefold())
        adressen = [kontakt.email] + [
            w.wert for w in weitere if w.art == Kontaktweg.Art.EMAIL
        ]
        adressen = [a.casefold() for a in adressen if a]
        gleich = namen.get(name) or next(
            (emails[a] for a in adressen if a in emails), None
        )
        if gleich:
            bericht.dubletten.append((nr, kontakt.anzeigename, gleich))
            if not imp.dubletten_anlegen:
                continue
        kontakt.nummer = _nummer(
            roh.get("nummer", ""), kundennummer, vergeben, hinweise, "K"
        )
        if kontakt.nummer:
            vergeben.add(kontakt.nummer)
        namen.setdefault(name, f"Zeile {nr}")
        for adresse in adressen:
            emails.setdefault(adresse, f"Zeile {nr}")
        bericht.neu.append(kontakt)
        for kategorie in kontakt.kategorien_wahl:
            if kategorie.pk is None and kategorie.name not in angekuendigt:
                angekuendigt.add(kategorie.name)
                hinweise.append(
                    f"Die Kategorie „{kategorie}“ legt Kontorfreund neu an."
                )
        # Hinweise nur zu Zeilen, die übernommen werden.
        bericht.hinweise += [(nr, h) for h in hinweise]
    _nummern_vergeben(bericht, vergeben)


def _kategorien(text, kategorien, meldungen):
    """Kategorien einer Zeile, getrennt durch Komma oder Semikolon.

    `kategorien` hat die vorhandenen nach Namen (auch Plural und englisch für die
    vorgegebenen); unbekannte kommen ungespeichert dazu, für alle Zeilen dieselbe.
    """
    wahl = []
    for name in re.split(r"[,;\n]", text):
        name = " ".join(name.split())[:50].strip()
        if not name:
            continue
        kategorie = kategorien.get(name.casefold())
        if kategorie is None:
            neu = sum(k.pk is None for k in kategorien.values())
            if Kategorie.objects.count() + neu >= HOECHSTENS_KATEGORIEN:
                meldungen.append(
                    f"Kategorie „{name}“: höchstens {HOECHSTENS_KATEGORIEN} Kategorien."
                )
                continue
            kategorie = kategorien[name.casefold()] = Kategorie(name=name)
        if kategorie not in wahl:
            wahl.append(kategorie)
    return wahl


def _kontakt_daten(roh, meldungen, hinweise):
    """Formulardaten für KontaktForm aus den Werten einer Zeile."""
    daten = {feld: roh.get(feld, "") for feld in KontaktForm._meta.fields}
    art = daten["art"].casefold()
    if art and art not in ARTEN:
        meldungen.append(f"Art: „{daten['art']}“ ist weder Firma noch Person.")
    daten["art"] = ARTEN.get(art) or ("firma" if daten["firmenname"] else "person")
    anrede = daten["anrede"]
    daten["anrede"] = ANREDEN.get(anrede.casefold(), "")
    if anrede and not daten["anrede"] and anrede.casefold() not in OHNE_ANREDE:
        hinweise.append(
            f"Die Anrede „{anrede}“ kennt Kontorfreund nicht; sie bleibt leer."
        )
    if roh.get("hausnummer"):
        daten["strasse"] = f"{daten['strasse']} {roh['hausnummer']}".strip()
    daten["land"] = LAENDER.get(daten["land"].upper(), daten["land"]) or "Deutschland"
    if daten["land"] == "Deutschland" and re.fullmatch(r"\d{4}", daten["plz"]):
        daten["plz"] = "0" + daten["plz"]
    daten["xrechnung"] = daten["xrechnung"].casefold() in WAHR
    # Bei Personen steht in der Spalte für den Namen oft nur Vor- und Nachname.
    person = " ".join(t for t in [daten["vorname"], daten["nachname"]] if t)
    if daten["art"] == "person" and daten["firmenname"].casefold() == person.casefold():
        daten["firmenname"] = ""
    return daten


def _kontaktwege(roh):
    """(Arten, Bezeichnungen, Werte) für `kontaktwege_lesen`."""
    arten, bezeichnungen, werte = [], [], []
    for zeile in roh.get("weitere", "").splitlines():
        bezeichnung, _, wert = zeile.rpartition(": ")
        arten.append(Kontaktweg.Art.EMAIL if "@" in wert else Kontaktweg.Art.TELEFON)
        bezeichnungen.append(bezeichnung)
        werte.append(wert)
    for feld, bezeichnung in (("mobil", "Mobil"), ("fax", "Fax")):
        arten.append(Kontaktweg.Art.TELEFON)
        bezeichnungen.append(bezeichnung)
        werte.append(roh.get(feld, ""))
    return arten, bezeichnungen, werte


# ---------- Artikel ----------


def _artikel(imp, zeilen, bericht):
    namen = {
        a.bezeichnung.casefold(): f"{a.artikelnummer} {a}"
        for a in Artikel.objects.all()
    }
    vergeben = set(Artikel.objects.values_list("nummer", flat=True))
    for nr, roh in zeilen:
        meldungen, hinweise = [], []
        daten = {
            "bezeichnung": roh.get("bezeichnung", ""),
            "beschreibung": roh.get("beschreibung", ""),
            "einheit": _einheit(roh.get("einheit", ""), meldungen),
            "preis": _preis(roh.get("preis", ""), meldungen),
        }
        form = ArtikelForm(data=daten)
        meldungen += [] if form.is_valid() else _fehler(form)
        if meldungen:
            bericht.fehler.append((nr, meldungen))
            continue
        artikel = form.instance
        name = artikel.bezeichnung.casefold()
        if gleich := namen.get(name):
            bericht.dubletten.append((nr, artikel.bezeichnung, gleich))
            if not imp.dubletten_anlegen:
                continue
        artikel.nummer = _nummer(
            roh.get("nummer", ""), artikelnummer, vergeben, hinweise, "A"
        )
        if artikel.nummer:
            vergeben.add(artikel.nummer)
        namen.setdefault(name, f"Zeile {nr}")
        bericht.neu.append(artikel)
        bericht.hinweise += [(nr, h) for h in hinweise]
    _nummern_vergeben(bericht, vergeben)


def _einheit(text, meldungen):
    if not text:
        return "Stück"
    if einheit := EINHEITEN.get(text.casefold()):
        return einheit
    meldungen.append(
        f"Einheit: „{text}“ gibt es in Kontorfreund nicht. Möglich sind "
        + ", ".join(list(EINHEIT_CODE)[:-1])
        + f" und {list(EINHEIT_CODE)[-1]}."
    )
    return "Stück"


def _preis(text, meldungen):
    """Preis als Text für ArtikelForm („1234,5“); leer lässt das Formular ihn anmahnen."""
    roh = re.sub(r"\s|€|eur", "", text, flags=re.IGNORECASE)
    try:
        if DEUTSCH.fullmatch(roh):
            return zahl(Decimal(roh.replace(".", "").replace(",", ".")))
        if ENGLISCH.fullmatch(roh):
            return zahl(Decimal(roh.replace(",", "")))
    except InvalidOperation:
        pass
    if not text:
        return ""
    meldungen.append(f"Einzelpreis: „{text}“ ist kein Betrag.")
    # Die Zeile ist schon ein Fehler; das Formular soll den Preis nicht noch einmal melden.
    return "0"
