"""Bereiche der Seitenleiste in der Reihenfolge klassischer Desktop-Bürosoftware."""

NAVIGATION = [
    {"key": "start", "label": "Übersicht", "icon": "home", "url": "core:start"},
    {"key": "adressen", "label": "Adressen", "icon": "users", "url": "contacts:liste"},
    {
        "key": "rechnungen",
        "label": "Angebote & Rechnungen",
        "icon": "file",
        "url": "invoicing:liste",
    },
    {"key": "artikel", "label": "Artikel", "icon": "box", "url": "artikel:liste"},
    {
        "key": "offene-posten",
        "label": "Offene Posten",
        "icon": "banknote",
        "url": "zahlungen:liste",
    },
    {
        "key": "eingang",
        "label": "Eingangsrechnungen",
        "icon": "inbox",
        "url": "eingang:liste",
    },
    {
        "key": "wiedervorlagen",
        "label": "Wiedervorlagen",
        "icon": "clock",
        "url": "wiedervorlagen:liste",
    },
    {
        "key": "ablage",
        "label": "Ablage",
        "icon": "folder",
        "url": "archive:liste",
        "gruppe": "weitere",
    },
    {
        "key": "auswertungen",
        "label": "Auswertungen",
        "icon": "chart",
        "url": "auswertungen:rechnungsausgangsbuch",
        "gruppe": "weitere",
    },
]

# Bereiche, die noch nicht gebaut sind: (Titel, was kommt, Phase).
PLATZHALTER = {
    "hilfe": (
        "Hilfe",
        "Kurze Anleitungen zu jedem Bereich und Antworten auf häufige Fragen.",
        "Phase 4",
    ),
}
