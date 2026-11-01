import re
from datetime import date

from django.contrib import messages
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from auswertungen import tabelle
from konten.rechte import nur_inhaber

from . import datenschutz as ds
from . import plz
from .forms import KontaktForm
from .models import Kontakt

KATEGORIEN_PLURAL = {
    Kontakt.Kategorie.KUNDE: "Kunden",
    Kontakt.Kategorie.INTERESSENT: "Interessenten",
    Kontakt.Kategorie.LIEFERANT: "Lieferanten",
}

# Export der Liste (Spezifikation M-5): Spalte und Feld oder Eigenschaft von Kontakt.
EXPORT = [
    ("Kundennummer", "kundennummer"),
    ("Art", "get_art_display"),
    ("Kategorie", "get_kategorie_display"),
    ("Name", "anzeigename"),
    ("Namenszusatz", "zusatz"),
    ("Anrede", "anrede"),
    ("Titel", "titel"),
    ("Vorname", "vorname"),
    ("Nachname", "nachname"),
    ("Straße und Hausnummer", "strasse"),
    ("PLZ", "plz"),
    ("Ort", "ort"),
    ("Land", "land"),
    ("E-Mail", "email"),
    ("Telefon", "telefon"),
    ("Website", "website"),
    ("USt-IdNr.", "ust_id"),
    ("Käuferreferenz oder Leitweg-ID", "kaeuferreferenz"),
    ("XRechnung", "xrechnung"),
    ("Notiz", "notiz"),
]


def _export(kontakte):
    zeilen = []
    for k in kontakte:
        zeile = []
        for _, feld in EXPORT:
            wert = getattr(k, feld)
            wert = wert() if callable(wert) else wert
            if isinstance(wert, bool):
                wert = "ja" if wert else ""
            zeile.append(wert or None)
        zeilen.append(zeile)
    return [(titel, "text") for titel, _ in EXPORT], zeilen


def _nummer(text):
    """„K-0012“ oder „12“ → 12, sonst None."""
    treffer = re.fullmatch(r"(?:K-?)?0*(\d+)", text.strip(), flags=re.IGNORECASE)
    return int(treffer.group(1)) if treffer else None


def liste(request):
    q = request.GET.get("q", "").strip()
    kategorie = request.GET.get("kategorie", "")
    archiv = request.GET.get("archiv") == "1"
    # Gesperrte Adressen (Art. 18 DSGVO) stehen nur in dieser Liste, nur für den Inhaber.
    gesperrt = request.GET.get("gesperrt") == "1" and request.user.ist_inhaber
    if gesperrt:
        kontakte = Kontakt.objects.filter(gesperrt_am__isnull=False)
    else:
        kontakte = Kontakt.objects.filter(archiviert=archiv, gesperrt_am__isnull=True)
    kontakte = kontakte.annotate(
        anzahl_belege=Count("altbelege", distinct=True),
        anzahl_eingang=Count("eingangsrechnungen", distinct=True),
    )
    if kategorie in Kontakt.Kategorie.values:
        kontakte = kontakte.filter(kategorie=kategorie)
    if q:
        bedingung = (
            Q(anzeigename__icontains=q)
            | Q(vorname__icontains=q)
            | Q(nachname__icontains=q)
            | Q(ort__icontains=q)
            | Q(email__icontains=q)
        )
        if (nummer := _nummer(q)) is not None:
            bedingung |= Q(nummer=nummer)
        kontakte = kontakte.filter(bedingung)
    endung = request.GET.get("format", "")
    if endung in tabelle.TYPEN and not gesperrt:
        titel = KATEGORIEN_PLURAL.get(kategorie, "Adressen")
        if archiv:
            titel = f"Archiv {titel}"
        return tabelle.antwort(
            endung, *_export(kontakte), f"{titel} {date.today():%d.%m.%Y}"
        )
    return render(
        request,
        "contacts/liste.html",
        {
            "bereich": "adressen",
            "kontakte": kontakte,
            "q": q,
            "kategorie": kategorie,
            "kategorien": KATEGORIEN_PLURAL.items(),
            "archiv": archiv,
            "gesperrt": gesperrt,
            "anzahl": Kontakt.objects.filter(archiviert=False).count(),
            "anzahl_archiv": Kontakt.objects.filter(
                archiviert=True, gesperrt_am__isnull=True
            ).count(),
            "anzahl_gesperrt": Kontakt.objects.filter(gesperrt_am__isnull=False).count()
            if request.user.ist_inhaber
            else 0,
            "offen": request.GET.get("offen", ""),
            "exporte": tabelle.links(request),
        },
    )


def moegliche_dubletten(kontakt):
    """Gleiche E-Mail-Adresse oder gleicher Name am selben Ort."""
    andere = Kontakt.objects.filter(gesperrt_am__isnull=True)
    if kontakt.pk:
        andere = andere.exclude(pk=kontakt.pk)
    bedingung = Q(anzeigename__iexact=kontakt.name_berechnen(), ort__iexact=kontakt.ort)
    if kontakt.email:
        bedingung |= Q(email__iexact=kontakt.email)
    return list(andere.filter(bedingung)[:3])


def bearbeiten(request, pk=None):
    kontakt = get_object_or_404(Kontakt, pk=pk) if pk else None
    if kontakt and kontakt.gesperrt_am:
        ds.zugriff(request, kontakt)
        return redirect("contacts:datenschutz", kontakt.pk)
    form = KontaktForm(request.POST or None, instance=kontakt)
    dubletten = []
    if request.method == "POST" and form.is_valid():
        dubletten = moegliche_dubletten(form.instance)
        if not dubletten or request.POST.get("trotzdem"):
            kontakt = form.save()
            aktion = "gespeichert" if pk else "angelegt"
            messages.success(request, f"Adresse {kontakt.kundennummer} {aktion}.")
            return redirect(f"{reverse('contacts:liste')}?offen={kontakt.pk}")
    return render(
        request,
        "contacts/formular.html",
        {
            "bereich": "adressen",
            "form": form,
            "kontakt": kontakt,
            "dubletten": dubletten,
        },
    )


@require_POST
def archivieren(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    ds.zugriff(request, kontakt, aendern=True)
    kontakt.archiviert = not kontakt.archiviert
    kontakt.save(update_fields=["archiviert", "geaendert"])
    if kontakt.archiviert:
        messages.success(
            request,
            f"{kontakt} archiviert. Sie finden die Adresse unter „Archiv“.",
        )
    else:
        messages.success(request, f"{kontakt} ist wieder aktiv.")
    return redirect("contacts:liste")


# ---------- Datenschutz (Spezifikation D-1) ----------


@nur_inhaber
def datenschutz(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    alle = ds.belege(kontakt)
    loeschbar = ds.loeschbar(alle)
    return render(
        request,
        "contacts/datenschutz.html",
        {
            "bereich": "adressen",
            "kontakt": kontakt,
            # Eine gesperrte Adresse lässt sich nicht mehr öffnen; ihre Angaben stehen hier.
            "angaben": [
                (name, "\n".join(ds.zeilen(wert)))
                for name, wert in ds.stammdaten(kontakt).items()
                if wert not in ("", None, False)
            ]
            if kontakt.gesperrt_am
            else [],
            "belege": alle,
            "frist": ds.frist(alle),
            "loeschbar": loeschbar,
            "umfang": ds.umfang(kontakt, alle) if loeschbar else [],
            "entwuerfe": ds.entwuerfe(kontakt),
            "offen": kontakt.wiedervorlagen.filter(erledigt_am__isnull=True).count(),
            "auskunft": ds.letzte_auskunft(kontakt),
        },
    )


@nur_inhaber
@require_POST
def auskunft(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    return FileResponse(
        ds.auskunft(kontakt),
        as_attachment=True,
        filename=f"Auskunft {kontakt.kundennummer} {date.today():%Y-%m-%d}.zip",
        content_type="application/zip",
    )


@nur_inhaber
@require_POST
def sperren(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk, gesperrt_am__isnull=True)
    if ds.loeschbar(ds.belege(kontakt)):
        raise Http404
    ds.sperren(kontakt, request.user)
    messages.success(
        request,
        f"{kontakt.kundennummer} ist gesperrt. Die Adresse erscheint nirgends mehr; "
        "Sie finden sie unter Adressen bei „gesperrt“.",
    )
    return redirect("contacts:datenschutz", kontakt.pk)


@nur_inhaber
@require_POST
def entsperren(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk, gesperrt_am__isnull=False)
    ds.entsperren(kontakt)
    messages.success(
        request,
        f"Die Sperre ist aufgehoben. {kontakt} liegt im Archiv und lässt sich dort "
        "wiederherstellen.",
    )
    return redirect("contacts:datenschutz", kontakt.pk)


@nur_inhaber
@require_POST
def loeschen(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    if not ds.loeschbar(ds.belege(kontakt)):
        raise Http404
    if not request.POST.get("bestaetigt"):
        messages.error(
            request,
            "Bitte bestätigen Sie, dass Sie die Adresse endgültig löschen wollen.",
        )
        return redirect("contacts:datenschutz", kontakt.pk)
    ds.loeschen(kontakt)
    messages.success(
        request, f"{kontakt.kundennummer} ist mit allem, was dazugehörte, gelöscht."
    )
    return redirect("contacts:liste")


def orte(request):
    """Orte zu einer deutschen PLZ für das Feld „Ort“ (static/js/app.js, data-plz)."""
    alle, eindeutig = plz.orte(request.GET.get("plz", ""))
    return JsonResponse({"orte": alle, "ort": eindeutig})
