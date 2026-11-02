from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import lesen, uebernahme, vorlagen
from .forms import HochladenForm, ZuordnungForm
from .models import Import, Zuordnung

# Je Ziel: Bereich der Seitenleiste, Liste, Seite zum Hochladen, Einzahl, Mehrzahl.
ZIELE = {
    "kontakte": (
        "adressen",
        "contacts:liste",
        "importe:adressen",
        "Adresse",
        "Adressen",
    ),
    "artikel": ("artikel", "artikel:liste", "importe:artikel", "Artikel", "Artikel"),
}


def _anzahl(n, einzahl, mehrzahl):
    return f"{n} {einzahl if n == 1 else mehrzahl}"


def _seite(ziel):
    bereich, liste, hochladen, einzahl, mehrzahl = ZIELE[ziel]
    return {
        "bereich": bereich,
        "liste": liste,
        "hochladen": hochladen,
        "einzahl": einzahl,
        "mehrzahl": mehrzahl,
    }


def _import(request, pk):
    """Die hochgeladene Tabelle sieht nur, wer sie hochgeladen hat."""
    return get_object_or_404(Import, pk=pk, benutzer=request.user)


def hochladen(request, ziel):
    form = HochladenForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        datei = form.cleaned_data["datei"]
        if datei.size > lesen.GROESSTE_DATEI:
            form.add_error(
                "datei", f"Die Datei ist größer als {lesen.GROESSTE_DATEI // 2**20} MB."
            )
        else:
            try:
                spalten, zeilen = lesen.lesen(datei.read())
            except lesen.Unlesbar as fehler:
                form.add_error("datei", str(fehler))
            else:
                Import.aufraeumen(request.user, ziel)
                vorlage, zuordnung = vorlagen.vorschlagen(
                    ziel, spalten, Zuordnung.objects.filter(ziel=ziel)
                )
                imp = Import.objects.create(
                    ziel=ziel,
                    dateiname=datei.name[:255],
                    spalten=spalten,
                    zeilen=zeilen,
                    zuordnung=zuordnung,
                    vorlage=vorlage,
                    benutzer=request.user,
                )
                return redirect("importe:zuordnen", imp.pk)
    return render(
        request,
        "importe/hochladen.html",
        _seite(ziel)
        | {
            "form": form,
            "zuordnungen": Zuordnung.objects.filter(ziel=ziel),
            "vorlagen": [name for name, _ in vorlagen.VORLAGEN[ziel]],
            "groesste_mb": lesen.GROESSTE_DATEI // 2**20,
        },
    )


def zuordnen(request, pk):
    imp = _import(request, pk)
    gespeichert = Zuordnung.objects.filter(ziel=imp.ziel)
    if request.method == "POST" and "vorlage" in request.POST:
        for name, vorlage in vorlagen.alle(imp.ziel, gespeichert):
            if name == request.POST["vorlage"]:
                imp.zuordnung = vorlagen.anwenden(vorlage, imp.spalten)
                imp.vorlage, imp.bestaetigt = name, False
                imp.save()
                break
        return redirect("importe:zuordnen", imp.pk)
    form = ZuordnungForm(imp, request.POST or None)
    if request.method == "POST" and form.is_valid():
        imp.zuordnung = form.zuordnung()
        imp.kategorie = form.cleaned_data.get("kategorie", imp.kategorie)
        imp.dubletten_anlegen = form.cleaned_data["dubletten_anlegen"]
        imp.bestaetigt = True
        imp.save()
        if name := form.cleaned_data["speichern_als"].strip():
            Zuordnung.objects.update_or_create(
                ziel=imp.ziel, name=name, defaults={"felder": imp.zuordnung}
            )
            messages.success(request, f"Die Zuordnung ist als „{name}“ gespeichert.")
        return redirect("importe:bericht", imp.pk)
    return render(
        request,
        "importe/zuordnen.html",
        _seite(imp.ziel)
        | {
            "imp": imp,
            "form": form,
            "vorlagen": [name for name, _ in vorlagen.alle(imp.ziel, gespeichert)],
            "vorschau": imp.zeilen[:5],
        },
    )


def bericht(request, pk):
    imp = _import(request, pk)
    if not imp.bestaetigt:
        return redirect("importe:zuordnen", imp.pk)
    return render(
        request,
        "importe/bericht.html",
        _seite(imp.ziel) | {"imp": imp, "bericht": uebernahme.pruefen(imp)},
    )


@require_POST
def uebernehmen(request, pk):
    imp = _import(request, pk)
    if not imp.bestaetigt:
        return redirect("importe:zuordnen", imp.pk)
    _, liste, _, einzahl, mehrzahl = ZIELE[imp.ziel]
    with transaction.atomic():
        bericht = uebernahme.uebernehmen(imp)
        imp.delete()
    text = f"{_anzahl(len(bericht.neu), einzahl, mehrzahl)} übernommen."
    if bericht.dubletten and not imp.dubletten_anlegen:
        text += f" {_anzahl(len(bericht.dubletten), 'mögliche Dublette', 'mögliche Dubletten')} übersprungen."
    if bericht.fehler:
        text += f" {_anzahl(len(bericht.fehler), 'Zeile', 'Zeilen')} mit Fehlern ausgelassen."
    messages.success(request, text)
    return redirect(liste)


@require_POST
def verwerfen(request, pk):
    imp = _import(request, pk)
    imp.delete()
    messages.info(request, "Der Import ist abgebrochen, übernommen wurde nichts.")
    return redirect(ZIELE[imp.ziel][1])


@require_POST
def zuordnung_loeschen(request, pk):
    zuordnung = get_object_or_404(Zuordnung, pk=pk)
    zuordnung.delete()
    messages.success(request, f"Die Zuordnung „{zuordnung}“ ist gelöscht.")
    return redirect(ZIELE[zuordnung.ziel][2])
