import re

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Firmendaten
from invoicing.models import Steuersatz

from .forms import ArtikelForm
from .models import Artikel


def _nummer(text):
    """„A-0012“ oder „12“ → 12, sonst None."""
    treffer = re.fullmatch(r"(?:A-?)?0*(\d+)", text.strip(), flags=re.IGNORECASE)
    return int(treffer.group(1)) if treffer else None


def liste(request):
    q = request.GET.get("q", "").strip()
    inaktiv = request.GET.get("inaktiv") == "1"
    artikel = Artikel.objects.filter(aktiv=not inaktiv)
    if q:
        bedingung = Q(bezeichnung__icontains=q) | Q(beschreibung__icontains=q)
        if (nummer := _nummer(q)) is not None:
            bedingung |= Q(nummer=nummer)
        artikel = artikel.filter(bedingung)
    return render(
        request,
        "artikel/liste.html",
        {
            "bereich": "artikel",
            "artikel": artikel,
            "q": q,
            "inaktiv": inaktiv,
            "anzahl": Artikel.objects.filter(aktiv=True).count(),
            "anzahl_inaktiv": Artikel.objects.filter(aktiv=False).count(),
        },
    )


def bearbeiten(request, pk=None):
    artikel = get_object_or_404(Artikel, pk=pk) if pk else None
    # Den Steuersatz braucht nur, wer Umsatzsteuer ausweist; einen ermäßigten zeigt das
    # Formular immer, damit er sich zurücksetzen lässt.
    mit_steuersatz = (
        Firmendaten.laden().umsatzsteuer == Firmendaten.Umsatzsteuer.REGEL
        or (artikel is not None and artikel.steuersatz != Steuersatz.VOLL)
    )
    form = ArtikelForm(
        request.POST or None, instance=artikel, mit_steuersatz=mit_steuersatz
    )
    if request.method == "POST" and form.is_valid():
        artikel = form.save()
        aktion = "gespeichert" if pk else "angelegt"
        messages.success(request, f"Artikel {artikel.artikelnummer} {aktion}.")
        return redirect("artikel:liste")
    return render(
        request,
        "artikel/formular.html",
        {"bereich": "artikel", "form": form, "artikel": artikel},
    )


@require_POST
def aktiv(request, pk):
    artikel = get_object_or_404(Artikel, pk=pk)
    artikel.aktiv = not artikel.aktiv
    artikel.save(update_fields=["aktiv", "geaendert"])
    if artikel.aktiv:
        messages.success(request, f"{artikel} steht wieder zur Auswahl.")
    else:
        messages.success(
            request,
            f"{artikel} ist inaktiv und erscheint nicht mehr in der Rechnung.",
        )
    return redirect("artikel:liste")
