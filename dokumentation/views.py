from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from konten.rechte import nur_inhaber

from . import fassungen
from .forms import DATENSCHUTZ, TEXT, AngabenForm
from .inhalt import MASSNAHMEN
from .models import Angaben, Fassung

ZWECK = {
    Fassung.Art.VERFAHREN: "Danach fragt das Finanzamt bei einer Betriebsprüfung: wie Sie "
    "Rechnungen und andere Belege erstellen, aufbewahren und schützen (GoBD).",
    Fassung.Art.DATENSCHUTZ: "Welche Daten über Personen Sie wofür verarbeiten und wie Sie "
    "sie schützen, mit den Maßnahmen nach Art. 32 DSGVO. Die Datenschutzbehörde kann es "
    "verlangen.",
}


def _datei(fassung):
    pfad = Path(settings.DATA_DIR) / fassung.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt in der Ablage.")
    return FileResponse(
        pfad.open("rb"),
        as_attachment=True,
        filename=fassung.dateiname,
        content_type="application/pdf",
    )


@nur_inhaber
def seite(request):
    """Verfahrensdokumentation und Verzeichnis (Spezifikation D-5) mit den Angaben dazu."""
    form = AngabenForm(request.POST or None, instance=Angaben.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Angaben gespeichert.")
        return redirect("dokumentation:seite")
    dokumente = []
    for art, (_, titel, _, _) in fassungen.DOKUMENTE.items():
        entwurf = fassungen.entwurf(art)
        alle = list(Fassung.objects.filter(art=art).order_by("-nummer"))
        dokumente.append(
            {
                "art": art,
                "titel": titel,
                "zweck": ZWECK[art],
                "offen": fassungen.offen(entwurf),
                "geltend": alle[0] if alle else None,
                "frueher": alle[1:],
                "neu": not alle or alle[0].inhalt != entwurf,
            }
        )
    return render(
        request,
        "dokumentation/seite.html",
        {
            "dokumente": dokumente,
            "form": form,
            "text": [form[f] for f in [*TEXT, "altprogramm"] if f in form.fields],
            "datenschutz": [form[f] for f in DATENSCHUTZ],
            "massnahmen": [form[f] for f in MASSNAHMEN],
        },
    )


@nur_inhaber
@require_POST
def herunterladen(request, art):
    """Die geltende Fassung; hat sich etwas geändert, entsteht dabei eine neue."""
    if art not in Fassung.Art.values:
        raise Http404
    return _datei(fassungen.geltende(art, request.user))


@nur_inhaber
def fassung(request, pk):
    return _datei(get_object_or_404(Fassung, pk=pk))
