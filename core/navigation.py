"""Bereiche der Seitenleiste in der Reihenfolge klassischer Desktop-Bürosoftware."""

NAVIGATION = [
    {"key": "start", "label": "Übersicht", "icon": "home", "url": "core:start"},
    {"key": "adressen", "label": "Adressen", "icon": "users", "url": "contacts:liste"},
    {
        "key": "rechnungen",
        "label": "Angebote & Rechnungen",
        "icon": "file",
        "url": "invoicing:neu",
    },
    {"key": "artikel", "label": "Artikel", "icon": "box", "slug": "artikel"},
    {
        "key": "offene-posten",
        "label": "Offene Posten",
        "icon": "banknote",
        "slug": "offene-posten",
    },
    {
        "key": "wiedervorlagen",
        "label": "Wiedervorlagen",
        "icon": "clock",
        "slug": "wiedervorlagen",
    },
    {
        "key": "ablage",
        "label": "Ablage",
        "icon": "folder",
        "slug": "ablage",
        "gruppe": "weitere",
    },
    {
        "key": "auswertungen",
        "label": "Auswertungen",
        "icon": "chart",
        "slug": "auswertungen",
        "gruppe": "weitere",
    },
]

# Bereiche, die noch nicht gebaut sind: (Titel, was kommt, Phase).
PLATZHALTER = {
    "artikel": (
        "Artikel",
        "Artikel und Leistungen mit Einheit, Preis und Steuersatz.",
        "Phase 2",
    ),
    "offene-posten": (
        "Offene Posten",
        "Zahlungseingänge buchen, Mahnungen in drei Stufen, GiroCode.",
        "Phase 3",
    ),
    "wiedervorlagen": (
        "Wiedervorlagen",
        "Erinnerungen mit Fälligkeit, schnell verschieben und erledigen.",
        "Phase 1",
    ),
    "ablage": (
        "Ablage",
        "Dateien je Adresse und Vorgang, mit Vorschau für PDF und Bilder.",
        "Phase 1",
    ),
    "auswertungen": (
        "Auswertungen",
        "Rechnungsausgangsbuch, Umsatz je Kunde, DATEV-Export.",
        "Phase 3",
    ),
    "hilfe": (
        "Hilfe",
        "Kurze Anleitungen zu jedem Bereich und Antworten auf häufige Fragen.",
        "Phase 4",
    ),
}
