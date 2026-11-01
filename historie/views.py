from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_POST

from contacts.datenschutz import zugriff
from contacts.models import Kontakt
from wiedervorlagen.models import Wiedervorlage

from . import zeitleiste
from .forms import VorgangForm
from .models import VORSCHAU, Datei, Vorgang


def _anzahl(dateien):
    return "1 Datei" if len(dateien) == 1 else f"{len(dateien)} Dateien"


def _ablegen(request, kontakt, vorgang=None):
    """Die hochgeladenen Dateien ablegen; zu große meldet es und lässt sie weg."""
    abgelegt = []
    for hochgeladen in request.FILES.getlist("dateien"):
        if hochgeladen.size > settings.DATEI_MB * 1024 * 1024:
            messages.error(
                request,
                f"{hochgeladen.name}: Die Datei ist größer als {settings.DATEI_MB} MB "
                "und wurde nicht abgelegt.",
            )
            continue
        abgelegt.append(Datei.ablegen(kontakt, hochgeladen, request.user, vorgang))
    Datei.aufraeumen()
    return abgelegt


def _geloescht(request, **bedingung):
    """Die eben gelöschte Datei aus ?geloescht=, damit sie sich zurückholen lässt."""
    pk = request.GET.get("geloescht", "")
    if not pk.isdigit():
        return None
    return Datei.objects.filter(pk=pk, geloescht_am__isnull=False, **bedingung).first()


def verlauf(request, pk):
    """Seite einer Adresse: Schnellerfassung, offene Wiedervorlagen, Dateien und Zeitleiste."""
    kontakt = get_object_or_404(Kontakt, pk=pk)
    zugriff(request, kontakt, aendern=request.method == "POST")
    form = VorgangForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        vorgang = form.save(commit=False)
        vorgang.kontakt = kontakt
        vorgang.benutzer = request.user
        vorgang.save()
        dateien = _ablegen(request, kontakt, vorgang)
        messages.success(
            request,
            f"{vorgang.get_art_display()} eingetragen"
            + (f", mit {_anzahl(dateien)}." if dateien else "."),
        )
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
            "dateien": kontakt.dateien.filter(geloescht_am__isnull=True).select_related(
                "vorgang"
            ),
            "geloescht": _geloescht(request, kontakt=kontakt),
            "datei_mb": settings.DATEI_MB,
            "punkte": [p for p in punkte if not art or p.art == art],
            "anzahl": len(punkte),
            "art": art,
            "arten": zeitleiste.ARTEN,
            "weiter": request.get_full_path(),
        },
    )


def bearbeiten(request, pk):
    vorgang = get_object_or_404(Vorgang.objects.select_related("kontakt"), pk=pk)
    zugriff(request, vorgang.kontakt, aendern=True)
    form = VorgangForm(request.POST or None, instance=vorgang)
    if request.method == "POST" and form.is_valid():
        form.save()
        dateien = _ablegen(request, vorgang.kontakt, vorgang)
        messages.success(
            request,
            f"{vorgang.get_art_display()} gespeichert"
            + (f", {_anzahl(dateien)} angehängt." if dateien else "."),
        )
        return redirect("historie:verlauf", vorgang.kontakt_id)
    return render(
        request,
        "historie/vorgang.html",
        {
            "bereich": "adressen",
            "vorgang": vorgang,
            "form": form,
            "dateien": vorgang.dateien.filter(geloescht_am__isnull=True),
            "geloescht": _geloescht(request, vorgang=vorgang),
            "datei_mb": settings.DATEI_MB,
        },
    )


@require_POST
def loeschen(request, pk):
    vorgang = get_object_or_404(Vorgang, pk=pk)
    zugriff(request, vorgang.kontakt, aendern=True)
    dateien = vorgang.dateien.filter(geloescht_am__isnull=True).exists()
    vorgang.delete()
    messages.success(
        request,
        f"{vorgang.get_art_display()} gelöscht."
        + (" Die angehängten Dateien bleiben bei der Adresse." if dateien else ""),
    )
    return redirect("historie:verlauf", vorgang.kontakt_id)


# ---------- Dateien (Spezifikation K-3) ----------


@require_POST
def hochladen(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    zugriff(request, kontakt, aendern=True)
    dateien = _ablegen(request, kontakt)
    if len(dateien) == 1:
        messages.success(request, f"„{dateien[0]}“ ist abgelegt.")
    elif dateien:
        messages.success(request, f"{_anzahl(dateien)} sind abgelegt.")
    elif not request.FILES:
        messages.error(request, "Bitte wählen Sie eine Datei aus.")
    return redirect(reverse("historie:verlauf", args=[kontakt.pk]) + "#dateien")


# Der eingebaute PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def datei(request, pk):
    """PDF und Bilder zum Ansehen, alles andere nur als Download."""
    datei = get_object_or_404(Datei, pk=pk, geloescht_am__isnull=True)
    zugriff(request, datei.kontakt)
    if not datei.pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    ansehen = datei.vorschau and "herunterladen" not in request.GET
    antwort = FileResponse(
        datei.pfad.open("rb"),
        as_attachment=not ansehen,
        filename=datei.name,
        content_type=VORSCHAU.get(datei.endung, "application/octet-stream"),
    )
    if datei.endung != ".pdf":
        # Zeigt ein Browser doch einmal etwas an, läuft darin nichts (HTML, SVG).
        antwort.headers["Content-Security-Policy"] = "sandbox"
    return antwort


def _zurueck(request, datei):
    """Zur Seite, von der aus gelöscht wurde: Vorgang oder Adresse."""
    if request.POST.get("von") == "vorgang" and datei.vorgang_id:
        return reverse("historie:bearbeiten", args=[datei.vorgang_id])
    return reverse("historie:verlauf", args=[datei.kontakt_id])


@require_POST
def datei_loeschen(request, pk):
    datei = get_object_or_404(Datei, pk=pk, geloescht_am__isnull=True)
    zugriff(request, datei.kontakt, aendern=True)
    datei.geloescht_am = timezone.now()
    datei.save(update_fields=["geloescht_am"])
    Datei.aufraeumen()
    return redirect(f"{_zurueck(request, datei)}?geloescht={datei.pk}#dateien")


@require_POST
def datei_zurueckholen(request, pk):
    datei = get_object_or_404(Datei, pk=pk, geloescht_am__isnull=False)
    zugriff(request, datei.kontakt, aendern=True)
    datei.geloescht_am = None
    datei.save(update_fields=["geloescht_am"])
    messages.success(request, f"„{datei}“ ist wieder da.")
    return redirect(f"{_zurueck(request, datei)}#dateien")
