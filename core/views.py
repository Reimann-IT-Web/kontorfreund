from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from angebote.models import Angebot
from contacts.models import Kontakt
from invoicing.models import Rechnung
from konten.rechte import nur_inhaber
from zahlungen import mahnen
from zahlungen.models import Mahnstufe

from . import umsatz as umsaetze
from .forms import FirmendatenForm
from .models import Firmendaten
from .navigation import PLATZHALTER


def start(request):
    firma = Firmendaten.laden()
    kontakte = Kontakt.objects.filter(archiviert=False)
    anzahl = kontakte.count()
    jahr = date.today().year
    umsatz = umsaetze.umsatz(jahr)
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
            "grenze": umsaetze.VORJAHR,
            "grenze_prozent": round(umsatz / umsaetze.VORJAHR * 100),
            "grenz_hinweise": umsaetze.hinweise(jahr) if firma.kleinunternehmer else [],
            "naechstes_jahr": jahr + 1,
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
