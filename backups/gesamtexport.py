"""Gesamtexport (Spezifikation D-1 Komplettexport, D-6 Archivexport).

Alle Daten und Belege in einem ZIP, das sich ohne Kontorfreund lesen lässt: je Tabelle
eine CSV-Datei (wie die Exporte der Listen: UTF-8 mit BOM, Semikolon, Dezimalkomma, Werte
so, wie sie auf dem Bildschirm stehen), die Belege und Dateien im Original unter ihrem
Pfad im Archiv und eine LIESMICH.txt, die das erklärt. Die Spalten kommen aus den Feldern,
die der Nutzer sieht (`protokoll.erfassen._felder`), damit neue Felder von selbst
mitkommen; was dort fehlt (Nummern, Dateipfade, Prüfsummen, Zeitpunkte), steht
ausdrücklich in TABELLEN. Die Spalte „ID“ verknüpft die Tabellen.

Unverschlüsselt, anders als die Datensicherung; zum Wiederherstellen dient sie nicht.
"""

import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from angebote.models import Angebot
from angebote.models import Position as Angebotsposition
from archive.models import Altbeleg
from artikel.models import Artikel
from auftraege.models import Auftragsbestaetigung
from auftraege.models import Position as Auftragsposition
from auswertungen import tabelle
from contacts.models import Kontakt, Kontaktweg
from core.models import Firmendaten
from core.templatetags.kf import zahl
from dokumentation.models import Angaben, Fassung
from eingang.models import Eingangsrechnung
from historie.models import Datei, Vorgang
from invoicing.models import Position as Rechnungsposition
from invoicing.models import Rechnung
from protokoll.erfassen import VERDECKT, _felder, _name, _wert
from protokoll.models import Eintrag
from wiedervorlagen.models import Wiedervorlage
from zahlungen.models import Mahnung, Zahlung


def _zeit(wert):
    return f"{timezone.localtime(wert):%d.%m.%Y %H:%M}" if wert else ""


def _kunde(objekt):
    return objekt.kontakt.kundennummer if objekt.kontakt_id else ""


DATEI = [("PDF", lambda o: o.datei), ("SHA-256", lambda o: o.sha256)]
ID = [("ID", lambda o: o.pk)]

# Datei, Bezeichnung, Abfrage, Spalten vor und nach den sichtbaren Feldern
TABELLEN = [
    ("firma.csv", "Eigene Firmendaten", Firmendaten.objects.all(), [], []),
    (
        "adressen.csv",
        "Adressen",
        Kontakt.objects.select_related("firma"),
        ID + [("Kundennummer", lambda k: k.kundennummer)],
        [
            (
                "Kundennummer der Firma",
                lambda k: k.firma.kundennummer if k.firma else "",
            ),
            ("Angelegt am", lambda k: _zeit(k.erstellt)),
        ],
    ),
    (
        "telefon-email.csv",
        "Weitere Telefonnummern und E-Mail-Adressen der Adressen",
        Kontaktweg.objects.select_related("kontakt"),
        [("Kundennummer", _kunde)],
        [],
    ),
    (
        "artikel.csv",
        "Artikel",
        Artikel.objects.all(),
        ID + [("Artikelnummer", lambda a: a.artikelnummer)],
        [],
    ),
    (
        "angebote.csv",
        "Angebote",
        Angebot.objects.select_related("kontakt"),
        ID + [("Kundennummer", _kunde)],
        [("Fertiggestellt am", lambda a: _zeit(a.fertiggestellt_am))] + DATEI,
    ),
    (
        "angebotspositionen.csv",
        "Positionen der Angebote",
        Angebotsposition.objects.select_related("angebot"),
        [("Angebot-ID", lambda p: p.angebot_id)],
        [("Gesamt", lambda p: zahl(p.gesamt, 2))],
    ),
    (
        "auftragsbestaetigungen.csv",
        "Auftragsbestätigungen",
        Auftragsbestaetigung.objects.select_related("kontakt"),
        ID + [("Kundennummer", _kunde), ("Angebot-ID", lambda a: a.angebot_id)],
        [
            ("Rechnung-ID", lambda a: a.rechnung_id),
            ("Fertiggestellt am", lambda a: _zeit(a.fertiggestellt_am)),
        ]
        + DATEI,
    ),
    (
        "auftragspositionen.csv",
        "Positionen der Auftragsbestätigungen",
        Auftragsposition.objects.select_related("auftrag"),
        [("Auftrag-ID", lambda p: p.auftrag_id)],
        [("Gesamt", lambda p: zahl(p.gesamt, 2))],
    ),
    (
        "rechnungen.csv",
        "Rechnungen, Stornorechnungen und Rechnungskorrekturen",
        Rechnung.objects.select_related("kontakt"),
        ID + [("Kundennummer", _kunde)],
        [
            ("Storniert Rechnung-ID", lambda r: r.storno_zu_id),
            ("Korrigiert Rechnung-ID", lambda r: r.korrektur_zu_id),
            ("Festgeschrieben am", lambda r: _zeit(r.festgeschrieben_am)),
        ]
        + DATEI
        + [("XML", lambda r: r.xml_datei), ("XML SHA-256", lambda r: r.xml_sha256)],
    ),
    (
        "rechnungspositionen.csv",
        "Positionen der Rechnungen",
        Rechnungsposition.objects.select_related("rechnung"),
        [("Rechnung-ID", lambda p: p.rechnung_id)],
        [("Gesamt", lambda p: zahl(p.gesamt, 2))],
    ),
    (
        "zahlungen.csv",
        "Zahlungen, Ausbuchungen und Skonto",
        Zahlung.objects.select_related("rechnung"),
        ID + [("Rechnung-ID", lambda z: z.rechnung_id)],
        [("Erfasst am", lambda z: _zeit(z.erstellt))],
    ),
    (
        "mahnungen.csv",
        "Zahlungserinnerungen und Mahnungen",
        Mahnung.objects.select_related("rechnung"),
        ID + [("Rechnung-ID", lambda m: m.rechnung_id)],
        [],
    ),
    (
        "eingangsrechnungen.csv",
        "Empfangene E-Rechnungen",
        Eingangsrechnung.objects.select_related("kontakt"),
        ID + [("Kundennummer", _kunde)],
        [("Hochgeladen am", lambda e: _zeit(e.hochgeladen))],
    ),
    (
        "altbelege.csv",
        "Belege aus dem früheren Programm",
        Altbeleg.objects.select_related("kontakt"),
        ID + [("Kundennummer", _kunde)],
        [("Übernommen am", lambda a: _zeit(a.importiert))],
    ),
    (
        "verlauf.csv",
        "Notizen, Anrufe, E-Mails und Termine zu den Adressen",
        Vorgang.objects.select_related("kontakt", "benutzer"),
        ID + [("Kundennummer", _kunde)],
        [("Erfasst von", lambda v: v.benutzer or "")],
    ),
    (
        "dateien.csv",
        "Dateien an Adressen",
        Datei.objects.select_related("kontakt", "vorgang", "benutzer"),
        ID + [("Kundennummer", _kunde), ("Vorgang-ID", lambda d: d.vorgang_id)],
        [
            ("Größe in Byte", lambda d: d.groesse),
            ("Abgelegt am", lambda d: _zeit(d.erstellt)),
            ("Abgelegt von", lambda d: d.benutzer or ""),
            ("Datei", lambda d: d.datei),
        ],
    ),
    (
        "wiedervorlagen.csv",
        "Wiedervorlagen",
        Wiedervorlage.objects.select_related("kontakt", "zustaendig", "erledigt_von"),
        ID + [("Kundennummer", _kunde)],
        [
            ("Angebot-ID", lambda w: w.angebot_id),
            ("Rechnung-ID", lambda w: w.rechnung_id),
            ("Erledigt von", lambda w: w.erledigt_von or ""),
        ],
    ),
    (
        "dokumentation-angaben.csv",
        "Angaben zum Betrieb für Verfahrensdokumentation und Datenschutz",
        Angaben.objects.all(),
        [],
        [],
    ),
    (
        "dokumentation-fassungen.csv",
        "Abgelegte Fassungen der Dokumentation",
        Fassung.objects.select_related("erstellt_von"),
        ID,
        [("Geändert", lambda f: "; ".join(f.aenderungen))],
    ),
]


def _sichtbar(modell):
    return [
        f
        for f in _felder(modell)
        if f.name not in VERDECKT and f.get_internal_type() != "BinaryField"
    ]


def tabelle_daten(modell, abfrage, vorne, hinten):
    """(Spaltentitel, Zeilen) einer Tabelle, alle Werte als Text."""
    felder = _sichtbar(modell)
    titel = [t for t, _ in vorne] + [_name(f) for f in felder]
    titel += [t for t, _ in hinten]
    zeilen = [
        [str(fn(o) or "") for _, fn in vorne]
        + [_wert(o, f) for f in felder]
        + [str(fn(o) or "") for _, fn in hinten]
        for o in abfrage.order_by("pk")
    ]
    return titel, zeilen


def protokoll():
    titel = ["Zeit", "Wer", "Aktion", "Art", "Objekt-ID", "Beschreibung", "Änderungen"]
    zeilen = [
        [
            _zeit(e.zeit),
            e.wer,
            e.get_aktion_display(),
            e.art,
            e.objekt_id,
            e.beschreibung,
            "; ".join(f"{feld}: {alt} → {neu}" for feld, alt, neu in e.aenderungen),
        ]
        for e in Eintrag.objects.order_by("zeit", "pk")
    ]
    return titel, zeilen


def _csv(titel, zeilen):
    return tabelle.csv([(t, "text") for t in titel], zeilen)


def dateien():
    """Pfade aller abgelegten Belege und Dateien im Datenordner."""
    pfade = []
    for r in Rechnung.objects.exclude(datei=""):
        pfade += [p for p in (r.datei, r.xml_datei) if p]
    for modell in (Angebot, Auftragsbestaetigung):
        pfade += modell.objects.exclude(datei="").values_list("datei", flat=True)
    for modell in (Mahnung, Altbeleg, Eingangsrechnung, Datei, Fassung):
        pfade += modell.objects.exclude(datei="").values_list("datei", flat=True)
    return pfade


def _liesmich(jetzt, inhalt, anzahl_dateien):
    firma = Firmendaten.laden()
    zeilen = [
        "Kontorfreund – Gesamtexport",
        "",
        f"Erstellt am {jetzt:%d.%m.%Y um %H:%M} Uhr mit Kontorfreund {settings.VERSION}"
        + (f" für {firma.name}" if firma.name else "")
        + ".",
        "",
        "Diese Datei enthält alle Daten und Belege aus Kontorfreund in Formaten, die sich",
        "ohne das Programm öffnen lassen. So bleiben sie lesbar, auch wenn Sie einmal das",
        "Programm wechseln.",
        "",
        "Ordner „tabellen“: je Tabelle eine CSV-Datei (UTF-8, Semikolon, Dezimalkomma),",
        "zu öffnen mit Excel oder LibreOffice. Die erste Zeile nennt die Spalten.",
        "",
    ]
    breite = max(len(datei) for datei, _, _ in inhalt)
    zeilen += [
        f"  {datei.ljust(breite)}  {beschreibung} ({anzahl} Zeile{'n' if anzahl != 1 else ''})"
        for datei, beschreibung, anzahl in inhalt
    ]
    zeilen += [
        "",
        "Die Spalte „ID“ verknüpft die Tabellen: „Rechnung-ID“ in rechnungspositionen.csv",
        "oder zahlungen.csv ist die ID in rechnungen.csv, „Angebot-ID“ die in angebote.csv",
        "und so weiter. Adressen finden Sie über die Kundennummer.",
        "",
        f"Ordner „archiv“: {anzahl_dateien} Belege und Dateien im Original, unverändert, so",
        "wie Kontorfreund sie abgelegt hat: Rechnungen, Angebote, Auftragsbestätigungen und",
        "Mahnungen als PDF, E-Rechnungen als XML, Belege aus dem früheren Programm,",
        "empfangene E-Rechnungen und die Dateien an Adressen. Die Spalten „PDF“, „XML“ und",
        "„Datei“ nennen den Pfad, die Spalten „SHA-256“ die Prüfsumme, mit der sich zeigen",
        "lässt, dass ein Beleg seit dem Ablegen unverändert ist.",
        "",
        "Für das Finanzamt erstellt Kontorfreund unter Auswertungen > Betriebsprüfung ein",
        "eigenes Datenpaket nach dem Beschreibungsstandard der Finanzverwaltung.",
        "",
        "Dieser Export ist nicht verschlüsselt und enthält Daten Ihrer Kunden. Bewahren Sie",
        "ihn sicher auf und löschen Sie ihn, wenn Sie ihn nicht mehr brauchen. Zum",
        "Wiederherstellen in Kontorfreund dient die Datensicherung, nicht dieser Export.",
        "",
    ]
    return "\r\n".join(zeilen).encode("utf-8-sig")


def paket():
    """Der Gesamtexport als temporäre Datei, zurückgespult; fehlende Dateien fehlen darin."""
    jetzt = timezone.localtime()
    datei = tempfile.TemporaryFile()
    inhalt = []
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as z:
        for name, beschreibung, abfrage, vorne, hinten in TABELLEN:
            titel, zeilen = tabelle_daten(abfrage.model, abfrage, vorne, hinten)
            z.writestr(f"tabellen/{name}", _csv(titel, zeilen))
            inhalt.append((name, beschreibung, len(zeilen)))
        titel, zeilen = protokoll()
        z.writestr("tabellen/protokoll.csv", _csv(titel, zeilen))
        inhalt.append(("protokoll.csv", "Änderungsprotokoll", len(zeilen)))
        abgelegt = 0
        for pfad in dateien():
            quelle = Path(settings.DATA_DIR) / pfad
            if quelle.is_file():
                # PDFs und Bilder sind schon gepackt; noch einmal zu packen kostet nur Zeit.
                z.write(quelle, pfad, compress_type=zipfile.ZIP_STORED)
                abgelegt += 1
        z.writestr("LIESMICH.txt", _liesmich(jetzt, inhalt, abgelegt))
    datei.seek(0)
    return datei
