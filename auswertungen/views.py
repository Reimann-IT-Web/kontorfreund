from datetime import date

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.http import content_disposition_header

from archive.models import Altbeleg
from invoicing.models import Rechnung

from . import buch, tabelle


def rechnungsausgangsbuch(request):
    heute = date.today()
    jahr = request.GET.get("jahr", "")
    jahr = int(jahr) if jahr.isdigit() and 2000 <= int(jahr) <= 2100 else heute.year
    wahl = request.GET.get("zeitraum", "")
    if wahl not in dict(buch.ZEITRAEUME):
        wahl = ""
    von, bis, name, text = buch.zeitraum(jahr, wahl)
    eintraege = buch.zeilen(von, bis)
    zeilen = [z for z, _ in eintraege]

    endung = request.GET.get("format", "")
    if endung in tabelle.TYPEN:
        titel = f"Rechnungsausgangsbuch {name}"
        werte = buch.tabelle(zeilen)
        inhalt = (
            tabelle.csv(buch.SPALTEN, werte)
            if endung == "csv"
            else getattr(tabelle, endung)(buch.SPALTEN, werte, titel)
        )
        return HttpResponse(
            inhalt,
            content_type=tabelle.TYPEN[endung],
            headers={
                "Content-Disposition": content_disposition_header(
                    True, f"{titel}.{endung}"
                )
            },
        )

    jahre = {heute.year}
    jahre |= {
        d.year
        for d in Rechnung.objects.filter(status=Rechnung.Status.FESTGESCHRIEBEN).dates(
            "datum", "year"
        )
    }
    jahre |= {d.year for d in Altbeleg.objects.dates("datum", "year")}
    return render(
        request,
        "auswertungen/rechnungsausgangsbuch.html",
        {
            "bereich": "auswertungen",
            "eintraege": eintraege,
            "summen": buch.summen(zeilen),
            "altbelege": any(z.quelle == "Altprogramm" for z in zeilen),
            "jahr": jahr,
            "jahre": sorted(jahre, reverse=True),
            "wahl": wahl,
            "zeitraeume": buch.ZEITRAEUME,
            "text": text,
            "exporte": [("csv", "CSV"), ("xlsx", "Excel"), ("ods", "LibreOffice")],
        },
    )
