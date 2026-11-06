"""Offene Posten und Mahnungen: Aufstellung, PDF und Ablage (Spezifikation M-1, M-3)."""

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction

from core.templatetags.kf import euro, zahl
from invoicing.beleg import (
    absaetze,
    absender_daten,
    briefanrede,
    briefkopf,
    datum_de,
    druckbilder,
    empfaenger_daten,
    girocode_svg,
    grussformel,
    iban_lesbar,
    setzen,
)
from invoicing.models import Rechnung

from .models import DATEINAME, STUFEN, Mahnung
from .zinsen import PAUSCHALE, BasiszinsFehlt, aufschlag, verzug_ab, verzugszinsen


def posten(kontakt=None):
    """Festgeschriebene Rechnungen, die bezahlt werden müssen, mit allem für
    offenen Betrag und Mahnstufe vorab geladen."""
    abfrage = (
        Rechnung.objects.filter(
            status=Rechnung.Status.FESTGESCHRIEBEN,
            storno_zu__isnull=True,
            korrektur_zu__isnull=True,
        )
        .select_related("kontakt", "stornorechnung")
        .prefetch_related("zahlungen", "korrekturen", "mahnungen")
        .order_by("datum", "nummer")
    )
    if kontakt:
        abfrage = abfrage.filter(kontakt=kontakt)
    return list(abfrage)


def naechste_stufe(rechnung, stufen):
    """(Mahnstufe, fällig ab) des nächsten Schreibens, oder None."""
    if rechnung.offen <= 0:
        return None
    mahnungen = list(rechnung.mahnungen.all())
    if mahnungen:
        letzte = max(mahnungen, key=lambda m: m.stufe)
        if letzte.stufe >= max(STUFEN):
            return None
        nummer, vorher = letzte.stufe + 1, letzte.frist
    else:
        nummer, vorher = 1, rechnung.faellig
    return stufen[nummer], vorher + timedelta(days=stufen[nummer].abstand)


def offene_nebenkosten(rechnung):
    """Mahngebühren, Zinsen und Pauschale aus der letzten Mahnung, die noch fehlen."""
    mahnungen = list(rechnung.mahnungen.all())
    if not mahnungen:
        return Decimal("0.00")
    letzte = max(mahnungen, key=lambda m: m.stufe)
    gezahlt = sum((z.nebenkosten for z in rechnung.zahlungen.all()), Decimal("0"))
    return max(letzte.nebenkosten - gezahlt, Decimal("0.00"))


def berechnen(rechnung, stufe, datum, gebuehr, mit_zinsen, mit_pauschale):
    """Aufstellung der Forderung am Mahntag und Hinweise für das Formular."""
    frueher = [m for m in rechnung.mahnungen.all() if m.stufe < stufe]
    beginn = verzug_ab(rechnung, frueher)
    im_verzug = beginn is not None and beginn <= datum
    unternehmen = not rechnung.kontakt.ist_verbraucher
    hinweise, fehler = [], []

    korrigiert = rechnung.korrigierter_betrag
    zeilen = [
        (
            f"Rechnung {rechnung.nummer} vom {rechnung.datum:%d.%m.%Y}"
            + (" nach Korrektur" if korrigiert != rechnung.brutto else ""),
            korrigiert,
        )
    ]
    if rechnung.bezahlt:
        zeilen.append(("abzüglich Ihrer Zahlungen", -rechnung.bezahlt))
    if rechnung.ausgebucht:
        zeilen.append(("abzüglich Nachlass", -rechnung.ausgebucht))

    gebuehren = Decimal("0.00")
    for m in frueher:
        if m.gebuehr:
            zeilen.append(
                (f"Mahngebühr {m.bezeichnung} vom {m.datum:%d.%m.%Y}", m.gebuehr)
            )
            gebuehren += m.gebuehr
    if gebuehr:
        zeilen.append((f"Mahngebühr {STUFEN[stufe]}", gebuehr))
        gebuehren += gebuehr

    zinsen = Decimal("0.00")
    if mit_zinsen and im_verzug:
        try:
            zinsen, tage, saetze = verzugszinsen(rechnung, beginn, datum)
        except BasiszinsFehlt:
            fehler.append(
                "Für den Zeitraum fehlt ein Basiszinssatz. Tragen Sie ihn in den "
                "Einstellungen zum Mahnwesen ein oder verzichten Sie auf Zinsen."
            )
        else:
            if zinsen:
                plus = aufschlag(rechnung.kontakt)
                satz = ", ".join(f"{zahl(s, 2)} %" for s in saetze)
                zeilen.append(
                    (
                        f"Verzugszinsen vom {beginn:%d.%m.%Y} bis "
                        f"{datum - timedelta(days=1):%d.%m.%Y} ({tage} Tage, "
                        f"{zahl(plus)} Prozentpunkte über dem Basiszinssatz: {satz})",
                        zinsen,
                    )
                )

    pauschale = Decimal("0.00")
    schon_gefordert = any(m.pauschale for m in frueher)
    if schon_gefordert or (mit_pauschale and im_verzug and unternehmen):
        zeilen.append(("Verzugspauschale nach § 288 Abs. 5 BGB", PAUSCHALE))
        if not schon_gefordert:
            pauschale = PAUSCHALE
    elif mit_pauschale:
        hinweise.append(
            "Die Pauschale von 40 € steht Ihnen nur gegenüber Unternehmen zu, "
            "die in Verzug sind."
        )

    gezahlt_neben = sum((z.nebenkosten for z in rechnung.zahlungen.all()), Decimal("0"))
    if gezahlt_neben:
        zeilen.append(("abzüglich gezahlter Mahnkosten und Zinsen", -gezahlt_neben))

    if im_verzug:
        hinweise.insert(0, f"Der Kunde ist seit dem {beginn:%d.%m.%Y} in Verzug.")
    else:
        hinweise.insert(
            0,
            "Erst dieses Schreiben setzt den Kunden in Verzug, und zwar mit Ablauf "
            "der Frist. Zinsen und Pauschale fallen deshalb noch nicht an"
            + (
                ", und auch eine Mahngebühr darf es noch nicht kosten."
                if gebuehr
                else "."
            ),
        )

    nebenkosten = gebuehren + zinsen + (PAUSCHALE if schon_gefordert else pauschale)
    return {
        "zeilen": zeilen,
        "offen": rechnung.offen,
        "gebuehr": gebuehr,
        "zinsen": zinsen,
        "pauschale": pauschale,
        "nebenkosten": nebenkosten,
        "gesamt": rechnung.offen + nebenkosten - gezahlt_neben,
        "verzug_ab": beginn,
        "im_verzug": im_verzug,
        "unternehmen": unternehmen,
        "hinweise": hinweise,
        "fehler": fehler,
    }


def beleg_daten(rechnung, firma, stufe, datum, frist, text, aufstellung):
    """Alle Angaben des Schreibens. Beim Erstellen eingefroren."""
    return {
        "stufe": stufe,
        "bezeichnung": STUFEN[stufe],
        "datum": datum.isoformat(),
        "frist": frist.isoformat(),
        "text": text,
        "anrede": briefanrede(rechnung.kontakt),
        "rechnung": {
            "nummer": rechnung.nummer,
            "datum": rechnung.datum.isoformat(),
            "faellig": rechnung.faellig.isoformat(),
        },
        "absender": absender_daten(firma),
        "empfaenger": empfaenger_daten(rechnung.kontakt, rechnung.anschrift),
        "zeilen": [[t, str(b)] for t, b in aufstellung["zeilen"]],
        "gesamt": str(aufstellung["gesamt"]),
        "grussformel": grussformel(firma),
    }


def druckdaten(b, entwurf=False, logo=b"", unterschrift=b""):
    """Mahnung als fertig formatierte Texte für die Typst-Vorlage der Rechnung."""
    a, e, r = b["absender"], b["empfaenger"], b["rechnung"]
    info = [("Datum", datum_de(b["datum"]))]
    if e["kundennummer"]:
        info.append(("Kundennummer", e["kundennummer"]))
    info += [
        ("Rechnungsnummer", r["nummer"]),
        ("Rechnungsdatum", datum_de(r["datum"])),
        ("Fällig seit", datum_de(r["faellig"])),
    ]
    gesamt = Decimal(b["gesamt"])
    zahlung = [f"Bitte überweisen Sie {euro(gesamt)} bis zum {datum_de(b['frist'])}."]
    if a["iban"]:
        konto = ", ".join(z for z in (a["bank"], f"IBAN {iban_lesbar(a['iban'])}") if z)
        zahlung.append(f"Konto: {konto}")
        zahlung.append(f"Verwendungszweck: Rechnung {r['nummer']}")
    return {
        "entwurf": entwurf,
        "titel": b["bezeichnung"],
        "logo": list(logo) or None,
        "unterschrift": list(unterschrift) or None,
        **briefkopf(a),
        "empfaenger": e["zeilen"],
        "info": info,
        "betreff": f"Rechnung {r['nummer']} vom {datum_de(r['datum'])}",
        "kopftext": absaetze(f"{b['anrede']}\n\n{b['text']}"),
        "positionen": [],
        "aufstellung": [[t, euro(betrag)] for t, betrag in b["zeilen"]],
        "summen": [],
        "summe_titel": "Zu zahlen",
        "brutto": euro(gesamt),
        "steuerhinweis": "",
        "zahlung": zahlung,
        "girocode": girocode_svg(
            {"absender": a, "brutto": b["gesamt"], "nummer": r["nummer"]}
        )
        if a["iban"] and gesamt > 0
        else None,
        "fusstext": absaetze(b["grussformel"]),
    }


def pdf(b, entwurf=False, logo=b"", unterschrift=b""):
    return setzen(druckdaten(b, entwurf, logo, unterschrift))


def erstellen(rechnung, firma, stufe, datum, frist, text, gebuehr, zinsen, pauschale):
    """Mahnung berechnen, als PDF ablegen und speichern."""
    with transaction.atomic():
        aufstellung = berechnen(rechnung, stufe, datum, gebuehr, zinsen, pauschale)
        b = beleg_daten(rechnung, firma, stufe, datum, frist, text, aufstellung)
        inhalt = pdf(b, **druckbilder(firma))
        relativ = (
            Path("archiv")
            / "mahnungen"
            / str(datum.year)
            / f"{DATEINAME[stufe]}-{rechnung.nummer}.pdf"
        )
        mahnung = Mahnung.objects.create(
            rechnung=rechnung,
            stufe=stufe,
            datum=datum,
            frist=frist,
            offen=aufstellung["offen"],
            gebuehr=aufstellung["gebuehr"],
            zinsen=aufstellung["zinsen"],
            pauschale=aufstellung["pauschale"],
            nebenkosten=aufstellung["nebenkosten"],
            gesamt=aufstellung["gesamt"],
            beleg=b,
            datei=relativ.as_posix(),
            sha256=hashlib.sha256(inhalt).hexdigest(),
        )
        ziel = Path(settings.DATA_DIR) / relativ
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with ziel.open("xb") as datei:  # niemals überschreiben
            datei.write(inhalt)
    return mahnung


def mail_vorschlag(mahnung, firma):
    """Empfänger, Betreff und Text, die der Nutzer vor dem Senden noch ändern kann."""
    r = mahnung.rechnung
    gruss = "\n".join(z for z in (firma.inhaber, firma.name) if z)
    return {
        "an": r.kontakt.email if r.kontakt else "",
        "betreff": f"{mahnung.bezeichnung} zur Rechnung {r.nummer}",
        "text": (
            f"{briefanrede(r.kontakt)}\n\n"
            f"anbei erhalten Sie meine {mahnung.bezeichnung} zur Rechnung {r.nummer} "
            f"vom {r.datum:%d.%m.%Y}. Bitte überweisen Sie {euro(mahnung.gesamt)} "
            f"bis zum {mahnung.frist:%d.%m.%Y}.\n\n"
            f"Mit freundlichen Grüßen\n{gruss}"
        ),
        "kopie": True,
    }


def vorschlaege(rechnungen, stufen, heute=None):
    """Rechnungen, bei denen das nächste Schreiben fällig ist: [(Rechnung, Mahnstufe)]."""
    heute = heute or date.today()
    liste = []
    for rechnung in rechnungen:
        naechste = naechste_stufe(rechnung, stufen)
        if naechste and naechste[1] <= heute:
            liste.append((rechnung, naechste[0]))
    return liste
