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

from archive.models import Altbeleg
from artikel.models import Artikel
from contacts.models import Anschrift, Kontakt
from core.models import Firmendaten
from invoicing import beleg as rechnungsbeleg
from invoicing import versand
from invoicing.forms import VersandForm, positionen_lesen
from invoicing.views import EINHEITEN
from protokoll.erfassen import positionen_geaendert, positionen_text

from . import beleg
from .forms import AngebotForm
from .models import Angebot, Position

logger = logging.getLogger(__name__)


def liste(request):
    return render(
        request,
        "angebote/liste.html",
        {
            "bereich": "rechnungen",
            "belegart": "angebote",
            "angebote": Angebot.objects.select_related(
                "kontakt", "rechnung", "auftrag"
            ),
            "altangebote": Altbeleg.objects.filter(art=Altbeleg.Art.ANGEBOT).count(),
            "naechste_nummer": Angebot.naechste_nummer(date.today()),
        },
    )


def neu(request):
    firma = Firmendaten.laden()
    empfaenger = request.GET.get("empfaenger", "")
    kontakt = (
        Kontakt.objects.filter(pk=empfaenger).first() if empfaenger.isdigit() else None
    )
    angebot = Angebot(
        kontakt=kontakt,
        lieferanschrift=kontakt.anschrift_fuer(Anschrift.Art.LIEFERUNG)
        if kontakt
        else None,
        # Die Auswahl in den Firmendaten ist zugleich der Steuerfall.
        steuerfall=firma.umsatzsteuer,
        kopftext=beleg.kopftext(kontakt),
        fusstext=beleg.fusstext(firma),
    )
    return _editor(request, angebot, firma)


def bearbeiten(request, pk):
    angebot = get_object_or_404(
        Angebot.objects.select_related("kontakt", "rechnung", "auftrag"), pk=pk
    )
    firma = Firmendaten.laden()
    if not angebot.ist_entwurf:
        return _anzeigen(request, angebot, firma)
    return _editor(request, angebot, firma)


def _editor(request, angebot, firma):
    if request.method == "POST":
        form = AngebotForm(request.POST, instance=angebot)
        positionen, fehler = positionen_lesen(request.POST, modell=Position)
        if form.is_valid() and not fehler:
            vorher = positionen_text(angebot.positionen.all()) if angebot.pk else ""
            with transaction.atomic():
                angebot = form.save()
                angebot.positionen.all().delete()
                for position in positionen:
                    position.angebot = angebot
                    position.save()
                positionen_geaendert(angebot, vorher)
            return _nach_speichern(request, angebot, firma)
        for meldung in fehler:
            messages.error(request, meldung)
        if form.errors:
            messages.error(request, "Bitte die markierten Angaben prüfen.")
    else:
        form = AngebotForm(instance=angebot)
        positionen = list(angebot.positionen.all()) if angebot.pk else []
    kontakte = list(form.fields["kontakt"].queryset)
    for kontakt in kontakte:
        kontakt.briefanrede = rechnungsbeleg.briefanrede(kontakt)
        kontakt.weitere = rechnungsbeleg.anschriften_wahl(kontakt)
    return render(
        request,
        "angebote/angebot.html",
        {
            "bereich": "rechnungen",
            "angebot": angebot,
            "titel": "Angebotsentwurf" if angebot.pk else "Neues Angebot",
            "form": form,
            "positionen": positionen,
            "kontakte": kontakte,
            "einheiten": EINHEITEN,
            "artikel": Artikel.objects.filter(aktiv=True),
            "naechste_nummer": Angebot.naechste_nummer(angebot.datum),
            "vorschau": rechnungsbeleg.seitenbilder(_entwurf_pdf(angebot, firma))
            if angebot.pk and request.GET.get("vorschau")
            else [],
        },
    )


def _nach_speichern(request, angebot, firma):
    hier = reverse("angebote:bearbeiten", args=[angebot.pk])
    aktion = request.POST.get("aktion")
    if aktion == "vorschau":
        return redirect(f"{hier}?vorschau=1")
    if aktion != "fertigstellen":
        messages.success(request, "Entwurf gespeichert.")
        return redirect(hier)
    fehlt = angebot.fehlende_angaben(firma)
    if fehlt:
        messages.error(
            request, f"Noch nicht vollständig: {', '.join(fehlt)}. Entwurf gespeichert."
        )
        return redirect(hier)
    try:
        beleg.fertigstellen(angebot, firma)
    except Exception:
        logger.exception("Fertigstellen fehlgeschlagen")
        messages.error(
            request,
            "Das PDF konnte nicht erzeugt werden. Der Entwurf ist gespeichert, "
            "es wurde keine Nummer vergeben.",
        )
        return redirect(hier)
    messages.success(
        request, f"Angebot {angebot.nummer} ist fertiggestellt und als PDF abgelegt."
    )
    return redirect(hier)


def _anzeigen(request, angebot, firma):
    form = VersandForm(
        request.POST or None, initial=beleg.mail_vorschlag(angebot, firma)
    )
    if request.method == "POST" and form.is_valid() and firma.mail_bereit:
        try:
            versand.senden(angebot, firma, **form.cleaned_data)
        except (smtplib.SMTPException, OSError) as fehler:
            logger.warning("Versand fehlgeschlagen: %s", fehler)
            messages.error(request, versand.fehlertext(fehler))
        else:
            messages.success(
                request,
                f"Angebot {angebot.nummer} wurde an {angebot.versendet_an} gesendet.",
            )
            return redirect("angebote:bearbeiten", angebot.pk)
    return render(
        request,
        "angebote/anzeigen.html",
        {
            "bereich": "rechnungen",
            "angebot": angebot,
            "firma": firma,
            "form": form,
            "seiten": rechnungsbeleg.seitenbilder(pfad.read_bytes())
            if (pfad := Path(settings.DATA_DIR) / angebot.datei).is_file()
            else [],
        },
    )


@require_POST
def antwort(request, pk):
    """Antwort des Kunden vermerken oder zurücknehmen."""
    angebot = get_object_or_404(Angebot, pk=pk, status=Angebot.Status.FERTIG)
    wert = request.POST.get("antwort", "")
    if wert not in {"", *Angebot.Antwort.values}:
        raise Http404("Unbekannte Antwort.")
    if angebot.rechnung_id and wert != Angebot.Antwort.ANGENOMMEN:
        messages.error(
            request,
            "Zu diesem Angebot gibt es schon eine Rechnung. Löschen Sie erst den "
            "Rechnungsentwurf, wenn das Angebot doch nicht angenommen wurde.",
        )
        return redirect("angebote:bearbeiten", angebot.pk)
    if hasattr(angebot, "auftrag") and wert != Angebot.Antwort.ANGENOMMEN:
        messages.error(
            request,
            "Zu diesem Angebot gibt es schon eine Auftragsbestätigung. Löschen Sie "
            "erst deren Entwurf, wenn das Angebot doch nicht angenommen wurde.",
        )
        return redirect("angebote:bearbeiten", angebot.pk)
    angebot.antwort = wert
    angebot.antwort_am = date.today() if wert else None
    angebot.save(update_fields=["antwort", "antwort_am", "geaendert"])
    messages.success(
        request,
        f"Angebot {angebot.nummer} ist als {angebot.get_antwort_display().lower()} vermerkt."
        if wert
        else f"Die Antwort zu Angebot {angebot.nummer} ist zurückgenommen.",
    )
    return redirect("angebote:bearbeiten", angebot.pk)


@require_POST
def rechnung_erstellen(request, pk):
    angebot = get_object_or_404(
        Angebot.objects.select_related("rechnung", "auftrag"),
        pk=pk,
        status=Angebot.Status.FERTIG,
    )
    if angebot.rechnung:
        return redirect("invoicing:bearbeiten", angebot.rechnung.pk)
    if hasattr(angebot, "auftrag"):
        # Die Rechnung entsteht dann aus der Auftragsbestätigung.
        return redirect("auftraege:bearbeiten", angebot.auftrag.pk)
    if angebot.antwort == Angebot.Antwort.ABGELEHNT:
        messages.error(
            request,
            "Das Angebot ist als abgelehnt vermerkt. Nehmen Sie die Antwort zurück, "
            "wenn der Kunde doch zugesagt hat.",
        )
        return redirect("angebote:bearbeiten", angebot.pk)
    rechnung = beleg.rechnung_erstellen(angebot, Firmendaten.laden())
    messages.success(
        request, f"Rechnungsentwurf aus Angebot {angebot.nummer} angelegt."
    )
    return redirect("invoicing:bearbeiten", rechnung.pk)


@require_POST
def kopieren(request, pk):
    original = get_object_or_404(Angebot, pk=pk, status=Angebot.Status.FERTIG)
    kopie = original.kopieren()
    messages.success(request, f"Kopie von Angebot {original.nummer} angelegt.")
    return redirect("angebote:bearbeiten", kopie.pk)


@require_POST
def loeschen(request, pk):
    angebot = get_object_or_404(Angebot, pk=pk, status=Angebot.Status.ENTWURF)
    angebot.delete()
    messages.success(request, "Entwurf gelöscht.")
    return redirect("angebote:liste")


def _entwurf_pdf(angebot, firma):
    b = beleg.beleg_daten(angebot, firma, "")
    return beleg.pdf(b, entwurf=True, **beleg.druckbilder(firma))


# Der PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def pdf(request, pk):
    angebot = get_object_or_404(Angebot, pk=pk)
    if angebot.ist_entwurf:
        return HttpResponse(
            _entwurf_pdf(angebot, Firmendaten.laden()),
            content_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="Angebot-Entwurf.pdf"'},
        )
    pfad = Path(settings.DATA_DIR) / angebot.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/pdf",
        filename=f"Angebot-{angebot.nummer}.pdf",
        as_attachment="herunterladen" in request.GET,
    )
