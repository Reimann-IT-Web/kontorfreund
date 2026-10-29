"""Rechnung als PDF/A-3 (Typst) mit eingebetteten ZUGFeRD-Daten (Profil EN 16931)."""

import base64
import calendar
import hashlib
import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import typst
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.note import IncludedNote
from drafthorse.models.party import TaxRegistration
from drafthorse.models.payment import PaymentMeans, PaymentTerms
from drafthorse.models.tradelines import LineItem
from drafthorse.pdf import attach_xml
from segno import helpers as qr

from core.templatetags.kf import euro, zahl

from .models import Rechnung

VORLAGE = Path(__file__).parent / "typst" / "rechnung.typ"
SCHRIFTEN = Path(__file__).parent / "schrift"

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


def beleg_daten(rechnung, firma, nummer):
    """Alle Angaben des Belegs. Beim Festschreiben eingefroren, danach nie neu berechnet."""
    netto, ust, brutto = rechnung.summen()
    k = rechnung.kontakt
    o = rechnung.storno_zu
    return {
        "nummer": nummer,
        "storno_zu": {"nummer": o.nummer, "datum": o.datum.isoformat()} if o else None,
        "datum": rechnung.datum.isoformat(),
        "faellig": rechnung.faellig.isoformat(),
        "zahlungsziel": rechnung.zahlungsziel,
        "leistung_von": rechnung.leistung_von.isoformat()
        if rechnung.leistung_von
        else "",
        "leistung_bis": rechnung.leistung_bis.isoformat()
        if rechnung.leistung_bis
        else "",
        "steuerfall": rechnung.steuerfall,
        "steuerhinweis": rechnung.steuerhinweis,
        "referenz": rechnung.referenz,
        "betreff": rechnung.betreff,
        "kopftext": rechnung.kopftext,
        "fusstext": rechnung.fusstext,
        "girocode": bool(rechnung.girocode and firma.iban),
        "absender": {
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
                "iban",
                "bank",
            )
        },
        "empfaenger": {
            "zeilen": k.anschrift_zeilen() if k else [],
            "name": k.anzeigename if k else "",
            "kundennummer": k.kundennummer if k else "",
            "strasse": k.strasse if k else "",
            "plz": k.plz if k else "",
            "ort": k.ort if k else "",
            "land": k.land if k else "",
            "ust_id": k.ust_id if k else "",
        },
        "positionen": [
            {
                "nr": p.nr,
                "bezeichnung": p.bezeichnung,
                "beschreibung": p.beschreibung,
                "menge": str(p.menge),
                "einheit": p.einheit,
                "preis": str(p.preis),
                "gesamt": str(p.gesamt),
            }
            for p in rechnung.positionen.all()
        ],
        "netto": str(netto),
        "ust": str(ust),
        "brutto": str(brutto),
    }


def _absaetze(text):
    return [
        absatz.splitlines() for absatz in text.strip().split("\n\n") if absatz.strip()
    ]


def _girocode(b):
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


def druckdaten(b, entwurf=False, logo=b""):
    """Beleg-Angaben als fertig formatierte Texte für die Typst-Vorlage."""
    a, e, storno = b["absender"], b["empfaenger"], b["storno_zu"]
    info = [("Rechnungsnummer", b["nummer"] or "wird vergeben")]
    info.append(("Rechnungsdatum", datum_de(b["datum"])))
    if storno:
        info.append(("Zur Rechnung", storno["nummer"]))  # Datum steht im Text darunter
    if e["kundennummer"]:
        info.append(("Kundennummer", e["kundennummer"]))
    if b["leistung_von"]:
        info.append(leistungszeit(b["leistung_von"], b["leistung_bis"]))
    if b["referenz"]:
        info.append(("Ihre Referenz", b["referenz"]))

    summen = []
    if b["steuerfall"] == Rechnung.Steuerfall.REGEL:
        summen = [
            ["Nettobetrag", euro(b["netto"])],
            ["Umsatzsteuer 19 %", euro(b["ust"])],
        ]

    iban = " ".join(a["iban"][i : i + 4] for i in range(0, len(a["iban"]), 4))
    zahlung = [
        f"Die Rechnung {storno['nummer']} ist damit nicht mehr zu bezahlen. "
        "Einen bereits gezahlten Betrag erhalten Sie zurück."
        if storno
        else "Zahlbar sofort ohne Abzug."
        if b["zahlungsziel"] == 0
        else f"Zahlbar ohne Abzug bis zum {datum_de(b['faellig'])}."
    ]
    if iban and not storno:
        konto = ", ".join(z for z in (a["bank"], f"IBAN {iban}") if z)
        zahlung.append(f"Bitte überweisen Sie den Betrag auf folgendes Konto: {konto}")
        if b["nummer"]:
            zahlung.append(f"Verwendungszweck: Rechnung {b['nummer']}")

    art = "Stornorechnung" if storno else "Rechnung"
    titel = f"{art} {b['nummer']}" if b["nummer"] else "Rechnung (Entwurf)"
    return {
        "entwurf": entwurf,
        "titel": titel,
        "logo": list(logo) or None,
        "absender_name": a["name"],
        "marke": a["marke"],
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
        "empfaenger": e["zeilen"],
        "info": info,
        "betreff": b["betreff"],
        "kopftext": _absaetze(b["kopftext"]),
        "positionen": [
            {
                "nr": str(p["nr"]),
                "bezeichnung": p["bezeichnung"],
                "beschreibung": p["beschreibung"].splitlines(),
                "menge": f"{zahl(p['menge'])} {p['einheit']}".strip(),
                "preis": euro(p["preis"]),
                "gesamt": euro(p["gesamt"]),
            }
            for p in b["positionen"]
        ],
        "summen": summen,
        "brutto": euro(b["brutto"]),
        "steuerhinweis": b["steuerhinweis"],
        "zahlung": zahlung,
        "girocode": _girocode(b)
        if b["girocode"] and Decimal(b["brutto"]) > 0
        else None,
        "fusstext": _absaetze(b["fusstext"]),
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


def pdf(b, entwurf=False, logo=b"", format="pdf"):
    return typst.compile(
        str(VORLAGE),
        font_paths=[str(SCHRIFTEN)],
        ignore_system_fonts=True,
        sys_inputs={"daten": json.dumps(druckdaten(b, entwurf, logo))},
        format=format,
        **({"pdf_standards": "a-3b"} if format == "pdf" else {"ppi": 110}),
    )


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
    """Rechnungsdaten als CII-XML nach EN 16931; None, wenn das Land unbekannt ist."""
    a, e = b["absender"], b["empfaenger"]
    if e["land"] not in LAND_CODE:
        return None
    kategorie, satz, grund, grund_code = KATEGORIE[b["steuerfall"]]

    doc = Document()
    doc.context.guideline_parameter.id = "urn:cen.eu:en16931:2017"
    doc.header.id = b["nummer"]
    doc.header.type_code = "380"
    doc.header.issue_date_time = date.fromisoformat(b["datum"])
    if b["steuerhinweis"]:
        notiz = IncludedNote()
        notiz.content = b["steuerhinweis"]
        doc.header.notes.add(notiz)

    verkaeufer = doc.trade.agreement.seller
    verkaeufer.name = a["name"]
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
    if e["ust_id"]:
        kaeufer.tax_registrations.add(TaxRegistration(id=("VA", e["ust_id"])))
    if b["referenz"]:
        doc.trade.agreement.buyer_reference = b["referenz"]
    if b["storno_zu"]:
        bezug = doc.trade.settlement.invoice_referenced_document
        bezug.issuer_assigned_id = b["storno_zu"]["nummer"]
        bezug.issue_date_time = date.fromisoformat(b["storno_zu"]["datum"])

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
    # Zahlungsangaben nur, wenn der Kunde etwas zu zahlen hat (nicht beim Storno).
    if Decimal(b["brutto"]) > 0:
        if a["iban"]:
            zahlweg = PaymentMeans()
            zahlweg.type_code = "58"  # SEPA-Überweisung
            zahlweg.payee_account.iban = a["iban"]
            abrechnung.payment_means.add(zahlweg)
        bedingung = PaymentTerms()
        bedingung.due = date.fromisoformat(b["faellig"])
        abrechnung.terms.add(bedingung)

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
    summe.line_total = Decimal(b["netto"])
    summe.tax_basis_total = Decimal(b["netto"])
    summe.tax_total = (Decimal(b["ust"]), "EUR")
    summe.grand_total = Decimal(b["brutto"])
    summe.due_amount = Decimal(b["brutto"])
    return doc.serialize(schema="FACTUR-X_EN16931")


def endgueltiges_pdf(b, logo=b""):
    inhalt = pdf(b, logo=logo)
    xml = zugferd(b)
    return attach_xml(inhalt, xml, lang="de-DE") if xml else inhalt


def festschreiben(rechnung, firma):
    """Nummer vergeben, PDF erzeugen und unveränderbar ablegen."""
    with transaction.atomic():
        nummer = Rechnung.naechste_nummer(rechnung.datum)
        b = beleg_daten(rechnung, firma, nummer)
        inhalt = endgueltiges_pdf(b, bytes(firma.logo))
        relativ = (
            Path("archiv")
            / "rechnungen"
            / str(rechnung.datum.year)
            / f"{rechnung.bezeichnung}-{nummer}.pdf"
        )
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
        ziel = Path(settings.DATA_DIR) / relativ
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with ziel.open("xb") as datei:  # niemals überschreiben
            datei.write(inhalt)
    return rechnung


def stornieren(original, firma):
    """Stornorechnung über den vollen Betrag mit Bezug auf das Original festschreiben."""
    with transaction.atomic():
        storno = original.kopieren(
            storno_zu=original,
            zahlungsziel=0,
            girocode=False,
            kopftext=f"{briefanrede(original.kontakt)}\n\n"
            f"die Rechnung {original.nummer} vom {original.datum:%d.%m.%Y} "
            "wird hiermit vollständig storniert.",
            fusstext=grussformel(firma),
        )
        # Negative Mengen statt Preise: EN 16931 erlaubt keinen negativen Einzelpreis (BR-27).
        storno.positionen.update(menge=-F("menge"))
        return festschreiben(storno, firma)
