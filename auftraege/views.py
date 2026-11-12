import logging
import smtplib
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_POST

from angebote.models import Angebot
from artikel.models import Artikel
from contacts.models import Anschrift, Kontakt
from core.models import Firmendaten
from invoicing import beleg as rechnungsbeleg
from invoicing import versand
from invoicing.forms import VersandForm, datum_auf_heute, positionen_lesen
from invoicing.views import EINHEITEN
from protokoll.erfassen import positionen_geaendert, positionen_text

from . import beleg
from .forms import AuftragForm
from .models import Auftragsbestaetigung, Position

logger = logging.getLogger(__name__)


def liste(request):
    return render(
        request,
        "auftraege/liste.html",
        {
            "bereich": "rechnungen",
            "belegart": "auftraege",
            "auftraege": Auftragsbestaetigung.objects.select_related(
                "kontakt", "rechnung"
            ),
            "naechste_nummer": Auftragsbestaetigung.naechste_nummer(date.today()),
        },
    )


def neu(request):
    firma = Firmendaten.laden()
    empfaenger = request.GET.get("empfaenger", "")
    kontakt = (
        Kontakt.objects.filter(pk=empfaenger).first() if empfaenger.isdigit() else None
    )
    auftrag = Auftragsbestaetigung(
        kontakt=kontakt,
        lieferanschrift=kontakt.anschrift_fuer(Anschrift.Art.LIEFERUNG)
        if kontakt
        else None,
        # Die Auswahl in den Firmendaten ist zugleich der Steuerfall.
        steuerfall=firma.umsatzsteuer,
        kopftext=beleg.kopftext(kontakt),
        fusstext=beleg.fusstext(firma),
    )
    return _editor(request, auftrag, firma)


def bearbeiten(request, pk):
    auftrag = get_object_or_404(
        Auftragsbestaetigung.objects.select_related("kontakt", "angebot", "rechnung"),
        pk=pk,
    )
    firma = Firmendaten.laden()
    if not auftrag.ist_entwurf:
        return _anzeigen(request, auftrag, firma)
    return _editor(request, auftrag, firma)


def _editor(request, auftrag, firma):
    if request.method == "POST":
        form = AuftragForm(request.POST, instance=auftrag)
        positionen, fehler = positionen_lesen(request.POST, modell=Position)
        if form.is_valid() and not fehler:
            vorher = positionen_text(auftrag.positionen.all()) if auftrag.pk else ""
            with transaction.atomic():
                auftrag = form.save()
                auftrag.positionen.all().delete()
                for position in positionen:
                    position.auftrag = auftrag
                    position.save()
                positionen_geaendert(auftrag, vorher)
            return _nach_speichern(request, auftrag, firma)
        for meldung in fehler:
            messages.error(request, meldung)
        if form.errors:
            messages.error(request, "Bitte die markierten Angaben prüfen.")
    else:
        form = AuftragForm(instance=auftrag)
        datum_auf_heute(form)
        positionen = list(auftrag.positionen.all()) if auftrag.pk else []
    kontakte = list(form.fields["kontakt"].queryset)
    for kontakt in kontakte:
        kontakt.briefanrede = rechnungsbeleg.briefanrede(kontakt)
        kontakt.weitere = rechnungsbeleg.anschriften_wahl(kontakt)
    return render(
        request,
        "auftraege/auftrag.html",
        {
            "bereich": "rechnungen",
            "auftrag": auftrag,
            "titel": "Entwurf einer Auftragsbestätigung"
            if auftrag.pk
            else "Neue Auftragsbestätigung",
            "form": form,
            "positionen": positionen,
            "kontakte": kontakte,
            "einheiten": EINHEITEN,
            "artikel": Artikel.objects.filter(aktiv=True),
            "naechste_nummer": Auftragsbestaetigung.naechste_nummer(auftrag.datum),
            "vorschau": rechnungsbeleg.seitenbilder(_entwurf_pdf(auftrag, firma))
            if auftrag.pk and request.GET.get("vorschau")
            else [],
        },
    )


def _nach_speichern(request, auftrag, firma):
    hier = reverse("auftraege:bearbeiten", args=[auftrag.pk])
    aktion = request.POST.get("aktion")
    if aktion == "vorschau":
        return redirect(f"{hier}?vorschau=1")
    if aktion != "fertigstellen":
        messages.success(request, "Entwurf gespeichert.")
        return redirect(hier)
    fehlt = auftrag.fehlende_angaben(firma)
    if fehlt:
        messages.error(
            request, f"Noch nicht vollständig: {', '.join(fehlt)}. Entwurf gespeichert."
        )
        return redirect(hier)
    try:
        beleg.fertigstellen(auftrag, firma)
    except Exception:
        logger.exception("Fertigstellen fehlgeschlagen")
        messages.error(
            request,
            "Das PDF konnte nicht erzeugt werden. Der Entwurf ist gespeichert, "
            "es wurde keine Nummer vergeben.",
        )
        return redirect(hier)
    messages.success(request, f"{auftrag} ist fertiggestellt und als PDF abgelegt.")
    return redirect(hier)


def _anzeigen(request, auftrag, firma):
    form = VersandForm(
        request.POST or None, initial=beleg.mail_vorschlag(auftrag, firma)
    )
    if request.method == "POST" and form.is_valid() and firma.mail_bereit:
        try:
            versand.senden(auftrag, firma, **form.cleaned_data)
        except (smtplib.SMTPException, OSError) as fehler:
            logger.warning("Versand fehlgeschlagen: %s", fehler)
            messages.error(request, versand.fehlertext(fehler))
        else:
            messages.success(
                request, f"{auftrag} wurde an {auftrag.versendet_an} gesendet."
            )
            return redirect("auftraege:bearbeiten", auftrag.pk)
    return render(
        request,
        "auftraege/anzeigen.html",
        {
            "bereich": "rechnungen",
            "auftrag": auftrag,
            "firma": firma,
            "form": form,
            "seiten": rechnungsbeleg.seitenbilder(pfad.read_bytes())
            if (pfad := Path(settings.DATA_DIR) / auftrag.datei).is_file()
            else [],
        },
    )


@require_POST
def aus_angebot(request, pk):
    angebot = get_object_or_404(
        Angebot.objects.select_related("rechnung"), pk=pk, status=Angebot.Status.FERTIG
    )
    vorhanden = Auftragsbestaetigung.objects.filter(angebot=angebot).first()
    if vorhanden:
        return redirect("auftraege:bearbeiten", vorhanden.pk)
    if angebot.rechnung:
        messages.error(
            request,
            "Zu diesem Angebot gibt es schon eine Rechnung, eine Auftragsbestätigung "
            "ist nicht mehr nötig.",
        )
        return redirect("angebote:bearbeiten", angebot.pk)
    if angebot.antwort == Angebot.Antwort.ABGELEHNT:
        messages.error(
            request,
            "Das Angebot ist als abgelehnt vermerkt. Nehmen Sie die Antwort zurück, "
            "wenn der Kunde doch zugesagt hat.",
        )
        return redirect("angebote:bearbeiten", angebot.pk)
    auftrag = beleg.aus_angebot(angebot, Firmendaten.laden())
    messages.success(
        request,
        f"Auftragsbestätigung aus Angebot {angebot.nummer} angelegt. Tragen Sie noch "
        "ein, wann Sie die Leistung ausführen.",
    )
    return redirect("auftraege:bearbeiten", auftrag.pk)


@require_POST
def rechnung_erstellen(request, pk):
    auftrag = get_object_or_404(
        Auftragsbestaetigung.objects.select_related("rechnung"),
        pk=pk,
        status=Auftragsbestaetigung.Status.FERTIG,
    )
    if auftrag.rechnung:
        return redirect("invoicing:bearbeiten", auftrag.rechnung.pk)
    rechnung = beleg.rechnung_erstellen(auftrag, Firmendaten.laden())
    messages.success(request, f"Rechnungsentwurf aus {auftrag} angelegt.")
    return redirect("invoicing:bearbeiten", rechnung.pk)


@require_POST
def kopieren(request, pk):
    original = get_object_or_404(
        Auftragsbestaetigung, pk=pk, status=Auftragsbestaetigung.Status.FERTIG
    )
    kopie = original.kopieren()
    messages.success(request, f"Kopie von {original} angelegt.")
    return redirect("auftraege:bearbeiten", kopie.pk)


@require_POST
def loeschen(request, pk):
    auftrag = get_object_or_404(
        Auftragsbestaetigung, pk=pk, status=Auftragsbestaetigung.Status.ENTWURF
    )
    auftrag.delete()
    messages.success(request, "Entwurf gelöscht.")
    return redirect("auftraege:liste")


def _entwurf_pdf(auftrag, firma):
    b = beleg.beleg_daten(auftrag, firma, "")
    return beleg.pdf(b, entwurf=True, **beleg.druckbilder(firma))


# Der PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def pdf(request, pk):
    auftrag = get_object_or_404(Auftragsbestaetigung, pk=pk)
    if auftrag.ist_entwurf:
        return HttpResponse(
            _entwurf_pdf(auftrag, Firmendaten.laden()),
            content_type="application/pdf",
            headers={
                "Content-Disposition": 'inline; filename="Auftragsbestaetigung-Entwurf.pdf"'
            },
        )
    pfad = Path(settings.DATA_DIR) / auftrag.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/pdf",
        filename=f"Auftragsbestaetigung-{auftrag.nummer}.pdf",
        as_attachment="herunterladen" in request.GET,
    )
