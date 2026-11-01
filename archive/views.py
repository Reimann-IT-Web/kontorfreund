from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_POST

from konten.rechte import nur_inhaber

from . import pruefung
from .models import Altbeleg, Pruefung

ARTEN_PLURAL = {
    Altbeleg.Art.RECHNUNG: "Rechnungen",
    Altbeleg.Art.STORNO: "Stornos",
    Altbeleg.Art.GUTSCHRIFT: "Gutschriften",
    Altbeleg.Art.ANGEBOT: "Angebote",
}


def liste(request):
    q = request.GET.get("q", "").strip()
    art = request.GET.get("art", "")
    jahr = request.GET.get("jahr", "")
    kontakt = request.GET.get("kontakt", "")
    belege = Altbeleg.objects.select_related("kontakt")
    if art in Altbeleg.Art.values:
        belege = belege.filter(art=art)
    if jahr.isdigit():
        belege = belege.filter(datum__year=int(jahr))
    if kontakt.isdigit():
        belege = belege.filter(kontakt_id=int(kontakt))
    if q:
        belege = belege.filter(
            Q(nummer__icontains=q) | Q(kontakt__anzeigename__icontains=q) | Q(bezug=q)
        )
    summe = belege.filter(art__in=Altbeleg.UMSATZWIRKSAM).aggregate(s=Sum("betrag"))[
        "s"
    ]
    letzte = Pruefung.letzte()
    return render(
        request,
        "archive/liste.html",
        {
            "bereich": "ablage",
            "belege": belege,
            "q": q,
            "art": art,
            "jahr": jahr,
            "kontakt": kontakt,
            "arten": ARTEN_PLURAL.items(),
            "jahre": [
                d.year for d in Altbeleg.objects.dates("datum", "year", order="DESC")
            ],
            "summe": summe,
            "gesamt": Altbeleg.objects.count(),
            "pruefung": letzte,
            "befunde": [
                dict(b, seit=date.fromisoformat(b["seit"])) for b in letzte.befunde
            ]
            if letzte
            else [],
        },
    )


@require_POST
def pruefen(request):
    ergebnis = pruefung.pruefen()
    if not ergebnis.befunde:
        n = ergebnis.anzahl
        messages.success(
            request, f"Geprüft: keine Abweichung in {n} Datei{'en' if n != 1 else ''}."
        )
    return redirect("archive:liste")


@nur_inhaber
@require_POST
def zurueckholen(request):
    geholt, beiseite, ergebnis = pruefung.zurueckholen()
    if n := len(geholt):
        text = f"{n} Datei{'en' if n != 1 else ''} aus der Datensicherung zurückgeholt."
        if beiseite:
            text += f" Was verändert war, liegt jetzt unter {beiseite}."
        messages.success(request, text)
    if n := len(ergebnis.befunde):
        messages.warning(
            request,
            f"Für {n} Datei{'en' if n != 1 else ''} fand sich in den Sicherungen kein "
            "unverändertes Original. Sicherungen, die mit einem früheren Kennwort "
            "entstanden sind, stellen Sie unter Datensicherung ganz wieder her; was "
            "seitdem eingegeben wurde, geht dabei verloren.",
        )
    return redirect("archive:liste")


# Der eingebaute PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def datei(request, pk):
    beleg = get_object_or_404(Altbeleg, pk=pk)
    pfad = Path(settings.DATA_DIR) / beleg.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/pdf",
        filename=f"{beleg.get_art_display()} {beleg.nummer}.pdf",
    )
