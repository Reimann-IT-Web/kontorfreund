"""Seiten der Serienrechnungen (Spezifikation B-11), unter /rechnungen/serien/."""

import logging
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST

from auswertungen import tabelle
from core.models import Firmendaten
from importe.lesen import GROESSTE_DATEI, Unlesbar, lesen

from . import aktionen, texte
from .anlegen import anlegen
from .auswertung import (
    FELDER,
    auswerten,
    erstes_datum,
    kopf_finden,
    vorschlagen,
    wahl_uebernehmen,
)
from .forms import AngabenForm, HochladenForm, VorlageForm, ZuordnungForm
from .models import Liste, Serie, Vorlage

logger = logging.getLogger(__name__)


def _seite(**mehr):
    return {"bereich": "rechnungen", "belegart": "serien", **mehr}


def liste(request):
    serien = Serie.objects.annotate(
        anzahl=Count("teilnehmer"),
        entwuerfe=Count("teilnehmer", filter=Q(teilnehmer__rechnung__status="entwurf")),
        versendet=Count(
            "teilnehmer", filter=Q(teilnehmer__rechnung__versendet_am__isnull=False)
        ),
    )
    return render(
        request,
        "serien/liste.html",
        _seite(
            serien=serien,
            form=HochladenForm(),
            groesste_mb=GROESSTE_DATEI // (1024 * 1024),
        ),
    )


@require_POST
def hochladen(request):
    form = HochladenForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Bitte eine Datei wählen.")
        return redirect("serien:liste")
    datei = form.cleaned_data["datei"]
    if datei.size > GROESSTE_DATEI:
        messages.error(
            request,
            f"Die Datei ist größer als {GROESSTE_DATEI // (1024 * 1024)} MB.",
        )
        return redirect("serien:liste")
    try:
        spalten, zeilen = kopf_finden(*lesen(datei.read()))
    except Unlesbar as fehler:
        messages.error(request, str(fehler))
        return redirect("serien:liste")
    Liste.aufraeumen(request.user)
    neu = Liste.objects.create(
        dateiname=datei.name[-255:],
        spalten=spalten,
        zeilen=zeilen,
        benutzer=request.user,
    )
    return redirect("serien:vorschau", neu.pk)


def _vorgaben(auswertung, vorlage):
    """Angaben zur Serie aus der ersten Teilnehmerzeile und der letzten Serie."""
    erste = auswertung.teilnehmer[0].werte if auswertung.teilnehmer else {}
    termin = erste.get("termin", "")
    return {
        "termin": termin[:100],
        "thema": erste.get("thema", "")[:300],
        "link": erste.get("link", "")[:500],
        "leistungsdatum": erstes_datum(termin),
        "datum": date.today(),
        "preis": vorlage.preis or None,
        "zahlungsziel": vorlage.zahlungsziel,
    }


def vorschau(request, pk):
    liste = get_object_or_404(Liste, pk=pk, benutzer=request.user)
    firma, vorlage = Firmendaten.laden(), Vorlage.laden()
    if request.method == "POST":
        zuordnung_form = ZuordnungForm(request.POST, spalten=liste.spalten)
        angaben = AngabenForm(request.POST)
        zuordnung = (
            zuordnung_form.zuordnung()
            if zuordnung_form.is_valid()
            else {
                f: request.POST.get(f"spalte_{f}")
                for f in FELDER
                if request.POST.get(f"spalte_{f}")
            }
        )
        auswertung = auswerten(
            liste.spalten,
            liste.zeilen,
            zuordnung,
            firma,
            " ".join(request.POST.get("termin", "").split()),
            " ".join(request.POST.get("thema", "").split()),
        )
        wahl_uebernehmen(auswertung, request.POST)
        if request.POST.get("aktion") == "anlegen":
            antwort = _anlegen(
                request, liste, auswertung, angaben, zuordnung_form, vorlage, firma
            )
            if antwort:
                return antwort
    else:
        zuordnung = vorschlagen(liste.spalten, vorlage.zuordnung)
        vorlaeufig = auswerten(liste.spalten, liste.zeilen, zuordnung, firma)
        vorgaben = _vorgaben(vorlaeufig, vorlage)
        auswertung = auswerten(
            liste.spalten,
            liste.zeilen,
            zuordnung,
            firma,
            vorgaben["termin"],
            vorgaben["thema"],
        )
        angaben = AngabenForm(initial=vorgaben)
        zuordnung_form = ZuordnungForm(
            spalten=liste.spalten,
            initial={f"spalte_{f}": t for f, t in zuordnung.items()},
        )
    teilnehmer = auswertung.teilnehmer
    return render(
        request,
        "serien/vorschau.html",
        _seite(
            liste=liste,
            angaben=angaben,
            zuordnung_form=zuordnung_form,
            felder_offen=bool(zuordnung_form.errors) or "name" not in zuordnung,
            auswertung=auswertung,
            teilnehmer=teilnehmer,
            gewaehlt=sum(1 for z in teilnehmer if z.waehlen),
            mit_mandat=sum(1 for z in teilnehmer if z.mandat_datum),
            firma=firma,
            vorlage=vorlage,
            regel=firma.umsatzsteuer == Firmendaten.Umsatzsteuer.REGEL,
        ),
    )


def _anlegen(request, liste, auswertung, angaben, zuordnung_form, vorlage, firma):
    """Entwürfe anlegen; None, wenn die Vorschau mit Meldungen bleibt."""
    if not (angaben.is_valid() and zuordnung_form.is_valid()):
        messages.error(request, "Bitte die markierten Angaben prüfen.")
        return None
    if not any(z.waehlen for z in auswertung.teilnehmer):
        messages.error(request, "Bitte mindestens einen Teilnehmer wählen.")
        return None
    try:
        serie = anlegen(
            liste,
            auswertung,
            angaben.cleaned_data,
            vorlage,
            firma,
            zuordnung_form.zuordnung(),
        )
    except IntegrityError:
        logger.exception("Serie anlegen fehlgeschlagen")
        messages.error(
            request,
            "Eine Kd-Nr. oder Mandatsreferenz wurde inzwischen anderweitig vergeben. "
            "Es wurde nichts angelegt; bitte die Vorschau neu laden.",
        )
        return None
    except ValidationError as fehler:
        messages.error(
            request,
            "Eine Adresse aus der Liste ist unvollständig oder ungültig: "
            f"{' '.join(fehler.messages)} Es wurde nichts angelegt.",
        )
        return None
    anzahl = serie.teilnehmer.count()
    messages.success(
        request,
        f"{anzahl} Rechnungsentw{'urf' if anzahl == 1 else 'ürfe'} angelegt. Prüfen Sie "
        "sie und schreiben Sie sie dann fest.",
    )
    return redirect("serien:serie", serie.pk)


@require_POST
def verwerfen(request, pk):
    Liste.objects.filter(pk=pk, benutzer=request.user).delete()
    messages.success(request, "Die Liste ist verworfen; es wurde nichts angelegt.")
    return redirect("serien:liste")


def serie(request, pk):
    s = get_object_or_404(Serie, pk=pk)
    if (endung := request.GET.get("format")) in tabelle.TYPEN:
        # Übersicht zum Übertragen in die eigene Liste (Schritt 7).
        return tabelle.antwort(
            endung, aktionen.SPALTEN, aktionen.uebersicht(s), f"Serie {s.termin}"[:60]
        )
    teilnehmer = list(
        s.teilnehmer.select_related("rechnung__kontakt").prefetch_related(
            "rechnung__zahlungen", "rechnung__positionen"
        )
    )
    return render(
        request,
        "serien/serie.html",
        _seite(
            serie=s,
            teilnehmer=teilnehmer,
            entwuerfe=sum(1 for t in teilnehmer if t.rechnung.ist_entwurf),
            zu_senden=len(aktionen.zu_senden(s)),
            zum_drucken=len(aktionen.zum_drucken(s)),
            einzuziehen=len(aktionen.einzuziehen(s)),
            firma=Firmendaten.laden(),
            vorlage=Vorlage.laden(),
            exporte=tabelle.links(request),
        ),
    )


def _meldungen(request, fehler):
    for t, grund in fehler:
        messages.error(request, f"Zeile {t.zeile}, {t.name}: {grund}")


@require_POST
def festschreiben(request, pk):
    s = get_object_or_404(Serie, pk=pk)
    nummern, fehler = aktionen.festschreiben(s, Firmendaten.laden())
    if nummern:
        bereich = nummern[0] if len(nummern) == 1 else f"{nummern[0]} bis {nummern[-1]}"
        messages.success(
            request,
            f"{len(nummern)} Rechnung{'' if len(nummern) == 1 else 'en'} "
            f"festgeschrieben ({bereich}).",
        )
    _meldungen(request, fehler)
    return redirect("serien:serie", s.pk)


@require_POST
def senden(request, pk):
    s = get_object_or_404(Serie, pk=pk)
    firma = Firmendaten.laden()
    if not firma.mail_bereit:
        messages.error(request, "Der E-Mail-Versand ist noch nicht eingerichtet.")
        return redirect("serien:serie", s.pk)
    gesendet, fehler = aktionen.senden(
        s, firma, Vorlage.laden(), bool(request.POST.get("kopie"))
    )
    if gesendet:
        messages.success(
            request,
            f"{len(gesendet)} Rechnung{'' if len(gesendet) == 1 else 'en'} per E-Mail "
            "gesendet.",
        )
    _meldungen(request, fehler)
    return redirect("serien:serie", s.pk)


def drucken(request, pk):
    s = get_object_or_404(Serie, pk=pk)
    if not aktionen.zum_drucken(s):
        messages.error(request, "Es gibt keine festgeschriebene Rechnung ohne E-Mail.")
        return redirect("serien:serie", s.pk)
    return HttpResponse(
        aktionen.druck_pdf(s, Vorlage.laden()),
        content_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition_header(
                True, f"Serie-{s.leistungsdatum:%Y-%m-%d}-Druck.pdf"
            )
        },
    )


@require_POST
def eingezogen(request, pk):
    s = get_object_or_404(Serie, pk=pk)
    gebucht = aktionen.eingezogen(s)
    if gebucht:
        messages.success(
            request,
            f"{len(gebucht)} Lastschrift{'' if len(gebucht) == 1 else 'en'} als "
            "eingezogen gebucht.",
        )
    else:
        messages.error(request, "Es ist keine Lastschrift zu buchen.")
    return redirect("serien:serie", s.pk)


def vorlage(request):
    v = Vorlage.laden()
    form = VorlageForm(request.POST or None, request.FILES or None, instance=v)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Vorlage gespeichert.")
        return redirect("serien:vorlage")
    return render(
        request,
        "serien/vorlage.html",
        _seite(
            form=form,
            vorlage=v,
            platzhalter_rechnung=texte.liste(texte.RECHNUNG),
            platzhalter_mail=texte.liste(texte.MAIL),
        ),
    )


def beilage(request):
    v = Vorlage.laden()
    if not v.beilage:
        return redirect("serien:vorlage")
    return HttpResponse(
        bytes(v.beilage),
        content_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition_header(
                True, v.beilage_name or "Beilage.pdf"
            )
        },
    )
