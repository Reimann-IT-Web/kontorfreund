"""Rechnung als PDF/A-3 (Typst) mit eingebetteten ZUGFeRD-Daten (Profil EN 16931)."""

import base64
import calendar
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import typst
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from drafthorse.models.accounting import (
    ApplicableTradeTax,
    CategoryTradeTax,
    TradeAllowanceCharge,
)
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem
from drafthorse.pdf import attach_xml
from PIL import Image, ImageChops, ImageOps
from segno import helpers as qr

from contacts.models import ist_leitweg_id
from core.templatetags.kf import euro, zahl

from .models import Rechnung, rabatt_betrag, runden, steuerhinweis

# XRechnung 3.0 in der Syntax CII; gültig ist Version 3.0.2, Version 4.0 erst ab 2027.
XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
ABRECHNUNG = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# Damit kommen auch Verbraucher ohne Mahnung in Verzug (§ 286 Abs. 3 Satz 1 Halbsatz 2 BGB).
VERZUGSHINWEIS = (
    "Zahlen Sie nicht innerhalb von 30 Tagen nach Fälligkeit und Zugang dieser "
    "Rechnung, kommen Sie nach § 286 Abs. 3 BGB auch ohne Mahnung in Verzug."
)
# Eigener Zahlungshinweis aus den Firmendaten: nur diese Platzhalter werden ersetzt.
ZAHLUNG_PLATZHALTER = ("betrag", "nummer", "datum", "faellig", "iban", "bank")
# Entspricht dem Text, den Kontorfreund ohne eigenen Hinweis druckt.
ZAHLUNG_BEISPIEL = (
    "Zahlbar ohne Abzug bis zum {faellig}.\n"
    "Bitte überweisen Sie den Betrag auf folgendes Konto: {bank}, IBAN {iban}\n"
    "Verwendungszweck: Rechnung {nummer}"
)

VORLAGE = Path(__file__).parent / "typst" / "rechnung.typ"
SCHRIFTEN = Path(__file__).parent / "schrift"
# Typst-Wurzel für Vorlagen anderer Apps, die den Briefkopf aus typst/kopf.typ laden.
WURZEL = Path(__file__).parent.parent

# Briefkopf (B-6): So breit darf ein Logo höchstens werden, damit Firmenname und Anschrift
# daneben Platz behalten (Satzspiegel 165 mm).
SATZBREITE_MM = 165
PLATZ_DANEBEN_MM = 50
LOGO_MINDESTBREITE_MM = 40
# Größere Bilder werden nicht zugeschnitten (Schutz vor Dekompressionsbomben).
ZUSCHNEIDEN_PIXEL = 40_000_000
# Heller als das gilt beim Zuschneiden als weißer Rand.
WEISS = 245
# Die Vorschau des Briefkopfs zeigt die Seite bis knapp über dem Beginn des Inhalts.
VORSCHAU_MM = 92

MONATE = (
    "Januar Februar März April Mai Juni Juli August September Oktober November Dezember"
).split()

# Mengeneinheiten nach UN/ECE Recommendation 20, wie sie EN 16931 verlangt.
EINHEIT_CODE = {
    "Stück": "H87",
    "Std.": "HUR",
    "Tag": "DAY",
    "Monat": "MON",
    "Pauschale": "LS",
}
LAND_CODE = {
    "": "DE",
    "Deutschland": "DE",
    "Österreich": "AT",
    "Schweiz": "CH",
    "Niederlande": "NL",
    "Belgien": "BE",
    "Luxemburg": "LU",
    "Frankreich": "FR",
    "Dänemark": "DK",
    "Polen": "PL",
    "Tschechien": "CZ",
    "Italien": "IT",
    "Spanien": "ES",
}
# Umsatzsteuer-Kategorie (UNTDID 5305), Satz, Befreiungsgrund und -code je Steuerfall.
KATEGORIE = {
    Rechnung.Steuerfall.KLEINUNTERNEHMER: (
        "E",
        Decimal("0"),
        "Kleinunternehmer gemäß § 19 UStG",
        "",
    ),
    Rechnung.Steuerfall.REGEL: ("S", Decimal("19"), "", ""),
    Rechnung.Steuerfall.UMKEHR: (
        "AE",
        Decimal("0"),
        "Steuerschuldnerschaft des Leistungsempfängers",
        "VATEX-EU-AE",
    ),
    # Befreiungsgrund (BT-120) ist der Hinweis des Belegs. Einen VATEX-Code setzt
    # Kontorfreund nicht, weil es die Rechtsgrundlage der Befreiung nicht kennt.
    Rechnung.Steuerfall.STEUERFREI: ("E", Decimal("0"), None, ""),
}


def datum_de(wert):
    return date.fromisoformat(wert).strftime("%d.%m.%Y") if wert else ""


def leistungszeit(von, bis):
    """(Bezeichnung, Text): ein Tag, ein ganzer Monat oder ein Zeitraum."""
    von = date.fromisoformat(von)
    bis = date.fromisoformat(bis) if bis else von
    if bis == von:
        return "Leistungsdatum", von.strftime("%d.%m.%Y")
    if (
        (von.year, von.month) == (bis.year, bis.month)
        and von.day == 1
        and bis.day == calendar.monthrange(bis.year, bis.month)[1]
    ):
        return "Leistungszeitraum", f"{MONATE[von.month - 1]} {von.year}"
    return "Leistungszeitraum", f"{von:%d.%m.%Y} – {bis:%d.%m.%Y}"


def briefanrede(kontakt):
    if kontakt and kontakt.nachname and kontakt.anrede in ("Herr", "Frau"):
        name = " ".join(t for t in [kontakt.titel, kontakt.nachname] if t)
        if kontakt.anrede == "Herr":
            return f"Sehr geehrter Herr {name},"
        return f"Sehr geehrte Frau {name},"
    return "Sehr geehrte Damen und Herren,"


def grussformel(firma):
    return "Mit freundlichen Grüßen\n\n" + (firma.inhaber or firma.name)


def absender_daten(firma):
    return {
        feld: getattr(firma, feld)
        for feld in (
            "name",
            "marke",
            "inhaber",
            "strasse",
            "plz",
            "ort",
            "steuernummer",
            "ust_id",
            "email",
            "telefon",
            "internetadresse",
            "iban",
            "bank",
            "unterschrift_text",
        )
    }


def druckbilder(firma):
    """Bilder und Briefkopf für den Druck; sie liegen nur in den Firmendaten, nicht im Beleg.

    Maßgeblich für einen festgeschriebenen Beleg ist das abgelegte PDF, deshalb gelten
    geänderte Einstellungen nur für Belege, die danach entstehen.
    """
    kopf = kopf_einstellungen(firma)
    logo = bytes(firma.logo)
    if kopf["bild"]:
        logo = b""  # Das Kopfbild ersetzt Logo und Angaben.
    elif firma.logo_zuschneiden:
        logo = zuschneiden(logo)
    return {"logo": logo, "unterschrift": bytes(firma.unterschrift), "kopf": kopf}


def kopf_einstellungen(firma):
    """Aufbau des Briefkopfs für kopf.typ; `bild` ist das Kopfbild oder leer."""
    bild = bytes(firma.kopfbild) if firma.kopf_art == firma.Kopfart.BILD else b""
    breite = SATZBREITE_MM
    for gezeigt in (firma.kopf_name, firma.kopf_anschrift):
        if gezeigt:
            breite -= PLATZ_DANEBEN_MM
    return {
        "art": firma.Kopfart.BILD if bild else firma.Kopfart.LOGO,
        "lage": firma.logo_lage,
        "logo_hoehe": firma.logo_hoehe,
        "logo_breite": max(breite, LOGO_MINDESTBREITE_MM),
        "name": firma.kopf_name,
        "anschrift": firma.kopf_anschrift,
        "linie": firma.kopf_linie,
        "farbe": firma.akzentfarbe.lower(),
        "breite": firma.kopfbild_breite,
        "bild": bild,
    }


def kopf_druck(logo, kopf):
    """Logo, Kopfbild und Aufbau des Briefkopfs als Druckdaten; ohne `kopf` der bisherige Kopf."""
    kopf = dict(kopf or {})
    bild = kopf.pop("bild", b"")
    return {
        "logo": list(logo) or None,
        "kopfbild": list(bild) or None,
        "briefkopf": kopf or None,
    }


@lru_cache(maxsize=4)
def zuschneiden(daten):
    """PNG oder JPG ohne weißen oder durchsichtigen Rand; alles andere unverändert."""
    if not daten.startswith((b"\x89PNG", b"\xff\xd8")):
        return daten
    try:
        with Image.open(BytesIO(daten)) as bild:
            if bild.width * bild.height > ZUSCHNEIDEN_PIXEL:
                return daten
            jpeg = bild.format == "JPEG"
            bild = ImageOps.exif_transpose(bild)
            rgba = bild.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError):
        return daten
    sichtbar = rgba.getchannel("A").point(lambda a: 255 if a > 8 else 0)
    farbig = rgba.convert("L").point(lambda w: 255 if w < WEISS else 0)
    rahmen = ImageChops.multiply(sichtbar, farbig).getbbox()
    if not rahmen or rahmen == (0, 0, *rgba.size):
        return daten
    ausschnitt = bild.crop(rahmen)
    ausgabe = BytesIO()
    if jpeg:
        ausschnitt.convert("RGB").save(ausgabe, format="JPEG", quality=95)
    else:
        ausschnitt.save(ausgabe, format="PNG")
    return ausgabe.getvalue()


def empfaenger_daten(k, anschrift=None):
    """Empfänger mit einer weiteren Anschrift (K-1) oder der Standardanschrift."""
    a = anschrift or k
    return {
        "zeilen": k.anschrift_zeilen(anschrift) if k else [],
        "name": k.anzeigename if k else "",
        "kundennummer": k.kundennummer if k else "",
        "strasse": a.strasse if k else "",
        "plz": a.plz if k else "",
        "ort": a.ort if k else "",
        "land": a.land if k else "",
        "ust_id": k.ust_id if k else "",
        "email": k.email if k else "",
    }


def lieferanschrift_daten(k, anschrift):
    """Lieferanschrift (BG-13, BG-15), None ohne eigene."""
    if not (k and anschrift):
        return None
    return {
        "zeilen": k.anschrift_zeilen(anschrift),
        "name": k.anzeigename,
        "zusatz": anschrift.zusatz,
        "strasse": anschrift.strasse,
        "plz": anschrift.plz,
        "ort": anschrift.ort,
        "land": anschrift.land,
    }


def anschriften_wahl(kontakt):
    """Weitere Anschriften für die Auswahl im Editor: (Anschrift, Zeilen mit „|“)."""
    return [
        (a, "|".join(kontakt.anschrift_zeilen(a))) for a in kontakt.anschriften.all()
    ]


def lieferzeile(b):
    """Lieferanschrift für das PDF in einer Zeile; ältere Belege kennen sie nicht."""
    lieferung = b.get("lieferanschrift")
    return ", ".join(lieferung["zeilen"]) if lieferung else None


def positionen_daten(positionen):
    return [
        {
            "nr": p.nr,
            "bezeichnung": p.bezeichnung,
            "beschreibung": p.beschreibung,
            "menge": str(p.menge),
            "einheit": p.einheit,
            "preis": str(p.preis),
            "gesamt": str(p.gesamt),
        }
        for p in positionen
    ]


def rabatt_daten(beleg):
    """Rabatt auf die Summe der Positionen; None ohne Rabatt (wie in älteren Belegen)."""
    if not beleg.rabatt_prozent:
        return None
    zwischensumme = sum((p.gesamt for p in beleg.positionen.all()), Decimal("0.00"))
    return {
        "prozent": f"{beleg.rabatt_prozent:.2f}",
        "zwischensumme": str(zwischensumme),
        "betrag": str(rabatt_betrag(zwischensumme, beleg.rabatt_prozent)),
    }


def skonto_daten(rechnung, brutto):
    """Vereinbartes Skonto (§ 14 Abs. 4 Nr. 7 UStG), nur wenn etwas zu zahlen ist."""
    if not (rechnung.skonto_prozent > 0 and brutto > 0):
        return None
    abzug = runden(brutto * rechnung.skonto_prozent / 100)
    return {
        "prozent": f"{rechnung.skonto_prozent:.2f}",
        "tage": rechnung.skonto_tage,
        "bis": rechnung.skonto_bis.isoformat(),
        "betrag": str(abzug),
        "zahlbetrag": str(brutto - abzug),
    }


def beleg_steuerhinweis(rechnung, firma):
    """Storno und Korrektur behalten den eingefrorenen Hinweis ihres Originals."""
    original = rechnung.storno_zu or rechnung.korrektur_zu
    if original and original.beleg and original.steuerfall == rechnung.steuerfall:
        return original.beleg.get("steuerhinweis", "")
    return steuerhinweis(rechnung.steuerfall, firma)


def beleg_daten(rechnung, firma, nummer):
    """Alle Angaben des Belegs. Beim Festschreiben eingefroren, danach nie neu berechnet."""
    netto, ust, brutto = rechnung.summen()
    k = rechnung.kontakt
    o = rechnung.storno_zu
    r = rechnung.korrektur_zu
    return {
        "nummer": nummer,
        "storno_zu": {"nummer": o.nummer, "datum": o.datum.isoformat()} if o else None,
        "korrektur_zu": {"nummer": r.nummer, "datum": r.datum.isoformat()}
        if r
        else None,
        "datum": rechnung.datum.isoformat(),
        "faellig": rechnung.faellig.isoformat(),
        "zahlungsziel": rechnung.zahlungsziel,
        "skonto": skonto_daten(rechnung, brutto),
        # Ohne diesen Hinweis kommen Verbraucher erst durch eine Mahnung in Verzug.
        "verzugshinweis": bool(
            rechnung.verzugshinweis and k and k.ist_verbraucher and brutto > 0
        ),
        "leistung_von": rechnung.leistung_von.isoformat()
        if rechnung.leistung_von
        else "",
        "leistung_bis": rechnung.leistung_bis.isoformat()
        if rechnung.leistung_bis
        else "",
        "steuerfall": rechnung.steuerfall,
        "steuerhinweis": beleg_steuerhinweis(rechnung, firma),
        "referenz": rechnung.kaeuferreferenz,
        "xrechnung": bool(k and k.xrechnung),
        "betreff": rechnung.betreff,
        "kopftext": rechnung.kopftext,
        "fusstext": rechnung.fusstext,
        "zahlungstext": firma.zahlungstext,
        "girocode": bool(rechnung.girocode and firma.iban),
        "absender": absender_daten(firma),
        "empfaenger": empfaenger_daten(k, rechnung.anschrift),
        "lieferanschrift": lieferanschrift_daten(k, rechnung.lieferanschrift),
        "positionen": positionen_daten(rechnung.positionen.all()),
        "rabatt": rabatt_daten(rechnung),
        "netto": str(netto),
        "ust": str(ust),
        "brutto": str(brutto),
    }


def absaetze(text):
    return [
        absatz.splitlines() for absatz in text.strip().split("\n\n") if absatz.strip()
    ]


def schlusstext(text, a):
    """Absätze nach den Positionen; steht der Name unter der Unterschrift, nicht davor."""
    name = a["inhaber"] or a["name"]
    text = text.strip()
    if text.splitlines()[-1:] == [name] and name in a["unterschrift_text"]:
        text = text.removesuffix(name)
    return absaetze(text)


def girocode_svg(b):
    """SEPA-Überweisungscode (EPC069-12) als SVG."""
    a = b["absender"]
    code = qr.make_epc_qr(
        name=a["name"][:70],
        iban=a["iban"],
        amount=Decimal(b["brutto"]),
        text=f"Rechnung {b['nummer']}" if b["nummer"] else "Rechnung",
    )
    ausgabe = BytesIO()
    code.save(ausgabe, kind="svg", border=0, xmldecl=False, svgns=True)
    return ausgabe.getvalue().decode()


def druckdaten(b, entwurf=False, logo=b"", unterschrift=b"", kopf=None):
    """Beleg-Angaben als fertig formatierte Texte für die Typst-Vorlage."""
    a, e, storno = b["absender"], b["empfaenger"], b["storno_zu"]
    korrektur = b.get("korrektur_zu")
    info = [("Rechnungsnummer", b["nummer"] or "wird vergeben")]
    info.append(("Rechnungsdatum", datum_de(b["datum"])))
    if storno or korrektur:
        # Datum steht im Text darunter
        info.append(("Zur Rechnung", (storno or korrektur)["nummer"]))
    if e["kundennummer"]:
        info.append(("Kundennummer", e["kundennummer"]))
    if b["leistung_von"]:
        info.append(leistungszeit(b["leistung_von"], b["leistung_bis"]))
    if b["referenz"]:
        art = "Leitweg-ID" if ist_leitweg_id(b["referenz"]) else "Ihre Referenz"
        info.append((art, b["referenz"]))

    iban = iban_lesbar(a["iban"])
    eigener = b.get("zahlungstext", "").strip()  # ältere Belege kennen ihn nicht
    if storno:
        zahlung = [
            f"Die Rechnung {storno['nummer']} ist damit nicht mehr zu bezahlen. "
            "Einen bereits gezahlten Betrag erhalten Sie zurück."
        ]
    elif korrektur:
        zahlung = [
            f"Der Betrag der Rechnung {korrektur['nummer']} mindert sich damit um "
            f"{euro(-Decimal(b['brutto']))}. Haben Sie bereits mehr gezahlt, "
            "erhalten Sie den Unterschied zurück."
        ]
    elif eigener:
        zahlung = zahlungshinweis(eigener, b)
    elif b["zahlungsziel"] == 0:
        zahlung = ["Zahlbar sofort ohne Abzug."]
    else:
        zahlung = [f"Zahlbar ohne Abzug bis zum {datum_de(b['faellig'])}."]
    if skonto := b.get("skonto"):
        zahlung.append(
            f"Bei Zahlung bis zum {datum_de(skonto['bis'])} ziehen Sie "
            f"{zahl(skonto['prozent'])} % Skonto ab ({euro(skonto['betrag'])}) "
            f"und überweisen {euro(skonto['zahlbetrag'])}."
        )
    if iban and not (storno or korrektur or eigener):
        konto = ", ".join(z for z in (a["bank"], f"IBAN {iban}") if z)
        zahlung.append(f"Bitte überweisen Sie den Betrag auf folgendes Konto: {konto}")
        if b["nummer"]:
            zahlung.append(f"Verwendungszweck: Rechnung {b['nummer']}")
    if b.get("verzugshinweis"):
        zahlung.append(VERZUGSHINWEIS)

    art = (
        "Stornorechnung"
        if storno
        else "Rechnungskorrektur"
        if korrektur
        else "Rechnung"
    )
    titel = f"{art} {b['nummer']}" if b["nummer"] else f"{art} (Entwurf)"
    return {
        "entwurf": entwurf,
        "titel": titel,
        **kopf_druck(logo, kopf),
        "unterschrift": list(unterschrift) or None,
        **briefkopf(a),
        "empfaenger": e["zeilen"],
        "info": info,
        "betreff": b["betreff"],
        "lieferanschrift": lieferzeile(b),
        "kopftext": absaetze(b["kopftext"]),
        "positionen": druck_positionen(b["positionen"]),
        "summen": druck_summen(b),
        "summe_titel": "Korrekturbetrag" if korrektur else "Rechnungsbetrag",
        "brutto": euro(b["brutto"]),
        "steuerhinweis": b["steuerhinweis"],
        "zahlung": zahlung,
        "girocode": girocode_svg(b)
        if b["girocode"] and Decimal(b["brutto"]) > 0
        else None,
        "fusstext": schlusstext(b["fusstext"], a),
    }


def iban_lesbar(iban):
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def unbekannte_platzhalter(text):
    """Namen in geschweiften Klammern, die der Zahlungshinweis nicht kennt."""
    namen = dict.fromkeys(re.findall(r"\{([^{}]*)\}", text))
    return [n for n in namen if n not in ZAHLUNG_PLATZHALTER]


def zahlungshinweis(text, b):
    """Eigener Zahlungshinweis mit den Angaben des Belegs, als Zeilen."""
    a = b["absender"]
    werte = {
        "betrag": euro(b["brutto"]),
        "nummer": b["nummer"] or "(wird vergeben)",
        "datum": datum_de(b["datum"]),
        "faellig": datum_de(b["faellig"]),
        "iban": iban_lesbar(a["iban"]),
        "bank": a["bank"],
    }
    for name in ZAHLUNG_PLATZHALTER:
        text = text.replace("{" + name + "}", werte[name])
    return text.strip().splitlines()


def briefkopf(a):
    """Absender für Kopf, Rücksendeangabe und Fußzeile, gleich für jede Belegart."""
    iban = iban_lesbar(a["iban"])
    return {
        "absender_name": a["name"],
        "marke": a["marke"],
        "unterschrift_text": a["unterschrift_text"].splitlines(),
        "kopf": [
            z
            for z in (
                a["strasse"],
                f"{a['plz']} {a['ort']}".strip(),
                a["telefon"],
                a["email"],
            )
            if z
        ],
        "ruecksende": " · ".join(
            z for z in (a["name"], a["strasse"], f"{a['plz']} {a['ort']}".strip()) if z
        ),
        "fuss": [
            [
                z
                for z in (
                    a["name"],
                    a["inhaber"],
                    a["strasse"],
                    f"{a['plz']} {a['ort']}",
                )
                if z.strip()
            ],
            [
                z
                for z in (
                    f"Telefon {a['telefon']}" if a["telefon"] else "",
                    a["email"],
                    a["internetadresse"],
                )
                if z
            ],
            [
                z
                for z in (
                    a["bank"],
                    f"IBAN {iban}" if iban else "",
                    f"Steuernummer {a['steuernummer']}" if a["steuernummer"] else "",
                    f"USt-IdNr. {a['ust_id']}" if a["ust_id"] else "",
                )
                if z
            ],
        ],
    }


def druck_positionen(positionen):
    return [
        {
            "nr": str(p["nr"]),
            "bezeichnung": p["bezeichnung"],
            "beschreibung": p["beschreibung"].splitlines(),
            "menge": f"{zahl(p['menge'])} {p['einheit']}".strip(),
            "preis": euro(p["preis"]),
            "gesamt": euro(p["gesamt"]),
        }
        for p in positionen
    ]


def druck_summen(b):
    """Zeilen über dem Gesamtbetrag: Zwischensumme und Rabatt, falls es einen gibt,
    Netto und Umsatzsteuer, wenn Steuer ausgewiesen wird."""
    zeilen = []
    if rabatt := b.get("rabatt"):
        zeilen += [
            ["Zwischensumme", euro(rabatt["zwischensumme"])],
            [f"Rabatt {zahl(rabatt['prozent'])} %", euro(-Decimal(rabatt["betrag"]))],
        ]
    if b["steuerfall"] == Rechnung.Steuerfall.REGEL:
        zeilen += [
            ["Nettobetrag", euro(b["netto"])],
            ["Umsatzsteuer 19 %", euro(b["ust"])],
        ]
    return zeilen


def setzen(druck, format="pdf", ppi=110):
    """Druckdaten mit der Typst-Vorlage setzen, als PDF/A-3b oder als Bild."""
    return typst.compile(
        str(VORLAGE),
        font_paths=[str(SCHRIFTEN)],
        ignore_system_fonts=True,
        sys_inputs={"daten": json.dumps(druck)},
        format=format,
        **({"pdf_standards": "a-3b"} if format == "pdf" else {"ppi": ppi}),
    )


def pdf(b, entwurf=False, logo=b"", unterschrift=b"", kopf=None, format="pdf"):
    return setzen(druckdaten(b, entwurf, logo, unterschrift, kopf), format)


def kopf_vorschau(firma):
    """Oberer Teil einer Rechnung mit dem Briefkopf als PNG-Daten-URL (B-6).

    Gesetzt mit der echten Vorlage und den Firmendaten, ohne Empfänger und Inhalt; so zeigt
    die Vorschau auch, wie der Kopf zu Anschriftfeld und Infoblock steht.
    """
    bilder = druckbilder(firma)
    druck = {
        **briefkopf(absender_daten(firma)),
        **kopf_druck(bilder["logo"], bilder["kopf"]),
        "entwurf": False,
        "titel": "",
        "unterschrift": None,
        "unterschrift_text": [],
        "empfaenger": ["Anschrift des Empfängers"],
        "info": [
            ("Rechnungsnummer", "wird vergeben"),
            ("Rechnungsdatum", datum_de(timezone.localdate().isoformat())),
        ],
        "betreff": "",
        "kopftext": [],
        "positionen": [],
        "summen": [],
        "summe_titel": "",
        "brutto": "",
        "steuerhinweis": "",
        "zahlung": [],
        "girocode": None,
        "fusstext": [],
    }
    seiten = setzen(druck, "png", ppi=150)
    seite = seiten[0] if isinstance(seiten, list) else seiten
    with Image.open(BytesIO(seite)) as bild:
        oben = bild.crop((0, 0, bild.width, round(bild.height * VORSCHAU_MM / 297)))
    ausgabe = BytesIO()
    oben.save(ausgabe, format="PNG")
    return "data:image/png;base64," + base64.b64encode(ausgabe.getvalue()).decode()


def logo_lesbar(daten):
    try:
        typst.compile(
            b"#image(bytes(json(bytes(sys.inputs.logo))))",
            sys_inputs={"logo": json.dumps(list(daten))},
            format="svg",
        )
    except typst.TypstError:
        return False
    return True


def seitenbilder(inhalt):
    """PDF-Seiten als PNG-Daten-URLs; die Ansicht braucht so keinen PDF-Betrachter im Browser."""
    bilder = []
    dokument = pdfium.PdfDocument(inhalt)
    for seite in dokument:
        ausgabe = BytesIO()
        seite.render(scale=2).to_pil().save(ausgabe, format="PNG")
        bilder.append(
            "data:image/png;base64," + base64.b64encode(ausgabe.getvalue()).decode()
        )
    dokument.close()
    return bilder


def zugferd(b):
    """Rechnungsdaten als CII-XML nach EN 16931, auf Wunsch als XRechnung.

    None, wenn das Land des Empfängers oder der Lieferanschrift unbekannt ist.
    """
    a, e = b["absender"], b["empfaenger"]
    lieferung = b.get("lieferanschrift")
    if e["land"] not in LAND_CODE or (lieferung and lieferung["land"] not in LAND_CODE):
        return None
    kategorie, satz, grund, grund_code = KATEGORIE[b["steuerfall"]]
    if grund is None:
        grund = b["steuerhinweis"]
    xrechnung = b.get("xrechnung", False)

    doc = Document()
    if xrechnung:
        doc.context.business_parameter.id = ABRECHNUNG
    doc.context.guideline_parameter.id = (
        XRECHNUNG if xrechnung else "urn:cen.eu:en16931:2017"
    )
    doc.header.id = b["nummer"]
    doc.header.type_code = "380"
    doc.header.issue_date_time = date.fromisoformat(b["datum"])
    if b["steuerhinweis"]:
        notiz = IncludedNote()
        notiz.content = b["steuerhinweis"]
        doc.header.notes.add(notiz)

    verkaeufer = doc.trade.agreement.seller
    verkaeufer.name = a["name"]
    if xrechnung:
        # Ansprechpartner des Verkäufers (BG-6) verlangt die XRechnung immer.
        verkaeufer.contact.person_name = a["inhaber"] or a["name"]
        verkaeufer.contact.telephone.number = a["telefon"]
        verkaeufer.contact.email.address = a["email"]
    verkaeufer.address.line_one = a["strasse"]
    verkaeufer.address.postcode = a["plz"]
    verkaeufer.address.city_name = a["ort"]
    verkaeufer.address.country_id = "DE"
    if a["email"]:
        verkaeufer.electronic_address.uri_ID = ("EM", a["email"])
    if a["ust_id"]:
        verkaeufer.tax_registrations.add(TaxRegistration(id=("VA", a["ust_id"])))
    if a["steuernummer"]:
        verkaeufer.tax_registrations.add(TaxRegistration(id=("FC", a["steuernummer"])))

    kaeufer = doc.trade.agreement.buyer
    kaeufer.name = e["name"]
    kaeufer.address.line_one = e["strasse"]
    kaeufer.address.postcode = e["plz"]
    kaeufer.address.city_name = e["ort"]
    kaeufer.address.country_id = LAND_CODE[e["land"]]
    if xrechnung:
        # Elektronische Adresse des Käufers (BT-49): Leitweg-ID (Schema 0204) oder E-Mail.
        kaeufer.electronic_address.uri_ID = (
            ("0204", b["referenz"])
            if ist_leitweg_id(b["referenz"])
            else ("EM", e["email"])
        )
    if e["ust_id"]:
        kaeufer.tax_registrations.add(TaxRegistration(id=("VA", e["ust_id"])))
    if b["referenz"]:
        doc.trade.agreement.buyer_reference = b["referenz"]
    # Bezug auf die Rechnung, die storniert oder korrigiert wird (BT-25, BT-26).
    if original := b["storno_zu"] or b.get("korrektur_zu"):
        bezug = doc.trade.settlement.invoice_referenced_document
        bezug.issuer_assigned_id = original["nummer"]
        bezug.issue_date_time = date.fromisoformat(original["datum"])

    if lieferung:
        # Lieferanschrift (BT-70, BG-15); die Zusatzzeile wird Zeile 2 der Anschrift.
        an = doc.trade.delivery.ship_to
        an.name = lieferung["name"]
        an.address.line_one = lieferung["strasse"]
        if lieferung["zusatz"]:
            an.address.line_two = lieferung["zusatz"]
        an.address.postcode = lieferung["plz"]
        an.address.city_name = lieferung["ort"]
        an.address.country_id = LAND_CODE[lieferung["land"]]

    von, bis = b["leistung_von"], b["leistung_bis"] or b["leistung_von"]
    if von == bis:
        doc.trade.delivery.event.occurrence = date.fromisoformat(von)
    else:
        doc.trade.settlement.period.start = date.fromisoformat(von)
        doc.trade.settlement.period.end = date.fromisoformat(bis)

    for p in b["positionen"]:
        zeile = LineItem()
        zeile.document.line_id = str(p["nr"])
        zeile.product.name = p["bezeichnung"]
        if p["beschreibung"]:
            zeile.product.description = p["beschreibung"]
        zeile.agreement.net.amount = Decimal(p["preis"])
        zeile.delivery.billed_quantity = (
            Decimal(p["menge"]),
            EINHEIT_CODE.get(p["einheit"], "C62"),
        )
        zeile.settlement.trade_tax.type_code = "VAT"
        zeile.settlement.trade_tax.category_code = kategorie
        zeile.settlement.trade_tax.rate_applicable_percent = satz
        zeile.settlement.monetary_summation.total_amount = Decimal(p["gesamt"])
        doc.trade.items.add(zeile)

    abrechnung = doc.trade.settlement
    abrechnung.currency_code = "EUR"
    abrechnung.payment_reference = f"Rechnung {b['nummer']}"
    # Zahlungsangaben nur, wenn der Kunde etwas zu zahlen hat (nicht beim Storno);
    # die XRechnung verlangt den Zahlungsweg immer (BR-DE-1).
    zu_zahlen = Decimal(b["brutto"]) > 0
    if a["iban"] and (zu_zahlen or xrechnung):
        zahlweg = PaymentMeans()
        zahlweg.type_code = "58"  # SEPA-Überweisung
        zahlweg.payee_account.iban = a["iban"]
        abrechnung.payment_means.add(zahlweg)
    if zu_zahlen:
        bedingung = PaymentTerms()
        bedingung.due = date.fromisoformat(b["faellig"])
        if skonto := b.get("skonto"):
            # Skonto in BT-20 in der Form, die die XRechnung vorgibt (BR-DE-18).
            prozent = Decimal(skonto["prozent"])
            bedingung.description = (
                f"#SKONTO#TAGE={skonto['tage']}#PROZENT={prozent:.2f}#\n"
            )
        abrechnung.terms.add(bedingung)

    rabatt = b.get("rabatt")
    if rabatt:
        # Abschlag auf Belegebene (BG-20) mit derselben Steuerkategorie wie die Positionen.
        abschlag = TradeAllowanceCharge()
        abschlag.indicator = False
        abschlag.calculation_percent = Decimal(rabatt["prozent"])
        abschlag.basis_amount = Decimal(rabatt["zwischensumme"])
        abschlag.actual_amount = Decimal(rabatt["betrag"])
        abschlag.reason_code = "95"  # Discount (UNTDID 5189)
        abschlag.reason = "Rabatt"
        abschlag_steuer = CategoryTradeTax()
        abschlag_steuer.type_code = "VAT"
        abschlag_steuer.category_code = kategorie
        abschlag_steuer.rate_applicable_percent = satz
        abschlag.trade_tax.add(abschlag_steuer)
        abrechnung.allowance_charge.add(abschlag)

    steuer = ApplicableTradeTax()
    steuer.calculated_amount = Decimal(b["ust"])
    steuer.basis_amount = Decimal(b["netto"])
    steuer.type_code = "VAT"
    steuer.category_code = kategorie
    steuer.rate_applicable_percent = satz
    if grund:
        steuer.exemption_reason = grund
    if grund_code:
        steuer.exemption_reason_code = grund_code
    abrechnung.trade_tax.add(steuer)

    summe = abrechnung.monetary_summation
    summe.line_total = Decimal(rabatt["zwischensumme"] if rabatt else b["netto"])
    if rabatt:
        summe.allowance_total = Decimal(rabatt["betrag"])
    summe.tax_basis_total = Decimal(b["netto"])
    summe.tax_total = (Decimal(b["ust"]), "EUR")
    summe.grand_total = Decimal(b["brutto"])
    summe.due_amount = Decimal(b["brutto"])
    return doc.serialize(schema="FACTUR-X_EN16931")


def endgueltiges_pdf(b, **bilder):
    """PDF/A-3 mit eingebetteter XML, dazu die XML selbst (None, wenn keine entsteht)."""
    xml = zugferd(b)
    if b["xrechnung"] and not xml:
        raise ValueError(
            "Für eine XRechnung muss das Land des Empfängers und der "
            "Lieferanschrift bekannt sein."
        )
    inhalt = pdf(b, **bilder)
    return (attach_xml(inhalt, xml, lang="de-DE") if xml else inhalt), xml


def festschreiben(rechnung, firma):
    """Nummer vergeben, PDF (bei XRechnung auch die XML) erzeugen und unveränderbar ablegen."""
    with transaction.atomic():
        nummer = Rechnung.naechste_nummer(rechnung.datum)
        b = beleg_daten(rechnung, firma, nummer)
        inhalt, xml = endgueltiges_pdf(b, **druckbilder(firma))
        relativ = (
            Path("archiv")
            / "rechnungen"
            / str(rechnung.datum.year)
            / f"{rechnung.bezeichnung}-{nummer}.pdf"
        )
        dateien = {relativ: inhalt}
        if b["xrechnung"]:
            # Bei der E-Rechnung ist die XML das maßgebliche Original (Spezifikation B-9).
            dateien[relativ.with_suffix(".xml")] = xml
            rechnung.xml_datei = relativ.with_suffix(".xml").as_posix()
            rechnung.xml_sha256 = hashlib.sha256(xml).hexdigest()
        rechnung.nummer = nummer
        rechnung.beleg = b
        rechnung.netto, rechnung.ust, rechnung.brutto = (
            Decimal(b["netto"]),
            Decimal(b["ust"]),
            Decimal(b["brutto"]),
        )
        rechnung.datei = relativ.as_posix()
        rechnung.sha256 = hashlib.sha256(inhalt).hexdigest()
        rechnung.status = Rechnung.Status.FESTGESCHRIEBEN
        rechnung.festgeschrieben_am = timezone.now()
        rechnung.save()
        for pfad, daten in dateien.items():
            ziel = Path(settings.DATA_DIR) / pfad
            ziel.parent.mkdir(parents=True, exist_ok=True)
            with ziel.open("xb") as datei:  # niemals überschreiben
                datei.write(daten)
    return rechnung


def stornieren(original, firma):
    """Stornorechnung über den vollen Betrag mit Bezug auf das Original festschreiben."""
    with transaction.atomic():
        storno = original.kopieren(
            storno_zu=original,
            zahlungsziel=0,
            skonto_prozent=0,
            skonto_tage=0,
            girocode=False,
            kopftext=f"{briefanrede(original.kontakt)}\n\n"
            f"die Rechnung {original.nummer} vom {original.datum:%d.%m.%Y} "
            "wird hiermit vollständig storniert.",
            fusstext=grussformel(firma),
        )
        # Negative Mengen statt Preise: EN 16931 erlaubt keinen negativen Einzelpreis (BR-27).
        storno.positionen.update(menge=-F("menge"))
        return festschreiben(storno, firma)


def korrektur_anlegen(original, firma):
    """Entwurf einer Rechnungskorrektur: alle Positionen mit negativer Menge zum Kürzen."""
    with transaction.atomic():
        korrektur = original.kopieren(
            korrektur_zu=original,
            zahlungsziel=0,
            skonto_prozent=0,
            skonto_tage=0,
            girocode=False,
            kopftext=f"{briefanrede(original.kontakt)}\n\n"
            f"die Rechnung {original.nummer} vom {original.datum:%d.%m.%Y} "
            "wird wie folgt korrigiert:",
            fusstext=grussformel(firma),
        )
        korrektur.positionen.update(menge=-F("menge"))
        return korrektur
