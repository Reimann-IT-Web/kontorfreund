from pathlib import Path

from django.conf import settings
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csp import csp_override

from .models import Altbeleg

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
        },
    )


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
