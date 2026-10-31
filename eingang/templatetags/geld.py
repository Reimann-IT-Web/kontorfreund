from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def geld(wert, waehrung="EUR"):
    """Betrag mit Währung wie `euro`; Einzelpreise behalten mehr als zwei Nachkommastellen."""
    if wert is None:
        return ""
    wert = Decimal(wert)
    stellen = max(2, -wert.normalize().as_tuple().exponent)
    text = f"{wert:,.{stellen}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{text} {'€' if waehrung == 'EUR' else waehrung}"


@register.filter
def iban(wert):
    """IBAN in Vierergruppen, wie sie auf Papier steht."""
    wert = wert.replace(" ", "")
    return " ".join(wert[i : i + 4] for i in range(0, len(wert), 4))
