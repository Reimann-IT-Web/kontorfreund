from datetime import date

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import content_disposition_header

from archive.models import Altbeleg
from invoicing.models import Rechnung
from konten.rechte import nur_inhaber

from . import buch, datev, tabelle
from .forms import DatevForm
from .models import Datev


def _auswahl(request):
    """(jahr, wahl) aus der Anfrage; ohne gültige Angabe das laufende Jahr."""
    jahr = request.GET.get("jahr", "")
    jahr = (
        int(jahr) if jahr.isdigit() and 2000 <= int(jahr) <= 2100 else date.today().year
    )
    wahl = request.GET.get("zeitraum", "")
    return jahr, wahl if wahl in dict(buch.ZEITRAEUME) else ""


def _jahre():
    jahre = {date.today().year}
    jahre |= {
        d.year
        for d in Rechnung.objects.filter(status=Rechnung.Status.FESTGESCHRIEBEN).dates(
            "datum", "year"
        )
    }
    jahre |= {d.year for d in Altbeleg.objects.dates("datum", "year")}
    return sorted(jahre, reverse=True)


def _download(inhalt, typ, dateiname):
    return HttpResponse(
        inhalt,
        content_type=typ,
        headers={"Content-Disposition": content_disposition_header(True, dateiname)},
    )


def rechnungsausgangsbuch(request):
    jahr, wahl = _auswahl(request)
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
        return _download(inhalt, tabelle.TYPEN[endung], f"{titel}.{endung}")

    return render(
        request,
        "auswertungen/rechnungsausgangsbuch.html",
        {
            "bereich": "auswertungen",
            "auswertung": "buch",
            "eintraege": eintraege,
            "summen": buch.summen(zeilen),
            "altbelege": any(z.quelle == "Altprogramm" for z in zeilen),
            "jahr": jahr,
            "jahre": _jahre(),
            "wahl": wahl,
            "zeitraeume": buch.ZEITRAEUME,
            "text": text,
            "exporte": [("csv", "CSV"), ("xlsx", "Excel"), ("ods", "LibreOffice")],
        },
    )


def datev_export(request):
    jahr, wahl = _auswahl(request)
    von, bis, name, text = buch.zeitraum(jahr, wahl)
    einstellung = Datev.laden()
    buchungen = datev.buchungen(von, bis, einstellung)

    endung = request.GET.get("format", "")
    if endung in ("csv", "zip") and buchungen and einstellung.bereit:
        dateiname = f"EXTF_Buchungsstapel_{name}.csv"
        inhalt = datev.datei(
            einstellung,
            von,
            bis,
            f"Rechnungsausgang {name}",
            buchungen,
            timezone.localtime(),
        )
        if endung == "zip":
            return _download(
                datev.mit_rechnungen(inhalt, dateiname, buchungen),
                "application/zip",
                f"DATEV {name} mit Rechnungen.zip",
            )
        return _download(inhalt, "text/csv; charset=windows-1252", dateiname)

    return render(
        request,
        "auswertungen/datev.html",
        {
            "bereich": "auswertungen",
            "auswertung": "datev",
            "buchungen": buchungen,
            "einstellung": einstellung,
            "altbelege": Altbeleg.objects.filter(
                art__in=Altbeleg.UMSATZWIRKSAM, datum__range=(von, bis)
            ).count(),
            "jahr": jahr,
            "jahre": _jahre(),
            "wahl": wahl,
            "zeitraeume": buch.ZEITRAEUME,
            "text": text,
        },
    )


@nur_inhaber
def datev_einstellungen(request):
    form = DatevForm(request.POST or None, instance=Datev.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "DATEV-Einstellungen gespeichert.")
        return redirect("auswertungen:datev")
    return render(
        request,
        "auswertungen/datev_einstellungen.html",
        {"bereich": "auswertungen", "form": form},
    )
