import re

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import plz
from .forms import KontaktForm
from .models import Kontakt

KATEGORIEN_PLURAL = {
    Kontakt.Kategorie.KUNDE: "Kunden",
    Kontakt.Kategorie.INTERESSENT: "Interessenten",
    Kontakt.Kategorie.LIEFERANT: "Lieferanten",
}


def _nummer(text):
    """„K-0012“ oder „12“ → 12, sonst None."""
    treffer = re.fullmatch(r"(?:K-?)?0*(\d+)", text.strip(), flags=re.IGNORECASE)
    return int(treffer.group(1)) if treffer else None


def liste(request):
    q = request.GET.get("q", "").strip()
    kategorie = request.GET.get("kategorie", "")
    archiv = request.GET.get("archiv") == "1"
    kontakte = Kontakt.objects.filter(archiviert=archiv).annotate(
        anzahl_belege=Count("altbelege", distinct=True),
        anzahl_eingang=Count("eingangsrechnungen", distinct=True),
    )
    if kategorie in Kontakt.Kategorie.values:
        kontakte = kontakte.filter(kategorie=kategorie)
    if q:
        bedingung = (
            Q(anzeigename__icontains=q)
            | Q(vorname__icontains=q)
            | Q(nachname__icontains=q)
            | Q(ort__icontains=q)
            | Q(email__icontains=q)
        )
        if (nummer := _nummer(q)) is not None:
            bedingung |= Q(nummer=nummer)
        kontakte = kontakte.filter(bedingung)
    return render(
        request,
        "contacts/liste.html",
        {
            "bereich": "adressen",
            "kontakte": kontakte,
            "q": q,
            "kategorie": kategorie,
            "kategorien": KATEGORIEN_PLURAL.items(),
            "archiv": archiv,
            "anzahl": Kontakt.objects.filter(archiviert=False).count(),
            "anzahl_archiv": Kontakt.objects.filter(archiviert=True).count(),
            "offen": request.GET.get("offen", ""),
        },
    )


def moegliche_dubletten(kontakt):
    """Gleiche E-Mail-Adresse oder gleicher Name am selben Ort."""
    andere = (
        Kontakt.objects.exclude(pk=kontakt.pk) if kontakt.pk else Kontakt.objects.all()
    )
    bedingung = Q(anzeigename__iexact=kontakt.name_berechnen(), ort__iexact=kontakt.ort)
    if kontakt.email:
        bedingung |= Q(email__iexact=kontakt.email)
    return list(andere.filter(bedingung)[:3])


def bearbeiten(request, pk=None):
    kontakt = get_object_or_404(Kontakt, pk=pk) if pk else None
    form = KontaktForm(request.POST or None, instance=kontakt)
    dubletten = []
    if request.method == "POST" and form.is_valid():
        dubletten = moegliche_dubletten(form.instance)
        if not dubletten or request.POST.get("trotzdem"):
            kontakt = form.save()
            aktion = "gespeichert" if pk else "angelegt"
            messages.success(request, f"Adresse {kontakt.kundennummer} {aktion}.")
            return redirect(f"{reverse('contacts:liste')}?offen={kontakt.pk}")
    return render(
        request,
        "contacts/formular.html",
        {
            "bereich": "adressen",
            "form": form,
            "kontakt": kontakt,
            "dubletten": dubletten,
        },
    )


@require_POST
def archivieren(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    kontakt.archiviert = not kontakt.archiviert
    kontakt.save(update_fields=["archiviert", "geaendert"])
    if kontakt.archiviert:
        messages.success(
            request,
            f"{kontakt} archiviert. Sie finden die Adresse unter „Archiv“.",
        )
    else:
        messages.success(request, f"{kontakt} ist wieder aktiv.")
    return redirect("contacts:liste")


def orte(request):
    """Orte zu einer deutschen PLZ für das Feld „Ort“ (static/js/app.js, data-plz)."""
    alle, eindeutig = plz.orte(request.GET.get("plz", ""))
    return JsonResponse({"orte": alle, "ort": eindeutig})
