"""Teilnehmerliste auswerten (Spezifikation B-11).

Gelesen wird mit `importe.lesen` (CSV, XLSX, ODS). Die Zeile mit den Überschriften ist
die erste, in der „Name“ und mindestens zwei weitere bekannte Überschriften stehen;
was darüber steht, gilt nicht. Die Spalten ordnet `vorschlagen` an üblichen
Überschriften zu, eine zuletzt gespeicherte Zuordnung geht vor.

Jede Zeile darunter ist genau eins von:

- Teilnehmer: Name und dazu Kd-Nr. oder Anschrift.
- leer: nur Termin, Thema oder Link stehen darin (vorausgefüllte Zeilen).
- Abschnitt: Text in genau einer Zelle, kein Name. Unter einem Abschnitt, dessen
  Überschrift „storn“ enthält (Stornierung, Storno), ist jede Zeile storniert.
- storniert: im Storno-Abschnitt oder mit „storn“ in einer Zelle außer Termin, Thema
  und Link.
- übersprungen: Name ohne Kd-Nr. und Anschrift, gesperrte Adresse, oder kein Name.

Farben wertet Kontorfreund nicht aus. Was in den Zeilen steht, bleibt im Speicher; das
Anlegen (`serien.anlegen`) übernimmt nur die gewählten Teilnehmer.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from contacts.forms import HOECHSTE_KUNDENNUMMER, nummer_lesen
from contacts.models import (
    MANDAT_MONATE,
    Kontakt,
    mandatsreferenz_pruefen,
    monate_zurueck,
)
from contacts.views import moegliche_dubletten
from importe.lesen import _titel
from invoicing.models import Rechnung

from .models import Teilnehmer

# Feld → (Bezeichnung, übliche Überschriften in Kleinbuchstaben)
FELDER = {
    "kdnr": (
        "Kd-Nr.",
        [
            "kd-nr.",
            "kd-nr",
            "kdnr",
            "kd.-nr.",
            "kundennummer",
            "kunden-nr.",
            "kunden-nr",
        ],
    ),
    "verein": (
        "Verein/Büro",
        [
            "betreuungsverein/-büro",
            "betreuungsverein/büro",
            "verein/büro",
            "betreuungsverein",
            "verein",
            "büro",
            "firma",
            "firmenname",
        ],
    ),
    "anrede": ("Anrede", ["anrede"]),
    "titel": ("Titel", ["titel"]),
    "vorname": ("Vorname", ["vorname"]),
    "name": ("Name", ["name", "nachname"]),
    "adresse": (
        "Adresse",
        ["adresse", "anschrift", "straße", "strasse", "straße und hausnummer"],
    ),
    "plz": ("PLZ", ["plz", "postleitzahl"]),
    "ort": ("Ort", ["ort", "stadt"]),
    "telefon": ("Telefon", ["telefon", "tel.", "tel"]),
    "handy": ("Handy", ["handy", "mobil", "mobiltelefon"]),
    "fax": ("Fax", ["fax", "telefax"]),
    "email": ("E-Mail", ["e-mail", "email", "mail"]),
    "sepa": ("Sepa erteilt", ["sepa erteilt", "sepa", "sepa-mandat", "mandat"]),
    "termin": ("Termin", ["termin"]),
    "thema": ("Thema", ["thema", "veranstaltung"]),
    "link": ("Link", ["link", "einwahllink", "zugang"]),
}
# Was jede Zeile des Termins gleich hat; zählt nicht als Inhalt einer Zeile.
SERIENFELDER = ("termin", "thema", "link")
# Ohne diese Spalten lässt sich kein Teilnehmer erkennen.
PFLICHT = ("name",)

# Storno, storniert, Stornierung, stornieren, storn. – nicht aber ein Ort wie Storndorf.
STORNO = re.compile(r"\bstorn(?:o|iert|ierung|ieren|\.)", re.IGNORECASE)
DATUM = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})")
NUR_DATUM = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?: \d{1,2}:\d{2})?")


def _norm(text):
    return " ".join(text.casefold().split())


BEKANNT = {name: feld for feld, (_, namen) in FELDER.items() for name in namen}


def _datum(treffer):
    tag, monat, jahr = (int(t) for t in treffer.groups()[:3])
    if jahr < 100:
        jahr += 2000
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


def datum_lesen(text):
    """Ein Datum, das allein in der Zelle steht (Excel liefert es als TT.MM.JJJJ)."""
    treffer = NUR_DATUM.fullmatch(text.strip())
    return _datum(treffer) if treffer else None


def erstes_datum(text):
    """Das erste Datum in einem Text wie „03.12.2026, 10-13 Uhr“."""
    treffer = DATUM.search(text)
    return _datum(treffer) if treffer else None


def _kopfzeile(werte):
    felder = {BEKANNT.get(_norm(w)) for w in werte}
    return "name" in felder and len(felder - {None}) >= 3


def kopf_finden(spalten, zeilen):
    """(Spalten, Zeilen) ab der Zeile mit den Überschriften; Zeilen darüber fallen weg."""
    if _kopfzeile(spalten):
        return spalten, zeilen
    for i, (_, werte) in enumerate(zeilen[:20]):
        if _kopfzeile(werte):
            return _titel(werte), zeilen[i + 1 :]
    return spalten, zeilen


def vorschlagen(spalten, gespeichert=None):
    """Feld → Spaltentitel aus üblichen Überschriften; gespeicherte gehen vor."""
    zuordnung = {}
    for titel in spalten:
        feld = BEKANNT.get(_norm(titel))
        if feld and feld not in zuordnung:
            zuordnung[feld] = titel
    for feld, titel in (gespeichert or {}).items():
        if feld in FELDER and titel in spalten:
            zuordnung = {f: t for f, t in zuordnung.items() if t != titel}
            zuordnung[feld] = titel
    return zuordnung


@dataclass
class Zeile:
    """Eine Zeile der Liste mit dem, was Kontorfreund daraus macht."""

    nr: int
    werte: dict
    art: str  # teilnehmer, leer, abschnitt, storniert, uebersprungen
    abschnitt: str = ""
    grund: str = ""
    # Nur bei Teilnehmern:
    schluessel: str = ""
    kdnr: int | None = None
    kontakt: Kontakt | None = None
    gefunden: str = ""  # wie die vorhandene Adresse gefunden wurde
    daten: dict = field(default_factory=dict)
    abweichungen: list = field(default_factory=list)
    mandat_datum: date | None = None
    mandat_referenz: str = ""
    lastschrift_moeglich: bool = False
    zahlweg: str = Rechnung.Zahlweg.UEBERWEISUNG
    email: str = ""
    erste: bool = True
    hinweise: list = field(default_factory=list)
    # Wahl des Nutzers, vorbelegt
    waehlen: bool = True
    uebernehmen: bool = True
    beilage: bool = True

    @property
    def name(self):
        return " ".join(
            t
            for t in [self.werte.get(f, "") for f in ("titel", "vorname", "name")]
            if t
        )

    @property
    def verein(self):
        return self.werte.get("verein", "")


@dataclass
class Auswertung:
    zeilen: list
    warnungen: list

    @property
    def teilnehmer(self):
        return [z for z in self.zeilen if z.art == "teilnehmer"]

    @property
    def uebersprungen(self):
        return [z for z in self.zeilen if z.art in ("storniert", "uebersprungen")]

    @property
    def leere(self):
        return sum(1 for z in self.zeilen if z.art == "leer")

    def zeile(self, nr):
        return next((z for z in self.teilnehmer if z.nr == nr), None)


def anrede_lesen(text):
    text = _norm(text)
    if text.startswith("herr"):
        return "Herr"
    if text.startswith("frau"):
        return "Frau"
    return ""


def email_lesen(text):
    text = text.strip()
    if not text:
        return ""
    try:
        validate_email(text)
    except ValidationError:
        return None
    return text


def kontakt_daten(werte):
    """Felder einer Adresse aus der Zeile; mit Verein oder Büro eine Firma."""
    plz = werte.get("plz", "")
    if re.fullmatch(r"\d{4}", plz):
        plz = "0" + plz  # Excel verliert die Null vorn (06108 wird 6108)
    verein = werte.get("verein", "")
    return {
        "art": Kontakt.Art.FIRMA if verein else Kontakt.Art.PERSON,
        "firmenname": verein[:200],
        "anrede": anrede_lesen(werte.get("anrede", "")),
        "titel": werte.get("titel", "")[:50],
        "vorname": werte.get("vorname", "")[:100],
        "nachname": werte.get("name", "")[:100],
        "strasse": werte.get("adresse", "")[:200],
        "plz": plz[:10],
        "ort": werte.get("ort", "")[:100],
        "email": email_lesen(werte.get("email", "")) or "",
        "telefon": (werte.get("telefon", "") or werte.get("handy", ""))[:50],
    }


def _gleiche_person(kontakt, daten):
    return (
        kontakt.nachname.casefold() == daten["nachname"].casefold()
        and kontakt.vorname.casefold() == daten["vorname"].casefold()
    )


def abweichungen(kontakt, daten):
    """[(Feld, Bezeichnung, Liste, Kontorfreund)]; leere Zellen der Liste zählen nicht."""
    felder = [("strasse", "Adresse"), ("plz", "PLZ"), ("ort", "Ort")]
    if kontakt.art == Kontakt.Art.FIRMA and daten["art"] == Kontakt.Art.FIRMA:
        felder.insert(0, ("firmenname", "Verein/Büro"))
    person = kontakt.art == Kontakt.Art.PERSON or _gleiche_person(kontakt, daten)
    if kontakt.art == Kontakt.Art.PERSON:
        felder[:0] = [("vorname", "Vorname"), ("nachname", "Name")]
    if person:
        felder.append(("email", "E-Mail"))
    return [
        (f, bezeichnung, daten[f], getattr(kontakt, f))
        for f, bezeichnung in felder
        if daten[f] and daten[f].casefold() != getattr(kontakt, f).casefold()
    ]


def _anderer_kunde(kontakt, daten):
    """Ob die gefundene Adresse nach ihrem Namen jemand anderes ist.

    Bei Personen zählt der Nachname, bei Firmen der Firmenname; eine Firma mit
    Verein oder Büro in der Liste ist derselbe Kunde, wenn der Name gleich ist.
    """
    if kontakt.art == Kontakt.Art.PERSON:
        name = daten["nachname"]
        return bool(name) and name.casefold() != kontakt.nachname.casefold()
    if daten["art"] == Kontakt.Art.PERSON:
        return not _gleiche_person(kontakt, daten)
    name = daten["firmenname"]
    return bool(name) and name.casefold() != kontakt.firmenname.casefold()


def _referenz(kontakt, werte, kdnr):
    """Mandatsreferenz: vorhandene der Adresse, sonst die Kd-Nr. der Liste."""
    if kontakt and kontakt.mandat_referenz:
        return kontakt.mandat_referenz
    text = werte.get("kdnr", "").strip()
    try:
        mandatsreferenz_pruefen(text)
    except ValidationError:
        return str(kdnr) if kdnr else ""
    return text


def _art_der_zeile(werte_liste, werte):
    """leer, abschnitt, ohne_name oder None für eine Zeile mit Name."""
    if werte.get("name"):
        return None
    gefuellt = [w for w in werte_liste if w.strip()]
    serie = {werte.get(f, "") for f in SERIENFELDER} - {""}
    if all(w.strip() in serie for w in gefuellt):
        return "leer"
    return "abschnitt" if len(gefuellt) == 1 else "ohne_name"


def auswerten(spalten, zeilen, zuordnung, firma, termin="", thema=""):
    """Alle Zeilen der Liste mit Vorschlag; `termin` und `thema` erkennen Doppelte."""
    index = {f: spalten.index(t) for f, t in zuordnung.items() if t in spalten}
    ohne_storno = {index[f] for f in SERIENFELDER if f in index}
    ergebnis, warnungen = [], []
    abschnitt, storno_abschnitt = "", False
    gruppen = {}
    heute = date.today()
    for nr, werte_liste in zeilen:
        werte = {f: werte_liste[i].strip() for f, i in index.items()}
        art = _art_der_zeile(werte_liste, werte)
        if art == "leer":
            ergebnis.append(Zeile(nr, werte, "leer"))
            continue
        if art == "abschnitt":
            abschnitt = next(w for w in werte_liste if w.strip()).strip()
            storno_abschnitt = bool(STORNO.search(abschnitt))
            ergebnis.append(Zeile(nr, werte, "abschnitt", abschnitt=abschnitt))
            continue
        if art == "ohne_name":
            ergebnis.append(Zeile(nr, werte, "uebersprungen", abschnitt, "ohne Namen"))
            continue
        storno = storno_abschnitt or any(
            STORNO.search(w) for i, w in enumerate(werte_liste) if i not in ohne_storno
        )
        if storno:
            grund = "storniert"
            if storno_abschnitt:
                grund += f" (Abschnitt „{abschnitt}“)"
            ergebnis.append(Zeile(nr, werte, "storniert", abschnitt, grund))
            continue
        if not (werte.get("kdnr") or werte.get("adresse")):
            ergebnis.append(
                Zeile(
                    nr, werte, "uebersprungen", abschnitt, "ohne Kd-Nr. und Anschrift"
                )
            )
            continue
        z = Zeile(nr, werte, "teilnehmer", abschnitt)
        _teilnehmer(z, gruppen, firma, termin, thema, heute)  # gesperrt: übersprungen
        ergebnis.append(z)
    termine = {z.werte.get("termin", "") for z in ergebnis if z.art == "teilnehmer"}
    themen = {z.werte.get("thema", "") for z in ergebnis if z.art == "teilnehmer"}
    for name, werte_menge in (("Termin", termine), ("Thema", themen)):
        if len(werte_menge - {""}) > 1:
            feld = name.lower()
            erster = next(
                z.werte.get(feld, "") for z in ergebnis if z.art == "teilnehmer"
            )
            andere = [
                str(z.nr)
                for z in ergebnis
                if z.art == "teilnehmer" and z.werte.get(feld, "") not in ("", erster)
            ]
            warnungen.append(
                f"{name} weicht in Zeile {', '.join(andere)} von der ersten Zeile ab."
            )
    return Auswertung(ergebnis, warnungen)


def _teilnehmer(z, gruppen, firma, termin, thema, heute):
    werte = z.werte
    kdnr_text = werte.get("kdnr", "")
    z.kdnr = nummer_lesen(kdnr_text) if kdnr_text else None
    if z.kdnr and z.kdnr > HOECHSTE_KUNDENNUMMER:
        z.kdnr = None
    if kdnr_text and not z.kdnr:
        z.hinweise.append(f"Die Kd-Nr. „{kdnr_text}“ ist keine Nummer.")
    z.schluessel = f"k{z.kdnr}" if z.kdnr else f"z{z.nr}"
    z.daten = kontakt_daten(werte)
    email = email_lesen(werte.get("email", ""))
    if email is None:
        z.hinweise.append(f"„{werte['email']}“ ist keine gültige E-Mail-Adresse.")
    z.email = email or ""

    erste = gruppen.get(z.schluessel)
    if erste:
        z.kontakt, z.gefunden = erste.kontakt, erste.gefunden
        z.uebernehmen = False
        if erste.name.casefold() == z.name.casefold():
            z.hinweise.append(f"Steht schon in Zeile {erste.nr}.")
            z.waehlen = False
    else:
        gruppen[z.schluessel] = z
        if z.kdnr:
            z.kontakt = Kontakt.objects.filter(nummer=z.kdnr).first()
            z.gefunden = "Kd-Nr."
        else:
            treffer = moegliche_dubletten(Kontakt(**z.daten))
            if len(treffer) == 1:
                z.kontakt, z.gefunden = treffer[0], "Name oder E-Mail"
        if z.kontakt:
            z.abweichungen = abweichungen(z.kontakt, z.daten)
            z.uebernehmen = bool(z.abweichungen)
    k = z.kontakt
    if k and k.gesperrt_am:
        z.art = "uebersprungen"
        z.grund = f"Adresse {k.kundennummer} ist gesperrt (Datenschutz)"
        return
    if k and _anderer_kunde(k, z.daten):
        # Nie die Adresse eines anderen Kunden überschreiben oder ihm eine Rechnung
        # schreiben, nur weil die Nummer passt: der Nutzer entscheidet.
        z.waehlen = z.uebernehmen = False
        z.hinweise.append(
            f"Die Kd-Nr. gehört in Kontorfreund zu „{k.anzeigename}“. Ist das derselbe "
            "Kunde, wählen Sie die Zeile; sonst korrigieren Sie die Kd-Nr. in der Liste."
        )

    _mandat(z, firma, heute)

    if k:
        frueher = Teilnehmer.objects.filter(
            rechnung__kontakt=k,
            nachname__iexact=z.daten["nachname"],
            vorname__iexact=z.daten["vorname"],
        )
        z.erste = not frueher.exists()
        if (
            termin
            and frueher.filter(
                serie__termin__iexact=termin, serie__thema__iexact=thema
            ).exists()
        ):
            z.hinweise.append(
                "Für diesen Teilnehmer gibt es schon eine Rechnung zu diesem Termin."
            )
            z.waehlen = False
    if not z.email:
        z.hinweise.append("Ohne E-Mail-Adresse: die Rechnung gibt es zum Drucken.")


def _mandat(z, firma, heute):
    """Mandat aus „Sepa erteilt“ und der Vorschlag für den Zahlweg (B-12)."""
    k = z.kontakt
    sepa = z.werte.get("sepa", "")
    z.mandat_datum = datum_lesen(sepa) if sepa else None
    if sepa and not z.mandat_datum:
        z.hinweise.append(f"In „Sepa erteilt“ steht „{sepa}“; bitte prüfen.")
        z.waehlen = False
    if not z.mandat_datum:
        if k and k.mandat_vorhanden:
            z.hinweise.append(
                "An der Adresse ist ein Mandat eingetragen, in der Liste nicht."
            )
        return
    if k and k.mandat_datum and k.mandat_datum != z.mandat_datum:
        z.hinweise.append(
            f"An der Adresse steht ein Mandat vom {k.mandat_datum:%d.%m.%Y}; "
            f"Kontorfreund übernimmt das Datum der Liste ({z.mandat_datum:%d.%m.%Y})."
        )
    z.mandat_referenz = _referenz(k, z.werte, z.kdnr)
    if not z.mandat_referenz:
        z.hinweise.append("Ohne Kd-Nr. gibt es keine Mandatsreferenz.")
        return
    andere = Kontakt.objects.filter(mandat_referenz=z.mandat_referenz)
    if k:
        andere = andere.exclude(pk=k.pk)
    if andere.exists():
        z.hinweise.append(
            f"Die Mandatsreferenz {z.mandat_referenz} hat schon eine andere Adresse."
        )
        return
    if not firma.glaeubiger_id:
        z.hinweise.append(
            f"Mandat vom {z.mandat_datum:%d.%m.%Y}, aber Ihre Gläubiger-ID fehlt "
            "in den Einstellungen."
        )
        return
    z.lastschrift_moeglich = True
    genutzt = max(d for d in (z.mandat_datum, k.mandat_zuletzt if k else None) if d)
    if genutzt > monate_zurueck(heute, MANDAT_MONATE):
        z.zahlweg = Rechnung.Zahlweg.LASTSCHRIFT
        return
    seit = (
        f"zuletzt eingezogen am {k.mandat_zuletzt:%d.%m.%Y}"
        if k and k.mandat_zuletzt
        else f"vom {z.mandat_datum:%d.%m.%Y}, seitdem kein Einzug bekannt"
    )
    z.hinweise.append(
        f"Mandat {seit}. Nach {MANDAT_MONATE} Monaten ohne Einzug verfällt es; "
        "ist es noch gültig, wählen Sie Lastschrift."
    )


def wahl_uebernehmen(auswertung, post):
    """Die Wahl aus der Vorschau: Zeilen, Zahlweg, Übernahme und Beilage.

    Zeilen, die das Formular nicht kannte (`gezeigt`), behalten den Vorschlag.
    """
    gezeigt = {int(n) for n in post.getlist("gezeigt") if n.isdigit()}
    gewaehlt = set(post.getlist("waehlen"))
    uebernehmen = set(post.getlist("uebernehmen"))
    beilage = set(post.getlist("beilage"))
    for z in auswertung.teilnehmer:
        if z.nr not in gezeigt:
            continue
        nr = str(z.nr)
        z.waehlen = nr in gewaehlt
        z.uebernehmen = nr in uebernehmen and bool(z.abweichungen)
        z.beilage = nr in beilage
        zahlweg = post.get(f"zahlweg_{nr}")
        if zahlweg == Rechnung.Zahlweg.LASTSCHRIFT and z.lastschrift_moeglich:
            z.zahlweg = zahlweg
        elif zahlweg == Rechnung.Zahlweg.UEBERWEISUNG:
            z.zahlweg = zahlweg
