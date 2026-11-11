"""Hilfe: eine kurze Anleitung je Bereich, Vorlage core/hilfe/<slug>.html.

Die Texte beschreiben das Programm, wie es ist. Ändert sich eine Beschriftung oder ein
Ablauf, gehört die passende Anleitung mit in dieselbe Änderung.
"""

THEMEN = [
    {
        "slug": "erste-schritte",
        "titel": "Erste Schritte",
        "kurz": "Starten, einrichten und die erste Rechnung schreiben.",
        "icon": "home",
    },
    {
        "slug": "adressen",
        "titel": "Adressen",
        "kurz": "Kunden, Lieferanten und Ansprechpartner, mit Verlauf und Dateien.",
        "icon": "users",
    },
    {
        "slug": "rechnungen",
        "titel": "Rechnungen",
        "kurz": "Schreiben, festschreiben, senden, stornieren und korrigieren.",
        "icon": "file",
    },
    {
        "slug": "angebote",
        "titel": "Angebote und Auftragsbestätigungen",
        "kurz": "Vom Angebot über den Auftrag zur Rechnung.",
        "icon": "send",
    },
    {
        "slug": "offene-posten",
        "titel": "Zahlungen und Mahnungen",
        "kurz": "Zahlungen buchen, Skonto, Mahnstufen und Verzugszinsen.",
        "icon": "banknote",
    },
    {
        "slug": "artikel",
        "titel": "Artikel",
        "kurz": "Leistungen mit Preis einmal anlegen und in jeden Beleg übernehmen.",
        "icon": "box",
    },
    {
        "slug": "eingangsrechnungen",
        "titel": "Eingangsrechnungen",
        "kurz": "E-Rechnungen Ihrer Lieferanten lesen und aufbewahren.",
        "icon": "inbox",
    },
    {
        "slug": "wiedervorlagen",
        "titel": "Wiedervorlagen",
        "kurz": "Woran Sie denken wollen, mit Erinnerung zur rechten Zeit.",
        "icon": "clock",
    },
    {
        "slug": "ablage",
        "titel": "Ablage und Aufbewahrung",
        "kurz": "Alte Belege, die tägliche Prüfung und die Aufbewahrungsfristen.",
        "icon": "folder",
    },
    {
        "slug": "auswertungen",
        "titel": "Auswertungen",
        "kurz": "Rechnungsausgangsbuch, DATEV-Export und Datenpaket fürs Finanzamt.",
        "icon": "chart",
    },
    {
        "slug": "datensicherung",
        "titel": "Datensicherung",
        "kurz": "Sichern, zweiter Speicherort, wiederherstellen, neuer Rechner.",
        "icon": "database",
    },
    {
        "slug": "einstellungen",
        "titel": "Einstellungen und Benutzer",
        "kurz": "Firmendaten, E-Mail-Versand, Konten, Telegram, mehrere Firmen, Updates.",
        "icon": "settings",
    },
    {
        "slug": "finanzamt-datenschutz",
        "titel": "Finanzamt und Datenschutz",
        "kurz": "Verfahrensdokumentation, Betriebsprüfung, Auskunft und Löschen.",
        "icon": "lock",
    },
]
