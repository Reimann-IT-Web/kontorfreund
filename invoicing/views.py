import logging
import smtplib
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_POST

from archive.models import Altbeleg
from contacts.models import Kontakt
from core.models import Firmendaten

from . import beleg, versand
from .forms import RechnungForm, VersandForm, positionen_lesen
from .models import Rechnung

logger = logging.getLogger(__name__)

EINHEITEN = ["Stück", "Std.", "Tag", "Monat", "Pauschale"]


def liste(request):
    return render(
        request,
        "invoicing/liste.html",
        {
            "bereich": "rechnungen",
            "rechnungen": Rechnung.objects.select_related("kontakt"),
            "altrechnungen": Altbeleg.objects.filter(art=Altbeleg.Art.RECHNUNG).count(),
        },
    )


def neu(request):
    firma = Firmendaten.laden()
    empfaenger = request.GET.get("empfaenger", "")
    kontakt = (
        Kontakt.objects.filter(pk=empfaenger).first() if empfaenger.isdigit() else None
    )
    rechnung = Rechnung(
        kontakt=kontakt,
        steuerfall=Rechnung.Steuerfall.KLEINUNTERNEHMER
        if firma.kleinunternehmer
        else Rechnung.Steuerfall.REGEL,
        kopftext=f"{beleg.briefanrede(kontakt)}\n\n"
        "vielen Dank für Ihren Auftrag. Ich berechne Ihnen folgende Leistungen:",
        fusstext="Mit freundlichen Grüßen\n\n" + (firma.inhaber or firma.name),
    )
    return _editor(request, rechnung, firma)


def bearbeiten(request, pk):
    rechnung = get_object_or_404(Rechnung.objects.select_related("kontakt"), pk=pk)
    firma = Firmendaten.laden()
    if not rechnung.ist_entwurf:
        return _anzeigen(request, rechnung, firma)
    return _editor(request, rechnung, firma)


def _editor(request, rechnung, firma):
    if request.method == "POST":
        form = RechnungForm(request.POST, instance=rechnung)
        positionen, fehler = positionen_lesen(request.POST)
        if form.is_valid() and not fehler:
            with transaction.atomic():
                rechnung = form.save()
                rechnung.positionen.all().delete()
                for position in positionen:
                    position.rechnung = rechnung
                    position.save()
            return _nach_speichern(request, rechnung, firma)
        for meldung in fehler:
            messages.error(request, meldung)
        if form.errors:
            messages.error(request, "Bitte die markierten Angaben prüfen.")
    else:
        form = RechnungForm(instance=rechnung)
        positionen = list(rechnung.positionen.all()) if rechnung.pk else []
    kontakte = list(form.fields["kontakt"].queryset)
    for kontakt in kontakte:
        kontakt.briefanrede = beleg.briefanrede(kontakt)
    return render(
        request,
        "invoicing/rechnung.html",
        {
            "bereich": "rechnungen",
            "rechnung": rechnung,
            "form": form,
            "positionen": positionen,
            "kontakte": kontakte,
            "einheiten": EINHEITEN,
            "naechste_nummer": Rechnung.naechste_nummer(rechnung.datum),
            "vorschau": bool(rechnung.pk and request.GET.get("vorschau")),
        },
    )


def _nach_speichern(request, rechnung, firma):
    hier = reverse("invoicing:bearbeiten", args=[rechnung.pk])
    aktion = request.POST.get("aktion")
    if aktion == "vorschau":
        return redirect(f"{hier}?vorschau=1")
    if aktion != "festschreiben":
        messages.success(request, "Entwurf gespeichert.")
        return redirect(hier)
    fehlt = rechnung.fehlende_angaben(firma)
    if fehlt:
        messages.error(
            request, f"Noch nicht vollständig: {', '.join(fehlt)}. Entwurf gespeichert."
        )
        return redirect(hier)
    try:
        beleg.festschreiben(rechnung, firma)
    except Exception:
        logger.exception("Festschreiben fehlgeschlagen")
        messages.error(
            request,
            "Das PDF konnte nicht erzeugt werden. Der Entwurf ist gespeichert, "
            "es wurde keine Nummer vergeben.",
        )
        return redirect(hier)
    messages.success(
        request,
        f"Rechnung {rechnung.nummer} ist festgeschrieben und als PDF abgelegt.",
    )
    return redirect(hier)


def _anzeigen(request, rechnung, firma):
    form = VersandForm(request.POST or None, initial=versand.vorschlag(rechnung, firma))
    if request.method == "POST" and form.is_valid() and firma.mail_bereit:
        try:
            versand.senden(rechnung, firma, **form.cleaned_data)
        except (smtplib.SMTPException, OSError) as fehler:
            logger.warning("Versand fehlgeschlagen: %s", fehler)
            messages.error(request, versand.fehlertext(fehler))
        else:
            messages.success(
                request,
                f"Rechnung {rechnung.nummer} wurde an {rechnung.versendet_an} gesendet.",
            )
            return redirect("invoicing:bearbeiten", rechnung.pk)
    return render(
        request,
        "invoicing/anzeigen.html",
        {
            "bereich": "rechnungen",
            "rechnung": rechnung,
            "b": rechnung.beleg,
            "firma": firma,
            "form": form,
        },
    )


@require_POST
def loeschen(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk, status=Rechnung.Status.ENTWURF)
    rechnung.delete()
    messages.success(request, "Entwurf gelöscht.")
    return redirect("invoicing:liste")


# Der PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
@xframe_options_sameorigin
def pdf(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    if rechnung.ist_entwurf:
        b = beleg.beleg_daten(rechnung, Firmendaten.laden(), "")
        return HttpResponse(
            beleg.pdf(b, entwurf=True),
            content_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="Rechnung-Entwurf.pdf"'},
        )
    pfad = Path(settings.DATA_DIR) / rechnung.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/pdf",
        filename=f"Rechnung-{rechnung.nummer}.pdf",
        as_attachment="herunterladen" in request.GET,
    )
