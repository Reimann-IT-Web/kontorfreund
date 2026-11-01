"""Auftragsbestätigung als PDF/A-3 mit derselben Vorlage wie die Rechnung, ohne E-Rechnungsdaten."""

import hashlib
from datetime import date
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from angebote.models import Angebot
from core.templatetags.kf import euro
from invoicing.beleg import (
    absaetze,
    absender_daten,
    briefanrede,
    briefkopf,
    datum_de,
    druck_positionen,
    druck_summen,
    empfaenger_daten,
    grussformel,
    leistungszeit,
    positionen_daten,
    setzen,
)
from invoicing.models import Position as Rechnungsposition
from invoicing.models import Rechnung

from .models import Auftragsbestaetigung, Position


def kopftext(kontakt, angebot=None):
    bezug = (
        f" zu meinem Angebot {angebot.nummer} vom {angebot.datum:%d.%m.%Y}"
        if angebot
        else ""
    )
    return (
        f"{briefanrede(kontakt)}\n\n"
        f"vielen Dank für Ihren Auftrag{bezug}. Hiermit bestätige ich Ihnen "
        "folgende Leistungen:"
    )


def fusstext(firma):
    return "Ich freue mich auf die Zusammenarbeit.\n\n" + grussformel(firma)


def beleg_daten(auftrag, firma, nummer):
    """Alle Angaben der Auftragsbestätigung. Beim Fertigstellen eingefroren."""
    netto, ust, brutto = auftrag.summen()
    return {
        "nummer": nummer,
        "datum": auftrag.datum.isoformat(),
        "leistung_von": auftrag.leistung_von.isoformat()
        if auftrag.leistung_von
        else "",
        "leistung_bis": auftrag.leistung_bis.isoformat()
        if auftrag.leistung_bis
        else "",
        "angebot": auftrag.angebot.nummer if auftrag.angebot else "",
        "steuerfall": auftrag.steuerfall,
        "steuerhinweis": auftrag.steuerhinweis,
        "betreff": auftrag.betreff,
        "kopftext": auftrag.kopftext,
        "fusstext": auftrag.fusstext,
        "absender": absender_daten(firma),
        "empfaenger": empfaenger_daten(auftrag.kontakt),
        "positionen": positionen_daten(auftrag.positionen.all()),
        "netto": str(netto),
        "ust": str(ust),
        "brutto": str(brutto),
    }


def druckdaten(b, entwurf=False, logo=b""):
    """Angaben der Auftragsbestätigung als fertig formatierte Texte für die Typst-Vorlage."""
    e = b["empfaenger"]
    info = [
        ("Auftragsnummer", b["nummer"] or "wird vergeben"),
        ("Datum", datum_de(b["datum"])),
    ]
    if e["kundennummer"]:
        info.append(("Kundennummer", e["kundennummer"]))
    if b["angebot"]:
        info.append(("Zum Angebot", b["angebot"]))
    if b["leistung_von"]:
        info.append(leistungszeit(b["leistung_von"], b["leistung_bis"]))
    return {
        "entwurf": entwurf,
        "titel": f"Auftragsbestätigung {b['nummer']}"
        if b["nummer"]
        else "Auftragsbestätigung (Entwurf)",
        "logo": list(logo) or None,
        **briefkopf(b["absender"]),
        "empfaenger": e["zeilen"],
        "info": info,
        "betreff": b["betreff"],
        "kopftext": absaetze(b["kopftext"]),
        "positionen": druck_positionen(b["positionen"]),
        "summen": druck_summen(b),
        "summe_titel": "Auftragssumme",
        "brutto": euro(b["brutto"]),
        "steuerhinweis": b["steuerhinweis"],
        "zahlung": [],
        "girocode": None,
        "fusstext": absaetze(b["fusstext"]),
    }


def pdf(b, entwurf=False, logo=b""):
    return setzen(druckdaten(b, entwurf, logo))


def fertigstellen(auftrag, firma):
    """Nummer vergeben, PDF erzeugen und unveränderbar ablegen."""
    with transaction.atomic():
        nummer = Auftragsbestaetigung.naechste_nummer(auftrag.datum)
        b = beleg_daten(auftrag, firma, nummer)
        inhalt = pdf(b, logo=bytes(firma.logo))
        relativ = (
            Path("archiv")
            / "auftraege"
            / str(auftrag.datum.year)
            / f"Auftragsbestaetigung-{nummer}.pdf"
        )
        auftrag.nummer = nummer
        auftrag.beleg = b
        auftrag.netto, auftrag.ust, auftrag.brutto = auftrag.summen()
        auftrag.datei = relativ.as_posix()
        auftrag.sha256 = hashlib.sha256(inhalt).hexdigest()
        auftrag.status = Auftragsbestaetigung.Status.FERTIG
        auftrag.fertiggestellt_am = timezone.now()
        auftrag.save()
        ziel = Path(settings.DATA_DIR) / relativ
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with ziel.open("xb") as datei:  # niemals überschreiben
            datei.write(inhalt)
    return auftrag


def aus_angebot(angebot, firma):
    """Entwurf mit Empfänger, Steuerfall, Betreff und allen Positionen des Angebots.

    Das Angebot gilt damit als angenommen.
    """
    with transaction.atomic():
        auftrag = Auftragsbestaetigung.objects.create(
            kontakt=angebot.kontakt,
            steuerfall=angebot.steuerfall,
            betreff=angebot.betreff,
            kopftext=kopftext(angebot.kontakt, angebot),
            fusstext=fusstext(firma),
            angebot=angebot,
        )
        Position.objects.bulk_create(
            Position(
                auftrag=auftrag,
                nr=p.nr,
                bezeichnung=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge=p.menge,
                einheit=p.einheit,
                preis=p.preis,
            )
            for p in angebot.positionen.all()
        )
        if not angebot.antwort:
            angebot.antwort = Angebot.Antwort.ANGENOMMEN
            angebot.antwort_am = date.today()
            angebot.save(update_fields=["antwort", "antwort_am", "geaendert"])
    return auftrag


def rechnung_erstellen(auftrag, firma):
    """Rechnungsentwurf mit Empfänger, Steuerfall, Betreff, Ausführung als
    Leistungszeitraum und allen Positionen."""
    with transaction.atomic():
        rechnung = Rechnung.objects.create(
            kontakt=auftrag.kontakt,
            steuerfall=auftrag.steuerfall,
            leistung_von=auftrag.leistung_von,
            leistung_bis=auftrag.leistung_bis,
            betreff=auftrag.betreff,
            kopftext=f"{briefanrede(auftrag.kontakt)}\n\n"
            "vielen Dank für Ihren Auftrag. Gemäß meiner Auftragsbestätigung "
            f"{auftrag.nummer} vom {auftrag.datum:%d.%m.%Y} berechne ich Ihnen "
            "folgende Leistungen:",
            fusstext=grussformel(firma),
        )
        Rechnungsposition.objects.bulk_create(
            Rechnungsposition(
                rechnung=rechnung,
                nr=p.nr,
                bezeichnung=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge=p.menge,
                einheit=p.einheit,
                preis=p.preis,
            )
            for p in auftrag.positionen.all()
        )
        auftrag.rechnung = rechnung
        auftrag.save(update_fields=["rechnung", "geaendert"])
    return rechnung


def mail_vorschlag(auftrag, firma):
    """Empfänger, Betreff und Text, die der Nutzer vor dem Senden noch ändern kann."""
    gruss = "\n".join(z for z in (firma.inhaber, firma.name) if z)
    return {
        "an": auftrag.kontakt.email if auftrag.kontakt else "",
        "betreff": str(auftrag),
        "text": (
            f"{briefanrede(auftrag.kontakt)}\n\n"
            "vielen Dank für Ihren Auftrag. Anbei erhalten Sie meine "
            f"Auftragsbestätigung {auftrag.nummer} vom {auftrag.datum:%d.%m.%Y} "
            f"über {euro(auftrag.brutto)}.\n\n"
            f"Mit freundlichen Grüßen\n{gruss}"
        ),
        "kopie": True,
    }
