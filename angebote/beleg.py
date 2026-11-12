"""Angebot als PDF/A-3 mit derselben Vorlage wie die Rechnung, ohne E-Rechnungsdaten."""

import hashlib
from datetime import date
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contacts.models import Anschrift
from core.templatetags.kf import euro
from invoicing.beleg import (
    absaetze,
    absender_daten,
    briefanrede,
    briefkopf,
    datum_de,
    druck_positionen,
    druck_summen,
    druckbilder,
    empfaenger_daten,
    grussformel,
    kopf_druck,
    lieferanschrift_daten,
    lieferzeile,
    positionen_daten,
    schlusstext,
    setzen,
)
from invoicing.models import Position as Rechnungsposition
from invoicing.models import Rechnung, steuerhinweis

from .models import Angebot


def kopftext(kontakt):
    return (
        f"{briefanrede(kontakt)}\n\n"
        "vielen Dank für Ihre Anfrage. Gerne biete ich Ihnen folgende Leistungen an:"
    )


def fusstext(firma):
    return "Über Ihren Auftrag freue ich mich.\n\n" + grussformel(firma)


def beleg_daten(angebot, firma, nummer):
    """Alle Angaben des Angebots. Beim Fertigstellen eingefroren."""
    netto, ust, brutto = angebot.summen()
    return {
        "nummer": nummer,
        "datum": angebot.datum.isoformat(),
        "gueltig_bis": angebot.gueltig_bis.isoformat(),
        "steuerfall": angebot.steuerfall,
        "steuerhinweis": steuerhinweis(angebot.steuerfall, firma),
        "betreff": angebot.betreff,
        "kopftext": angebot.kopftext,
        "fusstext": angebot.fusstext,
        "absender": absender_daten(firma),
        "empfaenger": empfaenger_daten(angebot.kontakt, angebot.anschrift),
        "lieferanschrift": lieferanschrift_daten(
            angebot.kontakt, angebot.lieferanschrift
        ),
        "positionen": positionen_daten(angebot.positionen.all()),
        "netto": str(netto),
        "ust": str(ust),
        "brutto": str(brutto),
    }


def druckdaten(b, entwurf=False, logo=b"", unterschrift=b"", kopf=None):
    """Angebots-Angaben als fertig formatierte Texte für die Typst-Vorlage."""
    e = b["empfaenger"]
    info = [
        ("Angebotsnummer", b["nummer"] or "wird vergeben"),
        ("Angebotsdatum", datum_de(b["datum"])),
    ]
    if e["kundennummer"]:
        info.append(("Kundennummer", e["kundennummer"]))
    info.append(("Gültig bis", datum_de(b["gueltig_bis"])))
    return {
        "entwurf": entwurf,
        "titel": f"Angebot {b['nummer']}" if b["nummer"] else "Angebot (Entwurf)",
        **kopf_druck(logo, kopf),
        "unterschrift": list(unterschrift) or None,
        **briefkopf(b["absender"]),
        "empfaenger": e["zeilen"],
        "info": info,
        "betreff": b["betreff"],
        "lieferanschrift": lieferzeile(b),
        "kopftext": absaetze(b["kopftext"]),
        "positionen": druck_positionen(b["positionen"]),
        "summen": druck_summen(b),
        "summe_titel": "Gesamtbetrag",
        "brutto": euro(b["brutto"]),
        "steuerhinweis": b["steuerhinweis"],
        "zahlung": [f"Dieses Angebot gilt bis zum {datum_de(b['gueltig_bis'])}."],
        "girocode": None,
        "fusstext": schlusstext(b["fusstext"], b["absender"]),
    }


def pdf(b, entwurf=False, logo=b"", unterschrift=b"", kopf=None):
    return setzen(druckdaten(b, entwurf, logo, unterschrift, kopf))


def fertigstellen(angebot, firma):
    """Nummer vergeben, PDF erzeugen und unveränderbar ablegen."""
    with transaction.atomic():
        nummer = Angebot.naechste_nummer(angebot.datum)
        b = beleg_daten(angebot, firma, nummer)
        inhalt = pdf(b, **druckbilder(firma))
        relativ = (
            Path("archiv")
            / "angebote"
            / str(angebot.datum.year)
            / f"Angebot-{nummer}.pdf"
        )
        angebot.nummer = nummer
        angebot.beleg = b
        angebot.netto, angebot.ust, angebot.brutto = angebot.summen()
        angebot.datei = relativ.as_posix()
        angebot.sha256 = hashlib.sha256(inhalt).hexdigest()
        angebot.status = Angebot.Status.FERTIG
        angebot.fertiggestellt_am = timezone.now()
        angebot.save()
        ziel = Path(settings.DATA_DIR) / relativ
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with ziel.open("xb") as datei:  # niemals überschreiben
            datei.write(inhalt)
    return angebot


def rechnung_erstellen(angebot, firma):
    """Rechnungsentwurf mit Empfänger, Steuerfall, Betreff und allen Positionen.

    Kopf- und Schlusstext passen zur Rechnung; das Angebot gilt als angenommen.
    """
    with transaction.atomic():
        rechnung = Rechnung.objects.create(
            kontakt=angebot.kontakt,
            # Rechnungen gehen an die Rechnungsanschrift, wenn es eine gibt.
            anschrift=angebot.kontakt.anschrift_fuer(Anschrift.Art.RECHNUNG)
            or angebot.anschrift,
            lieferanschrift=angebot.lieferanschrift,
            steuerfall=angebot.steuerfall,
            betreff=angebot.betreff,
            kopftext=f"{briefanrede(angebot.kontakt)}\n\n"
            f"vielen Dank für Ihren Auftrag. Gemäß meinem Angebot {angebot.nummer} "
            f"vom {angebot.datum:%d.%m.%Y} berechne ich Ihnen folgende Leistungen:",
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
            for p in angebot.positionen.all()
        )
        angebot.rechnung = rechnung
        felder = ["rechnung", "geaendert"]
        if not angebot.antwort:
            angebot.antwort = Angebot.Antwort.ANGENOMMEN
            angebot.antwort_am = date.today()
            felder += ["antwort", "antwort_am"]
        angebot.save(update_fields=felder)
    return rechnung


def mail_vorschlag(angebot, firma):
    """Empfänger, Betreff und Text, die der Nutzer vor dem Senden noch ändern kann."""
    gruss = "\n".join(z for z in (firma.inhaber, firma.name) if z)
    return {
        "an": angebot.kontakt.email if angebot.kontakt else "",
        "betreff": str(angebot),
        "text": (
            f"{briefanrede(angebot.kontakt)}\n\n"
            f"anbei erhalten Sie mein Angebot {angebot.nummer} vom "
            f"{angebot.datum:%d.%m.%Y} über {euro(angebot.brutto)}. "
            f"Es gilt bis zum {angebot.gueltig_bis:%d.%m.%Y}.\n\n"
            f"Mit freundlichen Grüßen\n{gruss}"
        ),
        "kopie": True,
    }
