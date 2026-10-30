from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import redirect, render

from angebote.models import Angebot
from archive.models import Altbeleg
from contacts.models import Kontakt
from invoicing.models import Rechnung
from konten.rechte import nur_inhaber
from zahlungen import mahnen
from zahlungen.models import Mahnstufe

from .forms import FirmendatenForm
from .models import Firmendaten
from .navigation import PLATZHALTER

KLEINUNTERNEHMER_GRENZE = Decimal("25000.00")


def start(request):
    firma = Firmendaten.laden()
    kontakte = Kontakt.objects.filter(archiviert=False)
    anzahl = kontakte.count()
    jahr = date.today().year
    # Übernommene Altbelege plus festgeschriebene Rechnungen aus Kontorfreund (netto).
    umsatz = (
        Altbeleg.objects.filter(
            art__in=Altbeleg.UMSATZWIRKSAM, datum__year=jahr
        ).aggregate(s=Sum("betrag"))["s"]
        or Decimal("0.00")
    ) + (
        Rechnung.objects.filter(
            status=Rechnung.Status.FESTGESCHRIEBEN, datum__year=jahr
        ).aggregate(s=Sum("netto"))["s"]
        or Decimal("0.00")
    )
    offen = [r for r in mahnen.posten() if r.offen > 0]
    ueberfaellig = [r for r in offen if r.ueberfaellig]
    mahnstufe = dict(mahnen.vorschlaege(ueberfaellig, Mahnstufe.alle()))
    for r in ueberfaellig:
        r.mahnstufe = mahnstufe.get(r)
    return render(
        request,
        "core/start.html",
        {
            "bereich": "start",
            "anzahl_kontakte": anzahl,
            "erste_schritte": not (firma.vollstaendig and anzahl),
            "zuletzt": kontakte.order_by("-geaendert")[:5],
            # Offene Posten: Summen in der Seitenleiste, Überfälliges in der Arbeitsliste.
            "posten": bool(offen)
            or Rechnung.objects.filter(status=Rechnung.Status.FESTGESCHRIEBEN).exists(),
            "summe_offen": sum((r.offen for r in offen), Decimal("0.00")),
            "summe_ueberfaellig": sum((r.offen for r in ueberfaellig), Decimal("0.00")),
            "anzahl_offen": len(offen),
            "ueberfaellig": sorted(ueberfaellig, key=lambda r: r.faellig),
            # Fertig, aber noch ohne Antwort; die zuerst ablaufen, stehen oben.
            "offene_angebote": sorted(
                Angebot.objects.filter(
                    status=Angebot.Status.FERTIG, antwort=""
                ).select_related("kontakt"),
                key=lambda a: a.gueltig_bis,
            ),
            "umsatz": umsatz,
            "grenze": KLEINUNTERNEHMER_GRENZE,
            "grenze_prozent": round(umsatz / KLEINUNTERNEHMER_GRENZE * 100),
            "naechstes_jahr": date.today().year + 1,
        },
    )


@nur_inhaber
def einstellungen(request):
    form = FirmendatenForm(
        request.POST or None, request.FILES or None, instance=Firmendaten.laden()
    )
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
