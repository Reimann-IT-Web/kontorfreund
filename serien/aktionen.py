"""Was die Seite einer Serie für alle Rechnungen auf einmal tut (Spezifikation B-11).

Jede Rechnung für sich: Scheitert eine, laufen die anderen weiter, und das Ergebnis
nennt sie mit Grund.
"""

import logging
import smtplib
from datetime import date
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from core import umsatz
from core.templatetags.kf import euro
from invoicing import beleg, versand
from invoicing.models import Rechnung
from zahlungen.models import Zahlung

from . import texte

logger = logging.getLogger(__name__)


def _rechnungen(serie):
    return [
        t
        for t in serie.teilnehmer.select_related("rechnung__kontakt").order_by(
            "zeile", "pk"
        )
    ]


def festschreiben(serie, firma):
    """Alle Entwürfe in der Reihenfolge der Liste; ([Nummern], [(Teilnehmer, Grund)])."""
    nummern, fehler = [], []
    heute = date.today()
    for t in _rechnungen(serie):
        r = t.rechnung
        if not r.ist_entwurf:
            continue
        # Wie im Editor (B-8): Ein Entwurf von gestern bekommt das heutige Datum.
        if r.datum < heute and timezone.localtime(r.geaendert).date() < heute:
            r.datum = heute
            r.save(update_fields=["datum", "geaendert"])
        if (
            r.steuerfall == Rechnung.Steuerfall.KLEINUNTERNEHMER
            and umsatz.ueber_laufender_grenze(r.datum.year, r.summen()[0])
        ):
            fehler.append(
                (
                    t,
                    f"Ihr Umsatz läge über {euro(umsatz.LAUFEND)}; bitte im Entwurf "
                    "Umsatzsteuer ausweisen.",
                )
            )
            continue
        if fehlt := r.fehlende_angaben(firma):
            fehler.append((t, f"Noch nicht vollständig: {', '.join(fehlt)}."))
            continue
        try:
            beleg.festschreiben(r, firma)
        except Exception:
            logger.exception("Festschreiben fehlgeschlagen")
            fehler.append((t, "Das PDF konnte nicht erzeugt werden."))
            continue
        nummern.append(r.nummer)
    return nummern, fehler


def mail(t, vorlage, firma):
    """(Betreff, Text) der E-Mail an einen Teilnehmer."""
    r, serie = t.rechnung, t.serie
    werte = {
        "termin": serie.termin,
        "thema": serie.thema,
        "link": serie.link,
        "betrag": euro(r.brutto),
        "datum": f"{r.datum:%d.%m.%Y}",
        "faellig": f"{r.faellig:%d.%m.%Y}",
        "kundennummer": r.kontakt.kundennummer if r.kontakt else "",
        "nummer": r.nummer,
    }
    gruss = "\n".join(z for z in (firma.inhaber, firma.name) if z)
    text = texte.fuellen(vorlage.mail_text, werte)
    return (
        # Eine Kopfzeile verträgt keinen Zeilenumbruch, etwa aus einer Excel-Zelle.
        " ".join(texte.fuellen(vorlage.mail_betreff, werte).split())[:200],
        f"{beleg.briefanrede(t)}\n\n{text}\n\nMit freundlichen Grüßen\n{gruss}",
    )


def beilagen(t, vorlage):
    if t.beilage and vorlage.beilage:
        return [
            (
                vorlage.beilage_name or "Beilage.pdf",
                bytes(vorlage.beilage),
                "application/pdf",
            )
        ]
    return []


def zu_senden(serie):
    """Festgeschrieben, mit E-Mail-Adresse und noch nicht versendet."""
    return [
        t
        for t in _rechnungen(serie)
        if not t.rechnung.ist_entwurf
        and t.rechnung.email_an
        and not t.rechnung.versendet_am
    ]


def senden(serie, firma, vorlage, kopie):
    """Jede Rechnung als eigene E-Mail; ([gesendet], [(Teilnehmer, Grund)])."""
    gesendet, fehler = [], []
    for t in zu_senden(serie):
        betreff, text = mail(t, vorlage, firma)
        try:
            versand.senden(
                t.rechnung,
                firma,
                t.rechnung.email_an,
                betreff,
                text,
                kopie,
                beilagen(t, vorlage),
            )
        except (smtplib.SMTPException, OSError, ValueError) as grund:
            logger.warning("Versand fehlgeschlagen: %s", grund)
            fehler.append((t, versand.fehlertext(grund)))
            continue
        gesendet.append(t)
    return gesendet, fehler


def zum_drucken(serie):
    """Festgeschriebene Rechnungen ohne E-Mail-Adresse."""
    return [
        t
        for t in _rechnungen(serie)
        if not t.rechnung.ist_entwurf and not t.rechnung.email_an
    ]


def druck_pdf(serie, vorlage):
    """Ein PDF mit den Rechnungen ohne E-Mail-Adresse, jede mit ihrer Beilage."""
    schreiber = PdfWriter()
    for t in zum_drucken(serie):
        pfad = Path(settings.DATA_DIR) / t.rechnung.datei
        schreiber.append(PdfReader(BytesIO(pfad.read_bytes())))
        for _, inhalt, _ in beilagen(t, vorlage):
            schreiber.append(PdfReader(BytesIO(inhalt)))
    ausgabe = BytesIO()
    schreiber.write(ausgabe)
    return ausgabe.getvalue()


SPALTEN = [
    ("Zeile der Liste", "text"),
    ("Kd-Nr.", "text"),
    ("Name", "text"),
    ("Rechnungsnummer", "text"),
    ("Betrag", "betrag"),
    ("Zahlweg", "text"),
    ("Versendet am", "datum"),
]


def uebersicht(serie):
    """Zeilen für die Übersicht als Tabelle (B-11, Schritt 7)."""
    zeilen = []
    for t in _rechnungen(serie):
        r = t.rechnung
        zeilen.append(
            [
                str(t.zeile),
                str(r.kontakt.nummer) if r.kontakt else "",
                t.name,
                r.nummer or "Entwurf",
                r.brutto if r.nummer else r.summen()[2],
                r.get_zahlweg_display(),
                timezone.localtime(r.versendet_am).date() if r.versendet_am else None,
            ]
        )
    return zeilen


def einzuziehen(serie, heute=None):
    """Festgeschriebene Lastschriften ohne Zahlung, deren Einzugstag erreicht ist."""
    heute = heute or date.today()
    return [
        t
        for t in _rechnungen(serie)
        if t.rechnung.ist_posten
        and t.rechnung.ist_lastschrift
        and not t.rechnung.zahlungen.exists()
        and t.rechnung.offen > 0
        and t.rechnung.faellig <= heute
    ]


def eingezogen(serie):
    """Bucht je Lastschrift den offenen Betrag zum Einzugstag (M-2)."""
    gebucht = []
    for t in einzuziehen(serie):
        r = t.rechnung
        Zahlung.objects.create(
            rechnung=r,
            datum=r.faellig,
            betrag=r.offen,
            art=Zahlung.Art.LASTSCHRIFT,
            notiz="Lastschrift der Serie",
        )
        gebucht.append(t)
    return gebucht
