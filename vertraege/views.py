"""Verträge für wiederkehrende Rechnungen (Spezifikation B-10)."""

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from artikel.models import Artikel
from core.models import Firmendaten
from core.templatetags.kf import euro
from invoicing.forms import positionen_lesen
from invoicing.models import Rechnung
from invoicing.views import EINHEITEN
from protokoll.erfassen import positionen_geaendert, positionen_text

from . import abrechnen
from .forms import VertragForm
from .models import Position, Vertrag

# Die Positionszeilen heißen wie Felder des Vertrags (bezeichnung), daher ein Präfix.
PRAEFIX = "vertrag"


def liste(request):
    vertraege = Vertrag.objects.select_related("kontakt").prefetch_related("positionen")
    return render(
        request,
        "vertraege/liste.html",
        {"bereich": "rechnungen", "belegart": "vertraege", "vertraege": vertraege},
    )


def neu(request):
    """Neuer Vertrag; mit ?aus_rechnung=<pk> vorbelegt mit Empfänger und Positionen."""
    firma = Firmendaten.laden()
    nr = request.GET.get("aus_rechnung", "")
    vorlage = Rechnung.objects.filter(pk=nr).first() if nr.isdigit() else None
    if vorlage and vorlage.kontakt:
        vertrag = Vertrag(
            kontakt=vorlage.kontakt,
            betreff=vorlage.betreff,
            zahlungsziel=vorlage.zahlungsziel,
            rabatt_prozent=vorlage.rabatt_prozent,
            steuerfall=vorlage.steuerfall,
            beginn=date.today(),
            **abrechnen.vorgaben(vorlage.kontakt, firma),
        )
        positionen = [
            Position(
                nr=p.nr,
                bezeichnung=p.bezeichnung,
                beschreibung=p.beschreibung,
                menge=p.menge,
                einheit=p.einheit,
                preis=p.preis,
            )
            for p in vorlage.positionen.all()
        ]
    else:
        vertrag = Vertrag(
            steuerfall=firma.umsatzsteuer,
            beginn=date.today(),
            **abrechnen.vorgaben(None, firma),
        )
        positionen = []
    return _editor(request, vertrag, positionen)


def bearbeiten(request, pk):
    vertrag = get_object_or_404(Vertrag, pk=pk)
    return _editor(request, vertrag, list(vertrag.positionen.all()))


def _editor(request, vertrag, positionen):
    if request.method == "POST":
        form = VertragForm(request.POST, instance=vertrag, prefix=PRAEFIX)
        positionen, fehler = positionen_lesen(request.POST, modell=Position)
        if not positionen:
            fehler.append("Ein Vertrag braucht mindestens eine Position.")
        elif any(not p.bezeichnung for p in positionen):
            fehler.append("Jede Position braucht eine Bezeichnung.")
        if form.is_valid() and not fehler:
            vorher = positionen_text(vertrag.positionen.all()) if vertrag.pk else ""
            with transaction.atomic():
                vertrag = form.save()
                vertrag.positionen.all().delete()
                for position in positionen:
                    position.vertrag = vertrag
                    position.save()
                positionen_geaendert(vertrag, vorher)
            _gespeichert(request, vertrag)
            return redirect("vertraege:liste")
        for meldung in fehler:
            messages.error(request, meldung)
        if form.errors:
            messages.error(request, "Bitte die markierten Angaben prüfen.")
    else:
        form = VertragForm(instance=vertrag, prefix=PRAEFIX)
    return render(
        request,
        "vertraege/vertrag.html",
        {
            "bereich": "rechnungen",
            "vertrag": vertrag,
            "titel": vertrag.bezeichnung if vertrag.pk else "Neuer Vertrag",
            "form": form,
            "positionen": positionen,
            "einheiten": EINHEITEN,
            "artikel": Artikel.objects.filter(aktiv=True),
        },
    )


def _gespeichert(request, vertrag):
    """Ist ein Zeitraum schon fällig, entsteht sein Entwurf gleich jetzt."""
    neu = [r for r in abrechnen.faellige() if r.vertrag_id == vertrag.pk]
    if not neu:
        messages.success(
            request,
            f"Vertrag „{vertrag}“ gespeichert. Der nächste Rechnungsentwurf entsteht "
            f"am {vertrag.naechster:%d.%m.%Y}."
            if vertrag.laeuft
            else f"Vertrag „{vertrag}“ gespeichert. Er ist beendet.",
        )
        return
    betrag = sum((r.summen()[2] for r in neu), Decimal("0.00"))
    messages.success(
        request,
        f"Vertrag „{vertrag}“ gespeichert. "
        + (
            "Der Rechnungsentwurf liegt"
            if len(neu) == 1
            else f"{len(neu)} Rechnungsentwürfe liegen"
        )
        + f" unter Rechnungen bereit ({euro(betrag)}).",
    )


@require_POST
def loeschen(request, pk):
    vertrag = get_object_or_404(Vertrag, pk=pk)
    name = str(vertrag)
    vertrag.delete()
    messages.success(
        request,
        f"Vertrag „{name}“ gelöscht. Seine Rechnungen und Entwürfe bleiben.",
    )
    return redirect("vertraege:liste")
