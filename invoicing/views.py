import logging
import smtplib
from datetime import date
from decimal import Decimal
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
from core import umsatz
from core.models import Firmendaten
from core.templatetags.kf import euro
from protokoll.erfassen import positionen_geaendert, positionen_text

from . import beleg, versand
from .forms import RechnungForm, VersandForm, positionen_lesen
from .models import Rechnung

logger = logging.getLogger(__name__)

# Leer heißt „ohne“: Der Beleg zeigt nur die Zahl, die E-Rechnung den Code C62.
EINHEITEN = ["Stück", "Std.", "Tag", "Monat", "Pauschale", ""]


def liste(request):
    return render(
        request,
        "invoicing/liste.html",
        {
            "bereich": "rechnungen",
            "belegart": "rechnungen",
            "rechnungen": Rechnung.objects.select_related(
                "kontakt", "storno_zu", "stornorechnung", "korrektur_zu"
            ).prefetch_related("zahlungen", "korrekturen"),
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
        anschrift=kontakt.anschrift_fuer(Anschrift.Art.RECHNUNG) if kontakt else None,
        lieferanschrift=kontakt.anschrift_fuer(Anschrift.Art.LIEFERUNG)
        if kontakt
        else None,
        # Die Auswahl in den Firmendaten ist zugleich der Steuerfall.
        steuerfall=firma.umsatzsteuer,
        kopftext=f"{beleg.briefanrede(kontakt)}\n\n"
        "vielen Dank für Ihren Auftrag. Ich berechne Ihnen folgende Leistungen:",
        fusstext=beleg.grussformel(firma),
    )
    return _editor(request, rechnung, firma)


def bearbeiten(request, pk):
    rechnung = get_object_or_404(
        Rechnung.objects.select_related(
            "kontakt", "storno_zu", "stornorechnung", "korrektur_zu"
        ),
        pk=pk,
    )
    firma = Firmendaten.laden()
    if not rechnung.ist_entwurf:
        return _anzeigen(request, rechnung, firma)
    return _editor(request, rechnung, firma)


def _editor(request, rechnung, firma):
    if request.method == "POST":
        form = RechnungForm(request.POST, instance=rechnung)
        positionen, fehler = positionen_lesen(
            request.POST, korrektur=rechnung.ist_korrektur
        )
        if form.is_valid() and not fehler:
            vorher = positionen_text(rechnung.positionen.all()) if rechnung.pk else ""
            with transaction.atomic():
                rechnung = form.save()
                rechnung.positionen.all().delete()
                for position in positionen:
                    position.rechnung = rechnung
                    position.save()
                positionen_geaendert(rechnung, vorher)
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
        kontakt.weitere = beleg.anschriften_wahl(kontakt)
    return render(
        request,
        "invoicing/rechnung.html",
        {
            "bereich": "rechnungen",
            "rechnung": rechnung,
            "titel": "Rechnungskorrektur"
            if rechnung.ist_korrektur
            else "Rechnungsentwurf"
            if rechnung.pk
            else "Neue Rechnung",
            "form": form,
            "positionen": positionen,
            "kontakte": kontakte,
            "einheiten": EINHEITEN,
            "artikel": Artikel.objects.filter(aktiv=True),
            "naechste_nummer": Rechnung.naechste_nummer(rechnung.datum),
            "grenz_hinweise": umsatz.hinweise(rechnung.datum.year, _netto(rechnung))
            if _ohne_umsatzsteuer(rechnung)
            else [],
            "vorschau": beleg.seitenbilder(_entwurf_pdf(rechnung, firma))
            if rechnung.pk and request.GET.get("vorschau")
            else [],
        },
    )


def _ohne_umsatzsteuer(rechnung):
    """Rechnung nach § 19, für die die Umsatzgrenzen gelten (nicht die Korrektur)."""
    return (
        rechnung.steuerfall == Rechnung.Steuerfall.KLEINUNTERNEHMER
        and not rechnung.ist_korrektur
    )


def _netto(rechnung):
    return rechnung.summen()[0] if rechnung.pk else Decimal("0.00")


def _nach_speichern(request, rechnung, firma):
    hier = reverse("invoicing:bearbeiten", args=[rechnung.pk])
    aktion = request.POST.get("aktion")
    if aktion == "vorschau":
        return redirect(f"{hier}?vorschau=1")
    if aktion != "festschreiben":
        messages.success(request, "Entwurf gespeichert.")
        return redirect(hier)
    jahr = rechnung.datum.year
    if _ohne_umsatzsteuer(rechnung) and umsatz.ueber_laufender_grenze(
        jahr, _netto(rechnung)
    ):
        # § 19 Abs. 1 UStG: Schon dieser Umsatz unterliegt der Regelbesteuerung.
        messages.error(
            request,
            f"Mit dieser Rechnung läge Ihr Umsatz {jahr} über "
            f"{euro(umsatz.LAUFEND)}. Sie muss deshalb Umsatzsteuer ausweisen: "
            "Stellen Sie unter „Umsatzsteuer“ auf 19 % um. Entwurf gespeichert.",
        )
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
        f"{rechnung.bezeichnung} {rechnung.nummer} ist festgeschrieben und als PDF abgelegt.",
    )
    if _ohne_umsatzsteuer(rechnung):
        for hinweis in umsatz.hinweise(jahr):
            messages.warning(request, hinweis)
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
            "korrekturen": (korrekturen := list(rechnung.korrekturen.all())),
            "teilweise_korrigiert": any(not k.ist_entwurf for k in korrekturen),
            "firma": firma,
            "form": form,
            "seiten": beleg.seitenbilder(pfad.read_bytes())
            if (pfad := Path(settings.DATA_DIR) / rechnung.datei).is_file()
            else [],
            "naechste_nummer": Rechnung.naechste_nummer(date.today()),
        },
    )


@require_POST
def stornieren(request, pk):
    original = get_object_or_404(
        Rechnung,
        pk=pk,
        status=Rechnung.Status.FESTGESCHRIEBEN,
        storno_zu__isnull=True,
        korrektur_zu__isnull=True,
        stornorechnung__isnull=True,
    )
    if original.korrekturen.exclude(status=Rechnung.Status.ENTWURF).exists():
        messages.error(
            request,
            f"Rechnung {original.nummer} ist bereits teilweise korrigiert. "
            "Den Rest mindern Sie mit einer weiteren Rechnungskorrektur.",
        )
        return redirect("invoicing:bearbeiten", original.pk)
    try:
        storno = beleg.stornieren(original, Firmendaten.laden())
    except Exception:
        logger.exception("Stornieren fehlgeschlagen")
        messages.error(
            request,
            "Die Stornorechnung konnte nicht erzeugt werden. Es wurde keine Nummer vergeben.",
        )
        return redirect("invoicing:bearbeiten", original.pk)
    meldung = (
        f"Rechnung {original.nummer} ist storniert (Stornorechnung {storno.nummer})."
    )
    if request.POST.get("kopie"):
        kopie = original.kopieren()
        messages.success(request, f"{meldung} Hier ist eine Kopie zum Korrigieren.")
        return redirect("invoicing:bearbeiten", kopie.pk)
    messages.success(request, meldung)
    return redirect("invoicing:bearbeiten", storno.pk)


@require_POST
def korrigieren(request, pk):
    original = get_object_or_404(Rechnung, pk=pk)
    if not original.korrigierbar:
        raise Http404("Diese Rechnung lässt sich nicht korrigieren.")
    korrektur = beleg.korrektur_anlegen(original, Firmendaten.laden())
    messages.success(
        request,
        f"Entwurf einer Rechnungskorrektur zu Rechnung {original.nummer} angelegt.",
    )
    return redirect("invoicing:bearbeiten", korrektur.pk)


@require_POST
def kopieren(request, pk):
    original = get_object_or_404(
        Rechnung,
        pk=pk,
        status=Rechnung.Status.FESTGESCHRIEBEN,
        storno_zu__isnull=True,
        korrektur_zu__isnull=True,
    )
    kopie = original.kopieren()
    messages.success(request, f"Kopie von Rechnung {original.nummer} angelegt.")
    return redirect("invoicing:bearbeiten", kopie.pk)


@require_POST
def loeschen(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk, status=Rechnung.Status.ENTWURF)
    rechnung.delete()
    messages.success(request, "Entwurf gelöscht.")
    return redirect("invoicing:liste")


def _entwurf_pdf(rechnung, firma):
    b = beleg.beleg_daten(rechnung, firma, "")
    return beleg.pdf(b, entwurf=True, **beleg.druckbilder(firma))


def xml(request, pk):
    rechnung = get_object_or_404(Rechnung.objects.exclude(xml_datei=""), pk=pk)
    pfad = Path(settings.DATA_DIR) / rechnung.xml_datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/xml; charset=utf-8",
        filename=f"{rechnung.bezeichnung}-{rechnung.nummer}.xml",
        as_attachment=True,
    )


# Der PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def pdf(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    if rechnung.ist_entwurf:
        return HttpResponse(
            _entwurf_pdf(rechnung, Firmendaten.laden()),
            content_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="Rechnung-Entwurf.pdf"'},
        )
    pfad = Path(settings.DATA_DIR) / rechnung.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/pdf",
        filename=f"{rechnung.bezeichnung}-{rechnung.nummer}.pdf",
        as_attachment="herunterladen" in request.GET,
    )
