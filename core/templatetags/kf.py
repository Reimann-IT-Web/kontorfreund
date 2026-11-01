from datetime import date
from decimal import Decimal

from django import template
from django.utils.html import format_html

register = template.Library()

# Eigene Linien-Symbole, 24er-Raster, Strichstärke kommt aus dem CSS.
_SYMBOLE = {
    "home": "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    "users": "M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20"
    "M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM20 20v-1.5a3.5 3.5 0 0 0-2.6-3.4"
    "M15.5 4.2a3.5 3.5 0 0 1 0 6.6",
    "file": "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h6",
    "box": "M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8",
    "banknote": "M3 6h18v12H3zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM6.5 10v4M17.5 10v4",
    "clock": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
    "building": "M4 21V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v16M15 9h3a2 2 0 0 1 2 2v10"
    "M3 21h18M8 7.5h3M8 11.5h3M8 15.5h3",
    "folder": "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
    "chart": "M4 4v16h16M8 16v-5M12 16V8M16 16v-3",
    "settings": "M4 6h9M17 6h3M15 4v4M4 12h3M11 12h9M9 10v4M4 18h11M19 18h1M17 16v4",
    "help": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3"
    "c-.6.3-1 .8-1 1.5v.7M12 17v.01",
    "search": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
    "plus": "M12 5v14M5 12h14",
    "check": "M5 12.5l4.5 4.5L19 7.5",
    "alert": "M12 3.5 2.5 20h19zM12 10v4.5M12 17.5v.01",
    "x": "M6 6l12 12M18 6 6 18",
    "chevron-down": "M6 9l6 6 6-6",
    "chevron-right": "M9 6l6 6-6 6",
    "phone": "M5 4h3l1.5 4.5-2 1.2a11 11 0 0 0 6.8 6.8l1.2-2L20 16v3a2 2 0 0 1-2 2"
    "A16 16 0 0 1 3 6a2 2 0 0 1 2-2z",
    "mail": "M3 6h18v12H3zM3 7l9 6 9-6",
    "send": "M21 3 10 14M21 3l-7 18-4-7-7-4z",
    "eye": "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "sun": "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4"
    "M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
    "moon": "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
    "menu": "M4 6h16M4 12h16M4 18h16",
    "lock": "M6 11h12v10H6zM8.5 11V7.5a3.5 3.5 0 0 1 7 0V11",
    "upload": "M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
    "download": "M12 4v11M7.5 10.5 12 15l4.5-4.5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
    "user-plus": "M14 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-4A3.5 3.5 0 0 0 3 18.5V20"
    "M8.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM19 8v6M16 11h6",
    "pencil": "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
    "calendar": "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
    "circle": "M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14z",
    "database": "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"
    "M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    "log-out": "M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l4 4-4 4M19 12H9",
    "restore": "M4 12a8 8 0 1 0 2.3-5.7L4 8.5M4 4v4.5h4.5M12 8v4l3 2",
    "list": "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01",
    "inbox": "M3 13h5l1.5 3h5l1.5-3h5M5.5 5h13L21 13v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z",
}


@register.simple_tag
def icon(name, label=""):
    """Inline-SVG; ohne Beschriftung für Screenreader ausgeblendet."""
    if label:
        return format_html(
            '<svg class="icon" viewBox="0 0 24 24" role="img" aria-label="{}"><path d="{}"/></svg>',
            label,
            _SYMBOLE[name],
        )
    return format_html(
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="{}"/></svg>',
        _SYMBOLE[name],
    )


@register.filter
def euro(wert):
    """1234.5 → „1.234,50 €“ (deutsches Format, geschütztes Leerzeichen vor dem Zeichen)."""
    text = f"{Decimal(wert):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{text} €"


@register.filter
def zahl(wert, stellen=None):
    """Zahl im deutschen Format für Eingabefelder: 2.5 → „2,5“, mit Stellen 75 → „75,00“."""
    wert = Decimal(wert)
    text = f"{wert:.{stellen}f}" if stellen is not None else f"{wert.normalize():f}"
    return text.replace(".", ",")


@register.filter
def relativ(tag):
    """Datum relativ zu heute: „heute“, „gestern“, „vor 3 Tagen“, „in 9 Tagen“."""
    tage = (tag - date.today()).days
    if tage == 0:
        return "heute"
    if tage == -1:
        return "gestern"
    if tage == 1:
        return "morgen"
    return f"vor {-tage} Tagen" if tage < 0 else f"in {tage} Tagen"


@register.filter
def tage_seit(tag):
    return (date.today() - tag).days
