from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from contacts.models import Kontakt
from wiedervorlagen.models import Wiedervorlage

from . import zeitleiste
from .forms import VorgangForm
from .models import Vorgang


def verlauf(request, pk):
    """Seite einer Adresse: Schnellerfassung, offene Wiedervorlagen und Zeitleiste."""
    kontakt = get_object_or_404(Kontakt, pk=pk)
    form = VorgangForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        vorgang = form.save(commit=False)
        vorgang.kontakt = kontakt
        vorgang.benutzer = request.user
        vorgang.save()
        messages.success(request, f"{vorgang.get_art_display()} eingetragen.")
        return redirect("historie:verlauf", kontakt.pk)
    art = request.GET.get("art", "")
    if art not in dict(zeitleiste.ARTEN):
        art = ""
    punkte = zeitleiste.punkte(kontakt)
    return render(
        request,
        "historie/verlauf.html",
        {
            "bereich": "adressen",
            "kontakt": kontakt,
            "form": form,
            "offen": Wiedervorlage.objects.filter(
                kontakt=kontakt, erledigt_am__isnull=True
            ).select_related("zustaendig", "angebot", "rechnung"),
            "punkte": [p for p in punkte if not art or p.art == art],
            "anzahl": len(punkte),
            "art": art,
            "arten": zeitleiste.ARTEN,
            "weiter": request.get_full_path(),
        },
    )


def bearbeiten(request, pk):
    vorgang = get_object_or_404(Vorgang.objects.select_related("kontakt"), pk=pk)
    form = VorgangForm(request.POST or None, instance=vorgang)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{vorgang.get_art_display()} gespeichert.")
        return redirect("historie:verlauf", vorgang.kontakt_id)
    return render(
        request,
        "historie/vorgang.html",
        {"bereich": "adressen", "vorgang": vorgang, "form": form},
    )


@require_POST
def loeschen(request, pk):
    vorgang = get_object_or_404(Vorgang, pk=pk)
    vorgang.delete()
    messages.success(request, f"{vorgang.get_art_display()} gelöscht.")
    return redirect("historie:verlauf", vorgang.kontakt_id)
