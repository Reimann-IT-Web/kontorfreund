"""Felder, Vorlagen und übliche Spaltennamen für den Import (Spezifikation M-6).

Eine Vorlage ordnet jedem Feld die Spaltentitel zu, unter denen ein Programm es
exportiert; es gilt der erste Titel, den die Datei hat. Die Spalten von
Lexware Office stammen aus dessen Hilfe zum Kontaktimport („Tabellenaufbau
Kontakte Import“) und zum Export beim Wechsel des Kontos, die von Google
Kontakte aus dessen CSV-Format. Gespeicherte Zuordnungen des Nutzers sind
Vorlagen mit genau einem Titel je Feld.

`vorschlagen` nimmt die Vorlage, die am besten passt, wenn die Datei mindestens
60 % ihrer Spalten hat, und ergänzt fehlende Felder über die üblichen Namen in
`UEBLICH`. Verglichen wird ohne Groß- und Kleinschreibung und mehrfache
Leerzeichen.
"""

FELDER = {
    "kontakte": [
        ("nummer", "Kundennummer"),
        ("art", "Art (Firma oder Person)"),
        ("kategorie", "Kategorien"),
        ("firmenname", "Firmenname"),
        ("zusatz", "Namenszusatz"),
        ("anrede", "Anrede"),
        ("titel", "Titel"),
        ("vorname", "Vorname"),
        ("nachname", "Nachname"),
        ("position", "Position"),
        ("strasse", "Straße und Hausnummer"),
        ("hausnummer", "Hausnummer, falls eigene Spalte"),
        ("plz", "PLZ"),
        ("ort", "Ort"),
        ("land", "Land"),
        ("email", "E-Mail"),
        ("telefon", "Telefon"),
        ("mobil", "Mobiltelefon"),
        ("fax", "Fax"),
        ("weitere", "Weitere Telefonnummern und E-Mail-Adressen"),
        ("website", "Website"),
        ("ust_id", "USt-IdNr."),
        ("kaeuferreferenz", "Käuferreferenz oder Leitweg-ID"),
        ("xrechnung", "XRechnung"),
        ("notiz", "Notiz"),
    ],
    "artikel": [
        ("nummer", "Artikelnummer"),
        ("bezeichnung", "Bezeichnung"),
        ("beschreibung", "Beschreibung"),
        ("einheit", "Einheit"),
        ("preis", "Einzelpreis netto"),
    ],
}

VORLAGEN = {
    "kontakte": [
        (
            # Adressliste (contacts.views.EXPORT) und Gesamtexport (adressen.csv).
            "Kontorfreund",
            {
                "nummer": ["Kundennummer"],
                "art": ["Art"],
                "kategorie": ["Kategorien", "Kategorie"],
                "firmenname": ["Firmenname", "Name"],
                "zusatz": ["Namenszusatz"],
                "anrede": ["Anrede"],
                "titel": ["Titel"],
                "vorname": ["Vorname"],
                "nachname": ["Nachname"],
                "position": ["Position"],
                "strasse": ["Straße und Hausnummer"],
                "plz": ["PLZ"],
                "ort": ["Ort"],
                "land": ["Land"],
                "email": ["E-Mail"],
                "telefon": ["Telefon"],
                "weitere": ["Weitere Telefonnummern und E-Mail-Adressen"],
                "website": ["Website"],
                "ust_id": ["USt-IdNr."],
                "kaeuferreferenz": ["Käuferreferenz oder Leitweg-ID"],
                "xrechnung": ["XRechnung", "Rechnungen zusätzlich als XRechnung"],
                "notiz": ["Notiz"],
            },
        ),
        (
            "Lexware Office",
            {
                "nummer": ["Kundennummer", "Lieferantennummer"],
                "firmenname": ["Firmenname"],
                "ust_id": ["Umsatzsteuer ID"],
                "anrede": ["Anrede"],
                "vorname": ["Vorname"],
                "nachname": ["Nachname"],
                "notiz": ["Notiz"],
                "strasse": ["Straße (Rechnungsadresse)", "Straße 1"],
                "zusatz": ["Adresszusatz (Rechnungsadresse)"],
                "ort": ["Ort (Rechnungsadresse)", "Ort 1"],
                "plz": ["PLZ (Rechnungsadresse)", "PLZ 1"],
                "land": ["Land (Rechnungsadresse)", "Land 1"],
                "telefon": ["Geschäftlich (Rufnummer)", "Telefon 1"],
                "email": ["Geschäftlich (E-Mail)", "E-Mail 1"],
                "website": ["Website"],
            },
        ),
        (
            "Google Kontakte",
            {
                "firmenname": ["Organization Name", "Organization 1 - Name"],
                "vorname": ["First Name", "Given Name"],
                "nachname": ["Last Name", "Family Name"],
                "email": ["E-mail 1 - Value"],
                "telefon": ["Phone 1 - Value"],
                "strasse": ["Address 1 - Street"],
                "plz": ["Address 1 - Postal Code"],
                "ort": ["Address 1 - City"],
                "land": ["Address 1 - Country"],
                "website": ["Website 1 - Value"],
                "notiz": ["Notes"],
            },
        ),
    ],
    "artikel": [
        (
            # Gesamtexport (artikel.csv).
            "Kontorfreund",
            {
                "nummer": ["Artikelnummer"],
                "bezeichnung": ["Bezeichnung"],
                "beschreibung": ["Beschreibung"],
                "einheit": ["Einheit"],
                "preis": ["Einzelpreis"],
            },
        ),
    ],
}

UEBLICH = {
    "kontakte": {
        "nummer": [
            "Kundennummer",
            "Kunden-Nr.",
            "Kundennr.",
            "Kd.-Nr.",
            "Kdnr",
            "Lieferantennummer",
        ],
        "art": ["Art", "Kontaktart"],
        "kategorie": ["Kategorien", "Kategorie", "Categories"],
        "firmenname": [
            "Firmenname",
            "Firma",
            "Unternehmen",
            "Company",
            "Organisation",
            "Organization",
        ],
        "zusatz": ["Namenszusatz", "Zusatz", "Firmenzusatz", "Adresszusatz"],
        "anrede": ["Anrede", "Salutation"],
        "titel": ["Titel", "Title"],
        "vorname": ["Vorname", "First Name", "Given Name"],
        "nachname": ["Nachname", "Familienname", "Last Name", "Surname", "Family Name"],
        "position": [
            "Position",
            "Funktion",
            "Berufsbezeichnung",
            "Job Title",
            "Organization Title",
            "Organization 1 - Title",
        ],
        "strasse": [
            "Straße",
            "Strasse",
            "Str.",
            "Straße und Hausnummer",
            "Anschrift",
            "Adresse",
            "Street",
            "Straße geschäftlich",
            "Business Street",
        ],
        "hausnummer": ["Hausnummer", "Hausnr.", "Hnr."],
        "plz": [
            "PLZ",
            "Postleitzahl",
            "Postleitzahl geschäftlich",
            "Zip",
            "Postal Code",
            "Business Postal Code",
        ],
        "ort": ["Ort", "Stadt", "Wohnort", "Ort geschäftlich", "City", "Business City"],
        "land": [
            "Land",
            "Land/Region geschäftlich",
            "Country",
            "Business Country/Region",
        ],
        "email": ["E-Mail", "Email", "E-Mail-Adresse", "Mail", "E-mail Address"],
        "telefon": [
            "Telefon",
            "Tel.",
            "Telefonnummer",
            "Rufnummer",
            "Festnetz",
            "Telefon geschäftlich",
            "Phone",
            "Business Phone",
        ],
        "mobil": [
            "Mobil",
            "Mobiltelefon",
            "Mobilnummer",
            "Handy",
            "Handynummer",
            "Mobil (Rufnummer)",
            "Mobile",
            "Mobile Phone",
        ],
        "fax": [
            "Fax",
            "Telefax",
            "Faxnummer",
            "Fax geschäftlich",
            "Fax (Rufnummer)",
            "Business Fax",
        ],
        "website": ["Website", "Webseite", "Homepage", "Internet", "Web Page"],
        "ust_id": [
            "USt-IdNr.",
            "USt-ID",
            "UStIdNr",
            "Umsatzsteuer-ID",
            "Umsatzsteuer-Identifikationsnummer",
            "VAT ID",
        ],
        "kaeuferreferenz": ["Käuferreferenz", "Leitweg-ID"],
        "xrechnung": ["XRechnung"],
        "notiz": [
            "Notiz",
            "Notizen",
            "Bemerkung",
            "Bemerkungen",
            "Anmerkung",
            "Kommentar",
            "Notes",
        ],
    },
    "artikel": {
        "nummer": [
            "Artikelnummer",
            "Artikel-Nr.",
            "Art.-Nr.",
            "Artnr",
            "Produktnummer",
            "SKU",
        ],
        "bezeichnung": [
            "Bezeichnung",
            "Artikelbezeichnung",
            "Artikelname",
            "Artikel",
            "Produkt",
            "Produktname",
            "Leistung",
            "Kurztext",
            "Name",
        ],
        "beschreibung": [
            "Beschreibung",
            "Langtext",
            "Artikelbeschreibung",
            "Description",
        ],
        "einheit": ["Einheit", "Mengeneinheit", "ME", "Unit"],
        "preis": [
            "Einzelpreis",
            "Preis",
            "Nettopreis",
            "Preis netto",
            "Netto",
            "Verkaufspreis",
            "Verkaufspreis netto",
            "VK",
            "VK netto",
            "Price",
            "Net Price",
            "Unit Price",
        ],
    },
}


def normal(titel):
    return " ".join(titel.replace("–", "-").casefold().split())


def anwenden(vorlage, spalten, zuordnung=None):
    """Feld → Spalte für die Felder der Vorlage, deren Spalte die Datei hat.

    Mit `zuordnung` bleibt, was dort steht; ergänzt werden nur die übrigen Felder
    mit noch freien Spalten.
    """
    nach_name = {normal(s): s for s in spalten}
    zuordnung = dict(zuordnung or {})
    for feld, namen in vorlage.items():
        if feld in zuordnung:
            continue
        for name in namen:
            spalte = nach_name.get(normal(name))
            if spalte and spalte not in zuordnung.values():
                zuordnung[feld] = spalte
                break
    return zuordnung


def alle(ziel, gespeichert):
    """(Name, Vorlage) der eingebauten Vorlagen und der gespeicherten Zuordnungen."""
    return VORLAGEN[ziel] + [
        (z.name, {feld: [spalte] for feld, spalte in z.felder.items()})
        for z in gespeichert
    ]


def vorschlagen(ziel, spalten, gespeichert):
    """(Name der passenden Vorlage oder "", Zuordnung Feld → Spalte)."""
    beste, zuordnung, wert = "", {}, (0.6, 2)
    for name, vorlage in alle(ziel, gespeichert):
        treffer = anwenden(vorlage, spalten)
        # Später genannte gewinnen bei Gleichstand: gespeicherte vor eingebauten.
        if (len(treffer) / len(vorlage), len(treffer)) >= wert:
            beste, zuordnung = name, treffer
            wert = (len(treffer) / len(vorlage), len(treffer))
    return beste, anwenden(UEBLICH[ziel], spalten, zuordnung)
