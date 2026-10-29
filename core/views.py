from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import redirect, render

from archive.models import Altbeleg
from contacts.models import Kontakt

from .forms import FirmendatenForm
from .models import Firmendaten
from .navigation import PLATZHALTER

KLEINUNTERNEHMER_GRENZE = Decimal("25000.00")


def start(request):
    firma = Firmendaten.laden()
    kontakte = Kontakt.objects.filter(archiviert=False)
    anzahl = kontakte.count()
    # Bis Phase 2 nur aus übernommenen Altbelegen; danach kommen festgeschriebene Rechnungen dazu.
    umsatz = Altbeleg.objects.filter(
        art__in=Altbeleg.UMSATZWIRKSAM, datum__year=date.today().year
    ).aggregate(s=Sum("betrag"))["s"] or Decimal("0.00")
    return render(
        request,
        "core/start.html",
        {
            "bereich": "start",
            "anzahl_kontakte": anzahl,
            "erste_schritte": not (firma.vollstaendig and anzahl),
            "zuletzt": kontakte.order_by("-geaendert")[:5],
            "umsatz": umsatz,
            "grenze": KLEINUNTERNEHMER_GRENZE,
            "grenze_prozent": round(umsatz / KLEINUNTERNEHMER_GRENZE * 100),
            "naechstes_jahr": date.today().year + 1,
        },
    )


def einstellungen(request):
    form = FirmendatenForm(request.POST or None, instance=Firmendaten.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Firmendaten gespeichert.")
        return redirect("core:einstellungen")
    return render(
        request, "core/einstellungen.html", {"bereich": "einstellungen", "form": form}
    )


def platzhalter(request, slug):
    if slug not in PLATZHALTER:
        raise Http404
    titel, inhalt, phase = PLATZHALTER[slug]
    return render(
        request,
        "core/platzhalter.html",
        {"bereich": slug, "titel": titel, "inhalt": inhalt, "phase": phase},
    )
