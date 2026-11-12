"""Datenschutz für eine Adresse (Spezifikation D-1).

Auskunft (Art. 15 und 20 DSGVO): ein ZIP mit allen gespeicherten Daten der Adresse, als
Brief zum Lesen (PDF) und als JSON zum Weiterverwenden, dazu Kopien ihrer Belege und
Dateien.

Löschen (Art. 17 DSGVO) geht, wenn kein Beleg mehr aufbewahrt werden muss. Dann
verschwinden die Adresse, ihre Vorgänge, Dateien, Wiedervorlagen und Entwürfe und auch die
Belege mit abgelaufener Frist; im Änderungsprotokoll bleibt nur, wann wer was getan hat.
Läuft noch eine Frist, wird die Adresse bis dahin gesperrt (Art. 17 Abs. 3 lit. b,
Art. 18 DSGVO): Sie liegt im Archiv, erscheint in keiner Liste und Suche, niemand kann
sie ändern, und ansehen kann sie nur der Inhaber. Entwürfe werden dabei gelöscht und
offene Wiedervorlagen erledigt.
"""

import json
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import typst
from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from angebote.models import Angebot
from archive import fristen
from archive.fristen import ENTWURF, belege, frist, loeschbar
from auftraege.models import Auftragsbestaetigung
from auswertungen.models import Datev
from core.models import Firmendaten
from core.templatetags.kf import euro
from invoicing.beleg import (
    SCHRIFTEN,
    WURZEL,
    absaetze,
    absender_daten,
    briefanrede,
    briefkopf,
    druckbilder,
    grussformel,
    kopf_druck,
)
from invoicing.models import Rechnung
from protokoll.erfassen import eintragen, schwaerzen
from protokoll.models import Eintrag
from zahlungen.models import Mahnung, Zahlung

from .forms import KontaktForm
from .models import Kontakt

VORLAGE = Path(__file__).parent / "typst" / "auskunft.typ"
ERLEDIGT = "Adresse gesperrt (Art. 18 DSGVO)"
# Belegarten mit Positionen
MIT_POSITIONEN = (Rechnung, Angebot, Auftragsbestaetigung)


def _positionen(beleg):
    return [
        {
            "Bezeichnung": p.bezeichnung,
            "Beschreibung": p.beschreibung,
            "Menge": p.menge,
            "Einheit": p.einheit,
            "Einzelpreis": p.preis,
        }
        for p in beleg.positionen.all()
    ]


def entwuerfe(kontakt):
    """Entwürfe von Auftragsbestätigungen, Angeboten und Rechnungen, in dieser
    Reihenfolge löschbar."""
    return [
        *kontakt.auftraege.filter(status=ENTWURF),
        *kontakt.angebote.filter(status=ENTWURF),
        *kontakt.rechnungen.filter(status=ENTWURF),
    ]


def zugriff(request, kontakt, aendern=False):
    """Eine gesperrte Adresse kann niemand ändern, und ansehen kann sie nur der Inhaber."""
    if kontakt.gesperrt_am and (aendern or not request.user.ist_inhaber):
        raise Http404


# ---------- Auskunft ----------


def _json(wert):
    if isinstance(wert, datetime):
        return timezone.localtime(wert).isoformat(timespec="seconds")
    if isinstance(wert, date):
        return wert.isoformat()
    if isinstance(wert, Decimal):
        return str(wert)
    raise TypeError(type(wert))


def stammdaten(kontakt):
    daten = {"Kundennummer": kontakt.kundennummer}
    for name in KontaktForm.Meta.fields:
        feld = Kontakt._meta.get_field(name)
        wert = getattr(kontakt, name)
        if feld.choices and wert:
            wert = getattr(kontakt, f"get_{name}_display")()
        elif feld.many_to_many:
            wert = kontakt.kategorien_text
        elif feld.is_relation:
            wert = f"{wert.kundennummer} {wert}" if wert else ""
        daten[str(feld.verbose_name)] = wert
    daten["Weitere Telefonnummern und E-Mail-Adressen"] = kontakt.kontaktwege_text
    daten["Weitere Anschriften"] = kontakt.anschriften_text
    daten["Angelegt am"] = kontakt.erstellt
    daten["Zuletzt geändert am"] = kontakt.geaendert
    daten["Archiviert"] = kontakt.archiviert
    daten["Gesperrt am"] = kontakt.gesperrt_am
    return daten


def auskunft_daten(kontakt, alle, jetzt):
    """Alle gespeicherten Daten zur Adresse, wie sie in auskunft.json stehen."""
    firma = Firmendaten.laden()
    return {
        "Auskunft nach": "Art. 15 DSGVO",
        "Erstellt am": jetzt,
        "Erstellt mit": f"Kontorfreund {settings.VERSION}",
        "Verantwortlicher": {
            "Name": firma.name,
            "Inhaber": firma.inhaber,
            "Anschrift": ", ".join(
                t for t in (firma.strasse, f"{firma.plz} {firma.ort}".strip()) if t
            ),
            "E-Mail": firma.email,
            "Telefon": firma.telefon,
        },
        "Adresse": stammdaten(kontakt),
        "Belege": [
            {
                "Art": b.art,
                "Nummer": b.nummer,
                "Datum": b.datum,
                "Betrag": b.betrag,
                "Aufbewahren bis": b.aufbewahren_bis,
                "Dateien": b.dateien,
                **(
                    {"Positionen": _positionen(b.objekt)}
                    if isinstance(b.objekt, MIT_POSITIONEN)
                    else {}
                ),
            }
            for b in alle
        ],
        "Entwürfe": [
            {
                "Art": str(e),
                "Datum": e.datum,
                "Betreff": e.betreff,
                # Ohne Betrag: Den rechnet Kontorfreund erst beim Fertigstellen aus.
                "Positionen": _positionen(e),
            }
            for e in entwuerfe(kontakt)
        ],
        "Zahlungen": [
            {
                "Rechnung": z.rechnung.nummer,
                "Datum": z.datum,
                "Art": z.get_art_display(),
                "Betrag": z.betrag,
                "Nebenkosten": z.nebenkosten,
                "Notiz": z.notiz,
            }
            for z in Zahlung.objects.filter(rechnung__kontakt=kontakt)
            .select_related("rechnung")
            .order_by("datum", "pk")
        ],
        "Verlauf": [
            {
                "Zeitpunkt": v.zeitpunkt,
                "Art": v.get_art_display(),
                "Betreff": v.betreff,
                "Text": v.text,
            }
            for v in kontakt.vorgaenge.order_by("zeitpunkt", "pk")
        ],
        "Dateien": [
            {
                "Name": d.name,
                "Größe in Byte": d.groesse,
                "Abgelegt am": d.erstellt,
                "Gelöscht am": d.geloescht_am,
                "Datei": d.datei,
            }
            for d in kontakt.dateien.order_by("erstellt", "pk")
        ],
        "Wiedervorlagen": [
            {
                "Was ist zu tun?": w.titel,
                "Fällig am": w.faellig,
                "Uhrzeit": w.uhrzeit.strftime("%H:%M") if w.uhrzeit else None,
                "Notiz": w.notiz,
                "Erledigt am": w.erledigt_am,
                "Ergebnis": w.ergebnis,
            }
            for w in kontakt.wiedervorlagen.order_by("faellig", "pk")
        ],
        "Änderungsprotokoll": [
            {
                "Zeitpunkt": e.zeit,
                "Aktion": e.get_aktion_display(),
                "Änderungen": [
                    {"Feld": feld, "Vorher": alt, "Nachher": neu}
                    for feld, alt, neu in e.aenderungen
                ],
            }
            for e in _protokoll(kontakt).order_by("zeit", "pk")
        ],
    }


def _protokoll(kontakt):
    return Eintrag.objects.filter(
        art=str(Kontakt._meta.verbose_name), objekt_id=str(kontakt.pk)
    )


def letzte_auskunft(kontakt):
    return _protokoll(kontakt).filter(aktion=Eintrag.Aktion.AUSKUNFT).first()


def zeilen(wert):
    """Wert als Zeilen für den Brief."""
    if isinstance(wert, bool):
        wert = "ja" if wert else "nein"
    elif isinstance(wert, datetime):
        wert = f"{timezone.localtime(wert):%d.%m.%Y %H:%M}"
    elif isinstance(wert, date):
        wert = f"{wert:%d.%m.%Y}"
    return str(wert or "").splitlines() or [""]


def _betrag(wert):
    return [euro(wert)] if wert is not None else [""]


def _tabelle(titel, spalten, zeilen, breit=(), rechts=()):
    return {
        "titel": titel,
        "spalten": spalten,
        "zeilen": zeilen,
        "breit": list(breit),
        "rechts": list(rechts),
    }


def _hinweise(kontakt, daten, ende):
    """Die Angaben nach Art. 15 Abs. 1 DSGVO."""
    arten = ["Name und Anschrift"]
    if kontakt.email or kontakt.telefon or kontakt.website:
        arten.append("Kontaktdaten")
    if kontakt.ust_id:
        arten.append("Umsatzsteuer-Identifikationsnummer")
    if daten["Belege"] or daten["Entwürfe"]:
        arten.append("Angebote, Aufträge, Rechnungen und Zahlungen")
    if daten["Verlauf"]:
        arten.append("Notizen zu Gesprächen, E-Mails und Terminen")
    if daten["Dateien"]:
        arten.append("abgelegte Dateien")
    if daten["Wiedervorlagen"]:
        arten.append("Wiedervorlagen")
    empfaenger = (
        "Behörden wie das Finanzamt, wenn ein Gesetz es verlangt, etwa bei einer "
        "Betriebsprüfung"
    )
    if Datev.laden().bereit:
        empfaenger = f"Unser Steuerberater für die Buchhaltung; {empfaenger}"
    dauer = (
        "Rechnungen und andere Buchungsbelege bewahren wir 8 Jahre auf, Angebote, "
        "Mahnungen und andere Geschäftsbriefe 6 Jahre, jeweils ab Ende des "
        "Kalenderjahres (§ 147 AO, § 14b UStG)."
    )
    if ende and ende >= date.today():
        dauer += f" Für Ihre Belege endet die Frist am {ende:%d.%m.%Y}."
    elif ende:
        dauer += f" Für Ihre Belege ist die Frist am {ende:%d.%m.%Y} abgelaufen."
    dauer += (
        " Ihre übrigen Daten speichern wir, solange wir sie für unsere "
        "Geschäftsbeziehung brauchen, oder bis Sie die Löschung verlangen."
    )
    return [
        "Zwecke: Wir verarbeiten Ihre Daten, um Anfragen, Angebote, Aufträge und "
        "Rechnungen abzuwickeln (Art. 6 Abs. 1 lit. b DSGVO) und um gesetzliche "
        "Aufbewahrungspflichten zu erfüllen (Art. 6 Abs. 1 lit. c DSGVO mit § 147 AO "
        "und § 14b UStG).",
        f"Gespeicherte Daten: {', '.join(arten)}.",
        f"Empfänger: {empfaenger}.",
        f"Speicherdauer: {dauer}",
        "Ihre Rechte: Sie können verlangen, dass wir Ihre Daten berichtigen (Art. 16 "
        "DSGVO), löschen (Art. 17 DSGVO) oder nur noch eingeschränkt verarbeiten "
        "(Art. 18 DSGVO), und Sie können der Verarbeitung widersprechen (Art. 21 "
        "DSGVO). Ihre Daten in maschinenlesbarer Form liegen dieser Auskunft als Datei "
        "„auskunft.json“ bei (Art. 20 DSGVO).",
        "Beschwerde: Sie können sich bei einer Datenschutz-Aufsichtsbehörde beschweren "
        "(Art. 77 DSGVO).",
        "Eine automatisierte Entscheidungsfindung einschließlich Profiling (Art. 22 "
        "DSGVO) findet nicht statt.",
    ]


def druckdaten(kontakt, daten, ende, jetzt, logo=b"", kopf=None):
    """Der Brief zur Auskunft als fertig formatierte Texte für auskunft.typ."""
    firma = Firmendaten.laden()
    abschnitte = [
        {
            "titel": "Gespeicherte Angaben",
            "felder": [
                [name, zeilen(wert)]
                for name, wert in daten["Adresse"].items()
                if wert not in ("", None, False)
            ],
        }
    ]
    if daten["Belege"]:
        abschnitte.append(
            _tabelle(
                "Belege",
                ["Art", "Nummer", "Datum", "Betrag", "Aufbewahren bis"],
                [
                    [zeilen(b["Art"]), zeilen(b["Nummer"]), zeilen(b["Datum"])]
                    + [_betrag(b["Betrag"]), zeilen(b["Aufbewahren bis"])]
                    for b in daten["Belege"]
                ],
                breit=[1],
                rechts=[3],
            )
        )
    if daten["Entwürfe"]:
        abschnitte.append(
            _tabelle(
                "Entwürfe",
                ["Art", "Datum", "Betreff"],
                [
                    [zeilen(e["Art"]), zeilen(e["Datum"]), zeilen(e["Betreff"])]
                    for e in daten["Entwürfe"]
                ],
                breit=[2],
            )
        )
    if daten["Zahlungen"]:
        abschnitte.append(
            _tabelle(
                "Zahlungen",
                ["Datum", "Rechnung", "Art", "Betrag"],
                [
                    [zeilen(z["Datum"]), zeilen(z["Rechnung"]), zeilen(z["Art"])]
                    + [_betrag(z["Betrag"])]
                    for z in daten["Zahlungen"]
                ],
                breit=[2],
                rechts=[3],
            )
        )
    if daten["Verlauf"]:
        abschnitte.append(
            _tabelle(
                "Gespräche, E-Mails, Termine und Notizen",
                ["Wann", "Art", "Inhalt"],
                [
                    [zeilen(v["Zeitpunkt"]), zeilen(v["Art"])]
                    + [
                        [t for t in (v["Betreff"], *v["Text"].splitlines()) if t]
                        or [""]
                    ]
                    for v in daten["Verlauf"]
                ],
                breit=[2],
            )
        )
    if daten["Dateien"]:
        abschnitte.append(
            _tabelle(
                "Dateien",
                ["Name", "Abgelegt am", "Größe"],
                [
                    [zeilen(d["Name"]), zeilen(d["Abgelegt am"])]
                    + [[str(filesizeformat(d["Größe in Byte"]))]]
                    for d in daten["Dateien"]
                ],
                breit=[0],
                rechts=[2],
            )
        )
    if daten["Wiedervorlagen"]:
        abschnitte.append(
            _tabelle(
                "Wiedervorlagen",
                ["Fällig am", "Was ist zu tun?", "Erledigt am"],
                [
                    [zeilen(w["Fällig am"]), zeilen(w["Was ist zu tun?"])]
                    + [zeilen(w["Erledigt am"])]
                    for w in daten["Wiedervorlagen"]
                ],
                breit=[1],
            )
        )
    aenderungen = [
        [zeilen(e["Zeitpunkt"]), zeilen(a["Feld"]), zeilen(a["Vorher"])]
        + [zeilen(a["Nachher"])]
        for e in daten["Änderungsprotokoll"]
        if e["Aktion"] == Eintrag.Aktion.GEAENDERT.label
        for a in e["Änderungen"]
    ]
    if aenderungen:
        abschnitte.append(
            _tabelle(
                "Frühere Angaben",
                ["Geändert am", "Feld", "Vorher", "Nachher"],
                aenderungen,
                breit=[2, 3],
            )
        )
    abschnitte.append(
        {
            "titel": "Informationen nach Art. 15 Abs. 1 DSGVO",
            "absaetze": [[t] for t in _hinweise(kontakt, daten, ende)],
        }
    )
    return {
        "titel": "Auskunft nach Art. 15 DSGVO",
        **kopf_druck(logo, kopf),
        **briefkopf(absender_daten(firma)),
        "empfaenger": kontakt.anschrift_zeilen(),
        "info": [
            ["Datum", f"{jetzt:%d.%m.%Y}"],
            ["Kundennummer", kontakt.kundennummer],
        ],
        "kopftext": absaetze(
            f"{briefanrede(kontakt)}\n\n"
            "Sie haben Auskunft über die Daten verlangt, die wir zu Ihnen gespeichert "
            f"haben. Hier ist die vollständige Aufstellung, Stand {jetzt:%d.%m.%Y}. "
            "Kopien Ihrer Belege und Dateien und alle Angaben in maschinenlesbarer Form "
            "liegen bei."
        ),
        "abschnitte": abschnitte,
        "fusstext": absaetze(grussformel(firma)),
    }


def setzen(druck):
    return typst.compile(
        str(VORLAGE),
        root=str(WURZEL),
        font_paths=[str(SCHRIFTEN)],
        ignore_system_fonts=True,
        sys_inputs={"daten": json.dumps(druck)},
    )


def auskunft(kontakt):
    """Die Auskunft als temporäre ZIP-Datei, zurückgespult; im Protokoll vermerkt."""
    jetzt = timezone.localtime()
    alle = belege(kontakt)
    daten = auskunft_daten(kontakt, alle, jetzt)
    bilder = druckbilder(Firmendaten.laden())
    datei = tempfile.TemporaryFile()
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            f"Auskunft {kontakt.kundennummer}.pdf",
            setzen(
                druckdaten(
                    kontakt,
                    daten,
                    frist(alle),
                    jetzt,
                    bilder["logo"],
                    bilder["kopf"],
                )
            ),
        )
        z.writestr(
            "auskunft.json",
            json.dumps(daten, ensure_ascii=False, indent=2, default=_json),
        )
        for pfad in [p for b in alle for p in b.dateien] + [
            d["Datei"] for d in daten["Dateien"]
        ]:
            quelle = Path(settings.DATA_DIR) / pfad
            if quelle.is_file():
                z.write(quelle, pfad)
    eintragen(Eintrag.Aktion.AUSKUNFT, kontakt)
    datei.seek(0)
    return datei


# ---------- Sperren und Löschen ----------


@transaction.atomic
def sperren(kontakt, benutzer):
    for entwurf in entwuerfe(kontakt):
        entwurf.delete()
    for w in kontakt.wiedervorlagen.filter(erledigt_am__isnull=True):
        w.erledigen(benutzer, ERLEDIGT)
    kontakt.archiviert = True
    kontakt.gesperrt_am = timezone.now()
    kontakt.save(update_fields=["archiviert", "gesperrt_am", "geaendert"])


def entsperren(kontakt):
    """Die Adresse bleibt im Archiv; zurückholen lässt sie sich von dort."""
    kontakt.gesperrt_am = None
    kontakt.save(update_fields=["gesperrt_am", "geaendert"])


def _anzahl(n, einzahl, mehrzahl):
    return f"{n} {einzahl if n == 1 else mehrzahl}"


def umfang(kontakt, alle):
    """Was beim Löschen mit verschwindet, als Liste für Seite und Protokoll."""
    teile = [
        (len(alle), "abgelaufener Beleg", "abgelaufene Belege"),
        (len(entwuerfe(kontakt)), "Entwurf", "Entwürfe"),
        (kontakt.vorgaenge.count(), "Eintrag im Verlauf", "Einträge im Verlauf"),
        (kontakt.dateien.count(), "Datei", "Dateien"),
        (kontakt.wiedervorlagen.count(), "Wiedervorlage", "Wiedervorlagen"),
    ]
    return [_anzahl(n, e, m) for n, e, m in teile if n]


@transaction.atomic
def loeschen(kontakt):
    """Endgültig löschen; nur, wenn keine Aufbewahrungsfrist mehr läuft."""
    alle = belege(kontakt)
    if not loeschbar(alle):
        raise ValueError("Für diese Adresse müssen noch Belege aufbewahrt werden.")
    weg = umfang(kontakt, alle)
    pfade = [d.datei for d in kontakt.dateien.all()]
    mit = [
        *kontakt.vorgaenge.all(),
        *kontakt.dateien.all(),
        *kontakt.wiedervorlagen.all(),
    ]
    geloescht = fristen.entfernen(
        [
            *kontakt.auftraege.all(),
            *kontakt.angebote.all(),
            *Mahnung.objects.filter(rechnung__kontakt=kontakt),
            *kontakt.rechnungen.all(),
            *kontakt.altbelege.all(),
            *kontakt.eingangsrechnungen.all(),
        ]
    )
    # Über eine Abfrage: So behält `kontakt` seine Nummer fürs Schwärzen.
    Kontakt.objects.filter(pk=kontakt.pk).delete()
    schwaerzen([kontakt, *geloescht, *mit])
    eintragen(
        Eintrag.Aktion.LOESCHUNG,
        kontakt,
        beschreibung=kontakt.kundennummer + (f" mit {', '.join(weg)}" if weg else ""),
    )
    transaction.on_commit(lambda: fristen.wegraeumen(pfade))
