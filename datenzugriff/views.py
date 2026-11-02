from datetime import date
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csp import csp_override

from dokumentation.models import Fassung

from . import daten


def _nur_pruefung(view):
    """Prüfer und, zur Vorschau, der Inhaber; Mitarbeiter bekommen 403."""

    @wraps(view)
    def pruefen(request, *args, **kwargs):
        if not (request.user.ist_pruefer or request.user.ist_inhaber):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return pruefen


def _jahre(benutzer):
    if benutzer.ist_pruefer:
        return list(range(benutzer.pruefung_von, benutzer.pruefung_bis + 1))
    return daten.jahre()


def _zeitraum(request):
    """(von, bis, Jahre, gewähltes Jahr); ohne Wahl der ganze Prüfungszeitraum."""
    jahre = _jahre(request.user)
    jahr = request.GET.get("jahr", "")
    if jahr.isdigit() and int(jahr) in jahre:
        jahr = int(jahr)
        return date(jahr, 1, 1), date(jahr, 12, 31), jahre, jahr
    return date(jahre[0], 1, 1), date(jahre[-1], 12, 31), jahre, None


def _kontext(request, **weiteres):
    von, bis, jahre, jahr = _zeitraum(request)
    return {
        "von": von,
        "bis": bis,
        "jahre": jahre,
        "jahr": jahr,
        "zeitraum": str(jahr)
        if jahr
        else f"{jahre[0]} bis {jahre[-1]}"
        if len(jahre) > 1
        else str(jahre[0]),
        **weiteres,
    }


@_nur_pruefung
def start(request):
    k = _kontext(request)
    ansichten, belege = daten.ansichten(k["von"], k["bis"])
    return render(
        request,
        "datenzugriff/start.html",
        k
        | {
            "ansichten": ansichten,
            "belege": len(belege),
            "fassungen": Fassung.objects.filter(art=Fassung.Art.VERFAHREN),
        },
    )


@_nur_pruefung
def tabelle(request, name):
    k = _kontext(request)
    ansichten, _ = daten.ansichten(k["von"], k["bis"])
    ansicht = next((a for a in ansichten if a.name == name), None)
    if not ansicht:
        raise Http404
    t = ansicht.tabelle
    suche = request.GET.get("q", "").strip()
    zeilen = daten.filtern(t.zeilen, t.spalten, suche) if suche else t.zeilen
    sortiert = request.GET.get("sortiert", "")
    spalte = (
        int(sortiert) if sortiert.isdigit() and int(sortiert) < len(t.spalten) else None
    )
    absteigend = request.GET.get("ab") == "1"
    if spalte is not None:
        zeilen = daten.sortieren(zeilen, spalte, absteigend)

    def adresse(i):
        werte = {"jahr": k["jahr"] or "", "q": suche, "sortiert": i}
        if i == spalte and not absteigend:
            werte["ab"] = 1
        return "?" + urlencode({n: w for n, w in werte.items() if w != ""})

    spalten = [
        {
            "name": titel,
            "erklaerung": erklaerung,
            "rechts": art in daten.RECHTS,
            "adresse": adresse(i),
            "sortiert": ("descending" if absteigend else "ascending")
            if i == spalte
            else "",
        }
        for i, (titel, art, erklaerung) in enumerate(t.spalten)
    ]
    return render(
        request,
        "datenzugriff/tabelle.html",
        k
        | {
            "ansicht": ansicht,
            "spalten": spalten,
            "zeilen": _breite(_zellen(z, t.spalten) for z in zeilen),
            "fuss": _zellen(ansicht.fuss, t.spalten)
            if ansicht.fuss and not suche
            else None,
            "anzahl": len(t.zeilen),
            "suche": suche,
        },
    )


def _breite(zeilen):
    """Spalten mit langen Texten dürfen umbrechen, alle übrigen bleiben einzeilig."""
    zeilen = list(zeilen)
    lang = {i for z in zeilen for i, c in enumerate(z) if len(c["text"]) > 40}
    for z in zeilen:
        for i in lang:
            z[i]["lang"] = True
    return zeilen


def _zellen(zeile, spalten):
    zellen = []
    for wert, (titel, art, _) in zip(zeile, spalten, strict=True):
        text = daten.anzeige(wert, art)
        zelle = {"text": text, "rechts": art in daten.RECHTS}
        if titel in daten.DATEIEN and text:
            zelle["datei"] = text
        elif "SHA-256" in titel and text:
            zelle["kurz"] = text[:12] + "…"
        zellen.append(zelle)
    return zellen


# Der PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
@_nur_pruefung
def beleg(request):
    """Eine Belegdatei aus dem Prüfungszeitraum, PDF im Browser, sonst als Download."""
    _, _, jahre, _ = _zeitraum(request)
    pfad = request.GET.get("pfad", "")
    _, belege = daten.ansichten(date(jahre[0], 1, 1), date(jahre[-1], 12, 31))
    datei = Path(settings.DATA_DIR) / pfad
    if pfad not in belege or not datei.is_file():
        raise Http404("Diese Datei gehört nicht zum Prüfungszeitraum oder fehlt.")
    pdf = datei.suffix.lower() == ".pdf"
    return FileResponse(
        datei.open("rb"),
        filename=datei.name,
        as_attachment=not pdf,
        content_type="application/pdf" if pdf else "application/octet-stream",
    )


@csp_override({})
@_nur_pruefung
def dokumentation(request, pk):
    fassung = get_object_or_404(Fassung, pk=pk, art=Fassung.Art.VERFAHREN)
    datei = Path(settings.DATA_DIR) / fassung.datei
    if not datei.is_file():
        raise Http404("Die Datei fehlt in der Ablage.")
    return FileResponse(
        datei.open("rb"), filename=fassung.dateiname, content_type="application/pdf"
    )
