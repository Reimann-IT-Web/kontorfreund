import logging
from datetime import date

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from konten.rechte import nur_inhaber

from . import gesamtexport as export
from . import sicherung
from .forms import EinlesenForm, KennwortForm, OrtForm, WiederherstellenForm

logger = logging.getLogger(__name__)


@nur_inhaber
def uebersicht(request):
    zustand = sicherung.zustand()
    aktion = request.POST.get("aktion")
    kennwort = KennwortForm(
        request.POST if aktion in ("einrichten", "kennwort") else None
    )
    ort = OrtForm(
        request.POST if aktion in ("einrichten", "ort") else None,
        initial={"ziel": zustand["ziel"], "aufbewahren": zustand["aufbewahren"]},
    )
    if not zustand["eingerichtet"]:
        if aktion == "einrichten" and all([kennwort.is_valid(), ort.is_valid()]):
            sicherung.einrichten(kennwort.cleaned_data["kennwort"])
            sicherung.einstellen(**ort.cleaned_data)
            return _sichern(
                request,
                "Die Datensicherung ist eingerichtet, die erste Sicherung liegt bereit.",
                "Die Datensicherung ist eingerichtet. Sobald Sie Daten eingeben, "
                "sichert Kontorfreund sie jeden Tag.",
            )
    elif aktion == "sichern":
        return _sichern(
            request, "Ihre Daten sind gesichert.", "Es gibt noch nichts zu sichern."
        )
    elif aktion == "ort" and ort.is_valid():
        sicherung.einstellen(**ort.cleaned_data)
        if ort.cleaned_data["ziel"] not in ("", zustand["ziel"]):
            return _sichern(
                request,
                "Gespeichert. Die neueste Sicherung liegt jetzt auch dort.",
                "Gespeichert.",
            )
        messages.success(request, "Gespeichert.")
        return redirect("backups:uebersicht")
    elif aktion == "kennwort" and kennwort.is_valid():
        sicherung.einrichten(kennwort.cleaned_data["kennwort"])
        text = (
            "Neue Sicherungen verwenden ab jetzt das neue Kennwort. "
            "Ältere öffnen Sie weiter mit dem bisherigen."
        )
        return _sichern(request, text, text)
    return render(
        request,
        "backups/uebersicht.html",
        {
            "bereich": "datensicherung",
            "kennwort_form": kennwort,
            "ort_form": ort,
            "einlesen_form": EinlesenForm(),
            "sicherungen": sicherung.liste(),
            "groesse": sicherung.geschaetzte_groesse(),
            "ordner": sicherung.sicherungsordner(),
        },
    )


def _sichern(request, text, ohne_daten):
    # Ein leerer Stand, etwa auf einem neuen Rechner, soll am zweiten Speicherort
    # keine ältere Sicherung verdrängen.
    if not sicherung.hat_daten():
        messages.success(request, ohne_daten)
        return redirect("backups:uebersicht")
    try:
        _, hinweis = sicherung.sichern()
    except Exception:
        logger.exception("Sicherung fehlgeschlagen")
        messages.error(request, sicherung.FEHLER_SCHREIBEN)
    else:
        if hinweis:
            messages.warning(request, f"{text} {hinweis}")
        else:
            messages.success(request, text)
    return redirect("backups:uebersicht")


@nur_inhaber
def wiederherstellen(request, ort, name):
    pfad = sicherung.finden(ort, name)
    if not pfad:
        raise Http404("Diese Sicherung gibt es nicht.")
    eintrag = sicherung.eintrag(pfad)
    if not eintrag["kopf"]:
        messages.error(request, "Diese Datei lässt sich nicht als Sicherung lesen.")
        return redirect("backups:uebersicht")
    form = WiederherstellenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            _, vorher = sicherung.wiederherstellen(pfad, form.cleaned_data["kennwort"])
        except sicherung.FalschesKennwort as fehler:
            form.add_error("kennwort", str(fehler))
        except sicherung.SicherungFehler as fehler:
            form.add_error(None, str(fehler))
        except Exception:
            logger.exception("Wiederherstellen fehlgeschlagen")
            form.add_error(
                None,
                "Die Wiederherstellung ist fehlgeschlagen. Falls schon etwas ersetzt wurde, "
                "liegt Ihr vorheriger Stand als Sicherung „Vor einer Wiederherstellung“ bereit.",
            )
        else:
            messages.success(
                request,
                f"Der Stand vom {eintrag['erstellt']:%d.%m.%Y, %H:%M} Uhr ist wiederhergestellt. "
                "Ihr vorheriger Stand liegt als eigene Sicherung bereit.",
            )
            return redirect("backups:uebersicht")
    return render(
        request,
        "backups/wiederherstellen.html",
        {
            "bereich": "datensicherung",
            "s": eintrag,
            "ort": sicherung.ORTE[ort],
            "jetzt": sicherung.umfang_jetzt(),
            "form": form,
        },
    )


@nur_inhaber
def gesamtexport(request):
    """Alle Daten und Belege, lesbar ohne Kontorfreund (backups/gesamtexport.py)."""
    return FileResponse(
        export.paket(),
        as_attachment=True,
        filename=f"Kontorfreund Gesamtexport {date.today():%Y-%m-%d}.zip",
        content_type="application/zip",
    )


@require_POST
@nur_inhaber
def einlesen(request):
    form = EinlesenForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Bitte wählen Sie eine Sicherungsdatei aus.")
        return redirect("backups:uebersicht")
    try:
        pfad = sicherung.einlesen(form.cleaned_data["datei"])
    except sicherung.SicherungFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("backups:uebersicht")
    return redirect("backups:wiederherstellen", "hier", pfad.name)
