"""E-Rechnungen lesen: XRechnung (UBL und CII) und ZUGFeRD/Factur-X.

`einlesen` nimmt die hochgeladene Datei (XML oder PDF mit eingebetteter XML) und
liefert Format und XML, `auswerten` macht aus der XML ein Wörterbuch für die
Anzeige mit den Angaben nach EN 16931 (Nummern BT-… in den Kommentaren). Beide
werfen `Unlesbar` mit einem Text für den Nutzer.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from xml.etree import ElementTree
from xml.parsers import expat

from pypdf import PdfReader

from contacts.models import ist_leitweg_id
from core.templatetags.kf import zahl
from invoicing.beleg import EINHEIT_CODE, LAND_CODE


class Unlesbar(ValueError):
    pass


CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
UBL_RECHNUNG = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_GUTSCHRIFT = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
NS = {
    "rsm": CII,
    "ram": "urn:un:unece:uncefact:data:standard:"
    "ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
WURZELN = {
    f"{{{CII}}}CrossIndustryInvoice": "CII",
    f"{{{UBL_RECHNUNG}}}Invoice": "UBL",
    f"{{{UBL_GUTSCHRIFT}}}CreditNote": "UBL",
}
# So heißt die eingebettete XML bei Factur-X, ZUGFeRD 2 und XRechnung im PDF.
ANHANG_NAMEN = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")

# Rechnungsarten (UNTDID 1001), die in Deutschland vorkommen.
ARTEN = {
    "380": "Rechnung",
    "381": "Gutschrift",
    "384": "Rechnungskorrektur",
    "389": "Gutschrift (Abrechnung durch den Empfänger)",
    "326": "Teilrechnung",
    "386": "Vorauszahlungsrechnung",
    "875": "Abschlagsrechnung (Bau)",
    "876": "Teilschlussrechnung (Bau)",
    "877": "Schlussrechnung (Bau)",
    "751": "Rechnungsinformation",
}
# Mengeneinheiten (UN/ECE Recommendation 20 und 21); sonst wird der Code gezeigt.
EINHEITEN = {code: name for name, code in EINHEIT_CODE.items()} | {
    "C62": "Stück",
    "EA": "Stück",
    "XPP": "Stück",
    "SET": "Satz",
    "MIN": "Min.",
    "WEE": "Woche",
    "ANN": "Jahr",
    "KGM": "kg",
    "TNE": "t",
    "MTR": "m",
    "KMT": "km",
    "MTK": "m²",
    "MTQ": "m³",
    "LTR": "l",
    "KWH": "kWh",
    "KWT": "kW",
    "P1": "%",
}
# Zahlungsarten (UNTDID 4461).
ZAHLARTEN = {
    "1": "nicht festgelegt",
    "10": "bar",
    "20": "Scheck",
    "30": "Überweisung",
    "31": "Überweisung",
    "42": "Zahlung auf Bankkonto",
    "48": "Bankkarte",
    "49": "Lastschrift",
    "54": "Kreditkarte",
    "55": "Debitkarte",
    "57": "Dauerauftrag",
    "58": "SEPA-Überweisung",
    "59": "SEPA-Lastschrift",
    "68": "Online-Zahlungsdienst",
    "97": "Verrechnung",
    "ZZZ": "wie vereinbart",
}
# Umsatzsteuer-Kategorien (UNTDID 5305).
STEUERARTEN = {
    "S": "Umsatzsteuer",
    "Z": "Nullsatz",
    "E": "steuerfrei",
    "AE": "Steuerschuldnerschaft des Leistungsempfängers",
    "K": "innergemeinschaftliche Lieferung",
    "G": "Ausfuhrlieferung",
    "O": "nicht steuerbar",
    "L": "Kanarische Inseln",
    "M": "Ceuta und Melilla",
}
LAENDER = {code: name for name, code in LAND_CODE.items() if name}

BEDINGUNG = re.compile(r"#(SKONTO|VERZUG)#TAGE=(\d+)#PROZENT=(-?\d+(?:\.\d+)?)#")


def einlesen(inhalt):
    """(Format „xml“ oder „pdf“, XML) aus der hochgeladenen Datei."""
    if inhalt.startswith(b"%PDF"):
        return "pdf", _aus_pdf(inhalt)
    _wurzel(inhalt)
    return "xml", inhalt


def _aus_pdf(inhalt):
    try:
        anhaenge = PdfReader(BytesIO(inhalt)).attachments
        namen = sorted(anhaenge, key=lambda n: n.lower() not in ANHANG_NAMEN)
        dateien = [d for n in namen if n.lower().endswith(".xml") for d in anhaenge[n]]
    # pypdf meldet beschädigte Dateien mit ganz unterschiedlichen Fehlern.
    except Exception as fehler:
        raise Unlesbar("Die PDF-Datei lässt sich nicht öffnen.") from fehler
    for xml in dateien:
        try:
            _wurzel(xml)
        except Unlesbar:
            continue
        return xml
    raise Unlesbar(
        "Diese PDF-Datei enthält keine E-Rechnung (keine eingebettete XRechnung "
        "oder ZUGFeRD-Daten). Eine reine PDF-Rechnung bewahren Sie bitte wie "
        "bisher auf."
    )


def _ohne_dtd(*_):
    raise Unlesbar("Die XML-Datei enthält eine Dokumenttyp-Definition.")


def _wurzel(xml):
    # Eine E-Rechnung braucht keine Dokumenttyp-Definition; ohne sie gibt es auch
    # keine Entitäten, mit denen eine Datei den Rechner lahmlegen könnte. Der Parser
    # selbst erkennt sie, in jeder Zeichenkodierung, bevor ElementTree sie liest.
    pruefer = expat.ParserCreate()
    pruefer.StartDoctypeDeclHandler = _ohne_dtd
    pruefer.EntityDeclHandler = _ohne_dtd
    try:
        pruefer.Parse(xml, True)
        wurzel = ElementTree.fromstring(xml)  # noqa: S314 – ohne DTD, siehe oben
    except (expat.ExpatError, ElementTree.ParseError) as fehler:
        raise Unlesbar("Die Datei ist weder eine XML- noch eine PDF-Datei.") from fehler
    if wurzel.tag not in WURZELN:
        raise Unlesbar(
            "Die Datei ist keine E-Rechnung im Format XRechnung oder ZUGFeRD 2."
        )
    return wurzel


def _t(el, pfad):
    if el is None:
        return ""
    return (el.findtext(pfad, "", NS) or "").strip()


def _b(el, pfad):
    if not (text := _t(el, pfad)):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise Unlesbar(f"„{text}“ ist kein gültiger Betrag.") from None


def _datum(text):
    """Datum aus „20261031“ (CII, Format 102) oder „2026-10-31“ (UBL)."""
    try:
        if re.fullmatch(r"\d{8}", text):
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        return date.fromisoformat(text) if text else None
    except ValueError:
        raise Unlesbar(f"„{text}“ ist kein gültiges Datum.") from None


def _d(el, pfad):
    """CII-Datum: das Element unter `pfad` enthält den DateTimeString."""
    return _datum(
        _t(el, f"{pfad}/udt:DateTimeString") or _t(el, f"{pfad}/qdt:DateTimeString")
    )


def _einheit(code):
    return EINHEITEN.get(code, code)


def _hinweis(text):
    """Freitext ohne vorangestellten Betreff-Code wie „#ADU#“."""
    return re.sub(r"^#[A-Z]{3}#", "", text).strip()


def _bedingungen(text):
    """Zahlungsbedingungen; Skonto und Verzug im Format der XRechnung als Satz."""
    zeilen = []
    for zeile in text.splitlines():
        if treffer := BEDINGUNG.match(zeile.strip()):
            art, tage, prozent = treffer.groups()
            prozent = Decimal(prozent)
            if art == "VERZUG":
                zeilen.append(f"{zahl(prozent)} % Verzugszinsen nach {tage} Tagen")
            elif prozent:
                zeilen.append(
                    f"{zahl(prozent)} % Skonto bei Zahlung innerhalb von {tage} Tagen"
                )
            else:
                zeilen.append(f"Zahlbar innerhalb von {tage} Tagen ohne Abzug")
        elif zeile.strip():
            zeilen.append(zeile.strip())
    return zeilen


def _profil(kennung, syntax):
    """Lesbarer Name der Spezifikation (BT-24)."""
    k = kennung.lower()
    if "xrechnung" in k:
        version = re.search(r"xrechnung_(\d+\.\d+)", k)
        name = f"XRechnung {version.group(1)}" if version else "XRechnung"
        return f"{name} Extension" if "extension" in k else name
    for endung, name in [
        (":minimum", "ZUGFeRD MINIMUM"),
        (":basicwl", "ZUGFeRD BASIC WL"),
        (":basic", "ZUGFeRD BASIC"),
        (":extended", "ZUGFeRD EXTENDED"),
    ]:
        if k.endswith(endung):
            return name
    if "peppol" in k:
        return "Peppol BIS Billing"
    if k == "urn:cen.eu:en16931:2017":
        return "EN 16931" if syntax == "UBL" else "ZUGFeRD EN 16931"
    return kennung


def auswerten(xml):
    """Alle Angaben der E-Rechnung für die Anzeige."""
    wurzel = _wurzel(xml)
    syntax = WURZELN[wurzel.tag]
    try:
        d = _cii(wurzel) if syntax == "CII" else _ubl(wurzel)
    # Fehlt ein Pflichtteil der Struktur, scheitert der Zugriff darunter.
    except (AttributeError, TypeError):
        raise Unlesbar("Die E-Rechnung ist unvollständig.") from None
    d["syntax"] = syntax
    d["profil"] = _profil(d["spezifikation"], syntax)
    # Diese Profile tragen nur Kopfdaten und gelten nicht als E-Rechnung (§ 14 UStG).
    d["nur_kopfdaten"] = d["profil"] in ("ZUGFeRD MINIMUM", "ZUGFeRD BASIC WL")
    d["art_text"] = ARTEN.get(d["art"], f"Rechnung (Art {d['art']})")
    for partei in (d["verkaeufer"], d["kaeufer"], d["lieferanschrift"]):
        if partei:
            partei["landname"] = LAENDER.get(partei["land"], partei["land"])
    if not d["nummer"] or not d["datum"]:
        raise Unlesbar("In der E-Rechnung fehlen Rechnungsnummer oder -datum.")
    if d["summen"]["brutto"] is None or d["summen"]["zahlbetrag"] is None:
        raise Unlesbar("In der E-Rechnung fehlt der Gesamtbetrag.")
    if referenz := d.pop("kaeuferreferenz"):
        d["angaben"].insert(
            0,
            ("Leitweg-ID" if ist_leitweg_id(referenz) else "Käuferreferenz", referenz),
        )
    d["angaben"] = [(name, wert) for name, wert in d["angaben"] if wert]
    d["anhaenge"] = [_anhang(*a) for a in d["anhaenge"]]
    return d


def _anhang(kennung, beschreibung, uri, datei):
    """Anhang (BG-24): eingebettete Datei als Base64-Text oder Verweis auf eine Adresse."""
    return {
        "kennung": kennung,
        "beschreibung": beschreibung,
        "uri": uri,
        "dateiname": datei.get("filename", "") if datei is not None else "",
        "mime": datei.get("mimeCode", "") if datei is not None else "",
        "base64": "".join((datei.text or "").split()) if datei is not None else "",
    }


def _zu_abschlag(zuschlag, grund, betrag, prozent):
    return {
        "zuschlag": zuschlag == "true",
        "grund": grund or ("Zuschlag" if zuschlag == "true" else "Abschlag"),
        "betrag": betrag,
        "prozent": prozent,
    }


# CII: ZUGFeRD, Factur-X und XRechnung in UN/CEFACT-Syntax


def _partei_cii(p):
    if p is None:
        return None
    a = p.find("ram:PostalTradeAddress", NS)
    steuer = {
        r.get("schemeID"): (r.text or "").strip()
        for r in p.findall("ram:SpecifiedTaxRegistration/ram:ID", NS)
    }
    kontakt = "ram:DefinedTradeContact"
    return {
        "name": _t(p, "ram:Name"),
        "handelsname": _t(p, "ram:SpecifiedLegalOrganization/ram:TradingBusinessName"),
        "zeilen": [
            z
            for z in (
                _t(a, "ram:LineOne"),
                _t(a, "ram:LineTwo"),
                _t(a, "ram:LineThree"),
            )
            if z
        ],
        "plz": _t(a, "ram:PostcodeCode"),
        "ort": _t(a, "ram:CityName"),
        "land": _t(a, "ram:CountryID"),
        "person": _t(p, f"{kontakt}/ram:PersonName"),
        "telefon": _t(
            p, f"{kontakt}/ram:TelephoneUniversalCommunication/ram:CompleteNumber"
        ),
        "email": _t(p, f"{kontakt}/ram:EmailURIUniversalCommunication/ram:URIID"),
        "ust_id": steuer.get("VA", ""),
        "steuernummer": steuer.get("FC", ""),
        "elektronisch": _t(p, "ram:URIUniversalCommunication/ram:URIID"),
    }


def _zu_abschlaege_cii(el):
    return [
        _zu_abschlag(
            _t(z, "ram:ChargeIndicator/udt:Indicator").lower(),
            _t(z, "ram:Reason"),
            _b(z, "ram:ActualAmount"),
            _b(z, "ram:CalculationPercent"),
        )
        for z in el.findall("ram:SpecifiedTradeAllowanceCharge", NS)
    ]


def _cii(w):
    dok = w.find("rsm:ExchangedDocument", NS)
    tx = w.find("rsm:SupplyChainTradeTransaction", NS)
    vereinbarung = tx.find("ram:ApplicableHeaderTradeAgreement", NS)
    lieferung = tx.find("ram:ApplicableHeaderTradeDelivery", NS)
    abrechnung = tx.find("ram:ApplicableHeaderTradeSettlement", NS)
    summe = abrechnung.find("ram:SpecifiedTradeSettlementHeaderMonetarySummation", NS)
    waehrung = _t(abrechnung, "ram:InvoiceCurrencyCode")

    positionen = []
    for z in tx.findall("ram:IncludedSupplyChainTradeLineItem", NS):
        zeile = z.find("ram:AssociatedDocumentLineDocument", NS)
        produkt = z.find("ram:SpecifiedTradeProduct", NS)
        preis = "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice"
        menge = z.find("ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS)
        einzel = z.find("ram:SpecifiedLineTradeSettlement", NS)
        positionen.append(
            {
                "nr": _t(zeile, "ram:LineID"),
                "unter": bool(_t(zeile, "ram:ParentLineID")),
                "name": _t(produkt, "ram:Name"),
                "beschreibung": _t(produkt, "ram:Description"),
                "artikelnummer": _t(produkt, "ram:SellerAssignedID"),
                "notiz": "\n".join(
                    (n.text or "").strip()
                    for n in zeile.findall("ram:IncludedNote/ram:Content", NS)
                ),
                "menge": _b(z, "ram:SpecifiedLineTradeDelivery/ram:BilledQuantity"),
                "einheit": _einheit(
                    menge.get("unitCode", "") if menge is not None else ""
                ),
                "preis": _b(z, f"{preis}/ram:ChargeAmount"),
                "preis_je": _b(z, f"{preis}/ram:BasisQuantity"),
                "netto": _b(
                    einzel,
                    "ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount",
                ),
                "kategorie": _t(einzel, "ram:ApplicableTradeTax/ram:CategoryCode"),
                "satz": _b(einzel, "ram:ApplicableTradeTax/ram:RateApplicablePercent"),
                "von": _d(einzel, "ram:BillingSpecifiedPeriod/ram:StartDateTime"),
                "bis": _d(einzel, "ram:BillingSpecifiedPeriod/ram:EndDateTime"),
                "zu_abschlaege": _zu_abschlaege_cii(einzel),
            }
        )

    wege = [
        {
            "art": ZAHLARTEN.get(c := _t(m, "ram:TypeCode"), c),
            "info": _t(m, "ram:Information"),
            "iban": _t(m, "ram:PayeePartyCreditorFinancialAccount/ram:IBANID")
            or _t(m, "ram:PayeePartyCreditorFinancialAccount/ram:ProprietaryID"),
            "inhaber": _t(m, "ram:PayeePartyCreditorFinancialAccount/ram:AccountName"),
            "bic": _t(m, "ram:PayeeSpecifiedCreditorFinancialInstitution/ram:BICID"),
            "lastschrift_iban": _t(
                m, "ram:PayerPartyDebtorFinancialAccount/ram:IBANID"
            ),
            "karte": _t(m, "ram:ApplicableTradeSettlementFinancialCard/ram:ID"),
        }
        for m in abrechnung.findall("ram:SpecifiedTradeSettlementPaymentMeans", NS)
    ]
    bedingungen = abrechnung.findall("ram:SpecifiedTradePaymentTerms", NS)
    # Die Steuersumme steht ggf. ein zweites Mal in Buchungswährung (BT-111).
    steuer = next(
        (
            _b(s, ".")
            for s in summe.findall("ram:TaxTotalAmount", NS)
            if s.get("currencyID", waehrung) == waehrung
        ),
        None,
    )
    bezug = abrechnung.find("ram:InvoiceReferencedDocument", NS)
    lieferadresse = lieferung.find("ram:ShipToTradeParty", NS)
    return {
        "spezifikation": _t(
            w,
            "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
        ),
        "art": _t(dok, "ram:TypeCode"),
        "nummer": _t(dok, "ram:ID"),
        "datum": _d(dok, "ram:IssueDateTime"),
        "faellig": next(
            (f for b in bedingungen if (f := _d(b, "ram:DueDateDateTime"))),
            None,
        ),
        "waehrung": waehrung,
        "verkaeufer": _partei_cii(vereinbarung.find("ram:SellerTradeParty", NS)),
        "kaeufer": _partei_cii(vereinbarung.find("ram:BuyerTradeParty", NS)),
        "zahlungsempfaenger": _t(abrechnung, "ram:PayeeTradeParty/ram:Name"),
        "lieferanschrift": _partei_cii(lieferadresse),
        "lieferdatum": _d(
            lieferung, "ram:ActualDeliverySupplyChainEvent/ram:OccurrenceDateTime"
        ),
        "zeitraum_von": _d(abrechnung, "ram:BillingSpecifiedPeriod/ram:StartDateTime"),
        "zeitraum_bis": _d(abrechnung, "ram:BillingSpecifiedPeriod/ram:EndDateTime"),
        "kaeuferreferenz": _t(vereinbarung, "ram:BuyerReference"),
        "angaben": [
            (
                "Bestellnummer",
                _t(
                    vereinbarung,
                    "ram:BuyerOrderReferencedDocument/ram:IssuerAssignedID",
                ),
            ),
            (
                "Auftragsnummer",
                _t(
                    vereinbarung,
                    "ram:SellerOrderReferencedDocument/ram:IssuerAssignedID",
                ),
            ),
            (
                "Vertragsnummer",
                _t(vereinbarung, "ram:ContractReferencedDocument/ram:IssuerAssignedID"),
            ),
            (
                "Projekt",
                _t(vereinbarung, "ram:SpecifiedProcuringProject/ram:Name")
                or _t(vereinbarung, "ram:SpecifiedProcuringProject/ram:ID"),
            ),
            (
                "Lieferschein",
                _t(
                    lieferung,
                    "ram:DespatchAdviceReferencedDocument/ram:IssuerAssignedID",
                ),
            ),
            (
                "Bezieht sich auf Rechnung",
                _bezug(
                    _t(bezug, "ram:IssuerAssignedID"),
                    _d(bezug, "ram:FormattedIssueDateTime"),
                ),
            ),
        ],
        "hinweise": [
            _hinweis(n.text or "")
            for n in dok.findall("ram:IncludedNote/ram:Content", NS)
            if (n.text or "").strip()
        ],
        "positionen": positionen,
        "zu_abschlaege": _zu_abschlaege_cii(abrechnung),
        "steuern": [
            {
                "kategorie": _t(s, "ram:CategoryCode"),
                "art": STEUERARTEN.get(k := _t(s, "ram:CategoryCode"), k),
                "satz": _b(s, "ram:RateApplicablePercent"),
                "basis": _b(s, "ram:BasisAmount"),
                "betrag": _b(s, "ram:CalculatedAmount"),
                "grund": _t(s, "ram:ExemptionReason"),
            }
            for s in abrechnung.findall("ram:ApplicableTradeTax", NS)
        ],
        "summen": {
            "positionen": _b(summe, "ram:LineTotalAmount"),
            "zuschlaege": _b(summe, "ram:ChargeTotalAmount"),
            "abschlaege": _b(summe, "ram:AllowanceTotalAmount"),
            "netto": _b(summe, "ram:TaxBasisTotalAmount"),
            "steuer": steuer,
            "brutto": _b(summe, "ram:GrandTotalAmount"),
            "gezahlt": _b(summe, "ram:TotalPrepaidAmount"),
            "rundung": _b(summe, "ram:RoundingAmount"),
            "zahlbetrag": _b(summe, "ram:DuePayableAmount"),
            "dritte": [],
        },
        "zahlung": {
            "wege": wege,
            "verwendungszweck": _t(abrechnung, "ram:PaymentReference"),
            "mandat": next(
                (m for b in bedingungen if (m := _t(b, "ram:DirectDebitMandateID"))), ""
            ),
            "glaeubiger_id": _t(abrechnung, "ram:CreditorReferenceID"),
            "bedingungen": [
                zeile
                for b in bedingungen
                for zeile in _bedingungen(_t(b, "ram:Description"))
            ],
        },
        "anhaenge": [
            (
                _t(a, "ram:IssuerAssignedID"),
                _t(a, "ram:Name"),
                _t(a, "ram:URIID"),
                a.find("ram:AttachmentBinaryObject", NS),
            )
            for a in vereinbarung.findall("ram:AdditionalReferencedDocument", NS)
            if _t(a, "ram:TypeCode") == "916"
        ],
    }


def _bezug(nummer, datum):
    if not nummer:
        return ""
    return f"{nummer} vom {datum:%d.%m.%Y}" if datum else nummer


# UBL: XRechnung und Peppol in OASIS-UBL-Syntax


def _partei_ubl(p):
    if p is None:
        return None
    a = p.find("cac:PostalAddress", NS)
    if a is None:
        a = p.find("cac:Address", NS)
    ust_id = steuernummer = ""
    for s in p.findall("cac:PartyTaxScheme", NS):
        if _t(s, "cac:TaxScheme/cbc:ID") == "VAT":
            ust_id = _t(s, "cbc:CompanyID")
        else:
            steuernummer = _t(s, "cbc:CompanyID")
    name = _t(p, "cac:PartyLegalEntity/cbc:RegistrationName")
    handelsname = _t(p, "cac:PartyName/cbc:Name")
    return {
        "name": name or handelsname,
        "handelsname": handelsname if name and handelsname != name else "",
        "zeilen": [
            z
            for z in (
                _t(a, "cbc:StreetName"),
                _t(a, "cbc:AdditionalStreetName"),
                _t(a, "cac:AddressLine/cbc:Line"),
            )
            if z
        ],
        "plz": _t(a, "cbc:PostalZone"),
        "ort": _t(a, "cbc:CityName"),
        "land": _t(a, "cac:Country/cbc:IdentificationCode"),
        "person": _t(p, "cac:Contact/cbc:Name"),
        "telefon": _t(p, "cac:Contact/cbc:Telephone"),
        "email": _t(p, "cac:Contact/cbc:ElectronicMail"),
        "ust_id": ust_id,
        "steuernummer": steuernummer,
        "elektronisch": _t(p, "cbc:EndpointID"),
    }


def _zu_abschlaege_ubl(el):
    return [
        _zu_abschlag(
            _t(z, "cbc:ChargeIndicator").lower(),
            _t(z, "cbc:AllowanceChargeReason"),
            _b(z, "cbc:Amount"),
            _b(z, "cbc:MultiplierFactorNumeric"),
        )
        for z in el.findall("cac:AllowanceCharge", NS)
    ]


def _zeilen_ubl(el, name, unter=False):
    positionen = []
    for z in el.findall(f"cac:{name}", NS):
        menge = z.find("cbc:InvoicedQuantity", NS)
        if menge is None:
            menge = z.find("cbc:CreditedQuantity", NS)
        artikel = z.find("cac:Item", NS)
        positionen.append(
            {
                "nr": _t(z, "cbc:ID"),
                "unter": unter,
                "name": _t(artikel, "cbc:Name"),
                "beschreibung": _t(artikel, "cbc:Description"),
                "artikelnummer": _t(artikel, "cac:SellersItemIdentification/cbc:ID"),
                "notiz": "\n".join(
                    (n.text or "").strip() for n in z.findall("cbc:Note", NS)
                ),
                "menge": _b(menge, "."),
                "einheit": _einheit(
                    menge.get("unitCode", "") if menge is not None else ""
                ),
                "preis": _b(z, "cac:Price/cbc:PriceAmount"),
                "preis_je": _b(z, "cac:Price/cbc:BaseQuantity"),
                "netto": _b(z, "cbc:LineExtensionAmount"),
                "kategorie": _t(artikel, "cac:ClassifiedTaxCategory/cbc:ID"),
                "satz": _b(artikel, "cac:ClassifiedTaxCategory/cbc:Percent"),
                "von": _datum(_t(z, "cac:InvoicePeriod/cbc:StartDate")),
                "bis": _datum(_t(z, "cac:InvoicePeriod/cbc:EndDate")),
                "zu_abschlaege": _zu_abschlaege_ubl(z),
            }
        )
        # Unterpositionen der XRechnung-Extension stehen direkt unter ihrer Position.
        positionen += _zeilen_ubl(z, "SubInvoiceLine", unter=True)
    return positionen


def _ubl(w):
    gutschrift = w.tag == f"{{{UBL_GUTSCHRIFT}}}CreditNote"
    waehrung = _t(w, "cbc:DocumentCurrencyCode")
    summe = w.find("cac:LegalMonetaryTotal", NS)
    # Die Steuersumme steht ggf. ein zweites Mal in Buchungswährung (BT-111).
    steuern = next(
        (
            s
            for s in w.findall("cac:TaxTotal", NS)
            if s.find("cbc:TaxAmount", NS).get("currencyID", waehrung) == waehrung
        ),
        None,
    )
    wege = w.findall("cac:PaymentMeans", NS)
    lieferung = w.find("cac:Delivery", NS)
    lieferadresse = None
    if (
        lieferung is not None
        and lieferung.find("cac:DeliveryLocation/cac:Address", NS) is not None
    ):
        lieferadresse = _partei_ubl(lieferung.find("cac:DeliveryLocation", NS))
        lieferadresse["name"] = _t(
            lieferung, "cac:DeliveryParty/cac:PartyName/cbc:Name"
        )
    verkaeufer = w.find("cac:AccountingSupplierParty/cac:Party", NS)
    bezug = w.find("cac:BillingReference/cac:InvoiceDocumentReference", NS)
    return {
        "spezifikation": _t(w, "cbc:CustomizationID"),
        "art": _t(w, "cbc:CreditNoteTypeCode" if gutschrift else "cbc:InvoiceTypeCode"),
        "nummer": _t(w, "cbc:ID"),
        "datum": _datum(_t(w, "cbc:IssueDate")),
        "faellig": _datum(
            _t(w, "cbc:DueDate")
            or next((d for m in wege if (d := _t(m, "cbc:PaymentDueDate"))), "")
        ),
        "waehrung": waehrung,
        "verkaeufer": _partei_ubl(verkaeufer),
        "kaeufer": _partei_ubl(w.find("cac:AccountingCustomerParty/cac:Party", NS)),
        "zahlungsempfaenger": _t(w, "cac:PayeeParty/cac:PartyName/cbc:Name"),
        "lieferanschrift": lieferadresse,
        "lieferdatum": _datum(_t(lieferung, "cbc:ActualDeliveryDate")),
        "zeitraum_von": _datum(_t(w, "cac:InvoicePeriod/cbc:StartDate")),
        "zeitraum_bis": _datum(_t(w, "cac:InvoicePeriod/cbc:EndDate")),
        "kaeuferreferenz": _t(w, "cbc:BuyerReference"),
        "angaben": [
            ("Bestellnummer", _t(w, "cac:OrderReference/cbc:ID")),
            ("Auftragsnummer", _t(w, "cac:OrderReference/cbc:SalesOrderID")),
            ("Vertragsnummer", _t(w, "cac:ContractDocumentReference/cbc:ID")),
            ("Projekt", _t(w, "cac:ProjectReference/cbc:ID")),
            ("Lieferschein", _t(w, "cac:DespatchDocumentReference/cbc:ID")),
            (
                "Bezieht sich auf Rechnung",
                _bezug(_t(bezug, "cbc:ID"), _datum(_t(bezug, "cbc:IssueDate"))),
            ),
        ],
        "hinweise": [
            _hinweis(n.text or "")
            for n in w.findall("cbc:Note", NS)
            if (n.text or "").strip()
        ],
        "positionen": _zeilen_ubl(w, "CreditNoteLine" if gutschrift else "InvoiceLine"),
        "zu_abschlaege": _zu_abschlaege_ubl(w),
        "steuern": [
            {
                "kategorie": _t(s, "cac:TaxCategory/cbc:ID"),
                "art": STEUERARTEN.get(k := _t(s, "cac:TaxCategory/cbc:ID"), k),
                "satz": _b(s, "cac:TaxCategory/cbc:Percent"),
                "basis": _b(s, "cbc:TaxableAmount"),
                "betrag": _b(s, "cbc:TaxAmount"),
                "grund": _t(s, "cac:TaxCategory/cbc:TaxExemptionReason"),
            }
            for s in (
                steuern.findall("cac:TaxSubtotal", NS) if steuern is not None else []
            )
        ],
        "summen": {
            "positionen": _b(summe, "cbc:LineExtensionAmount"),
            "zuschlaege": _b(summe, "cbc:ChargeTotalAmount"),
            "abschlaege": _b(summe, "cbc:AllowanceTotalAmount"),
            "netto": _b(summe, "cbc:TaxExclusiveAmount"),
            "steuer": _b(steuern, "cbc:TaxAmount"),
            "brutto": _b(summe, "cbc:TaxInclusiveAmount"),
            "gezahlt": _b(summe, "cbc:PrepaidAmount"),
            "rundung": _b(summe, "cbc:PayableRoundingAmount"),
            "zahlbetrag": _b(summe, "cbc:PayableAmount"),
            # Forderungen Dritter, die mit eingezogen werden (XRechnung-Extension, BG-DEX-09).
            "dritte": [
                {
                    "text": _t(z, "cbc:InstructionID") or _t(z, "cbc:ID"),
                    "betrag": _b(z, "cbc:PaidAmount"),
                }
                for z in w.findall("cac:PrepaidPayment", NS)
            ],
        },
        "zahlung": {
            "wege": [
                {
                    "art": ZAHLARTEN.get(c := _t(m, "cbc:PaymentMeansCode"), c),
                    "info": "",
                    "iban": _t(m, "cac:PayeeFinancialAccount/cbc:ID"),
                    "inhaber": _t(m, "cac:PayeeFinancialAccount/cbc:Name"),
                    "bic": _t(
                        m,
                        "cac:PayeeFinancialAccount/cac:FinancialInstitutionBranch/cbc:ID",
                    ),
                    "lastschrift_iban": _t(
                        m, "cac:PaymentMandate/cac:PayerFinancialAccount/cbc:ID"
                    ),
                    "karte": _t(m, "cac:CardAccount/cbc:PrimaryAccountNumberID"),
                }
                for m in wege
            ],
            "verwendungszweck": next(
                (v for m in wege if (v := _t(m, "cbc:PaymentID"))), ""
            ),
            "mandat": next(
                (v for m in wege if (v := _t(m, "cac:PaymentMandate/cbc:ID"))), ""
            ),
            "glaeubiger_id": next(
                (
                    (i.text or "").strip()
                    for i in w.findall(
                        ".//cac:PartyIdentification/cbc:ID[@schemeID='SEPA']", NS
                    )
                ),
                "",
            ),
            "bedingungen": [
                zeile
                for n in w.findall("cac:PaymentTerms/cbc:Note", NS)
                for zeile in _bedingungen(n.text or "")
            ],
        },
        "anhaenge": [
            (
                _t(a, "cbc:ID"),
                _t(a, "cbc:DocumentDescription"),
                _t(a, "cac:Attachment/cac:ExternalReference/cbc:URI"),
                a.find("cac:Attachment/cbc:EmbeddedDocumentBinaryObject", NS),
            )
            for a in w.findall("cac:AdditionalDocumentReference", NS)
            # Typ 130 ist die Kennung eines Abrechnungsobjekts (BT-18), kein Anhang.
            if _t(a, "cbc:DocumentTypeCode") != "130"
        ],
    }
