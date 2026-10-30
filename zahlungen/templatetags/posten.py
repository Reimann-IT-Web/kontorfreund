"""Zahlungen und Mahnungen auf der Seite einer festgeschriebenen Rechnung."""

from datetime import date

from django import template

from zahlungen import mahnen
from zahlungen.forms import AusbuchenForm, ZahlungForm
from zahlungen.models import Mahnstufe

register = template.Library()


@register.inclusion_tag("zahlungen/rechnung_panel.html", takes_context=True)
def zahlungen_panel(context, rechnung):
    offen = rechnung.offen
    vorschlag = {"betrag": offen} if offen > 0 else {}
    return {
        "rechnung": rechnung,
        "offen": offen,
        "zu_viel": -offen,
        "csrf_token": context.get("csrf_token"),
        "zahlungen": list(rechnung.zahlungen.all()),
        "mahnungen": list(rechnung.mahnungen.all()),
        "naechste": mahnen.naechste_stufe(rechnung, Mahnstufe.alle()),
        "heute": date.today(),
        "form": ZahlungForm(prefix="zahlung", initial=vorschlag),
        "ausbuchen": AusbuchenForm(prefix="ausbuchen", initial=vorschlag),
    }
