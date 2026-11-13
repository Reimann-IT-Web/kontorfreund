import unicodedata
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from auswertungen import tabelle
from konten.rechte import nur_inhaber

from . import datenschutz as ds
from . import plz
from .forms import (
    BEZEICHNUNGEN,
    KategorieForm,
    KontaktForm,
    anschriften_lesen,
    anschriften_speichern,
    kontaktwege_lesen,
    kontaktwege_speichern,
    nummer_lesen,
)
from .models import Anschrift, Kategorie, Kontakt, Kontaktweg

# Export der Liste (Spezifikation M-5): Spalte und Feld oder Eigenschaft von Kontakt.
EXPORT = [
    ("Kundennummer", "kundennummer"),
    ("Art", "get_art_display"),
    ("Kategorien", "kategorien_text"),
    ("Name", "anzeigename"),
    ("Namenszusatz", "zusatz"),
    ("Anrede", "anrede"),
    ("Titel", "titel"),
    ("Vorname", "vorname"),
    ("Nachname", "nachname"),
    ("Position", "position"),
    ("Straße und Hausnummer", "strasse"),
    ("PLZ", "plz"),
    ("Ort", "ort"),
    ("Land", "land"),
    ("Weitere Anschriften", "anschriften_text"),
    ("E-Mail", "email"),
    ("Telefon", "telefon"),
    ("Weitere Telefonnummern und E-Mail-Adressen", "kontaktwege_text"),
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


def _alphabetisch(text):
    """Schlüssel für das Alphabet nach DIN 5007: Ä wie A, groß wie klein."""
    zerlegt = unicodedata.normalize("NFKD", text.casefold())
    return "".join(z for z in zerlegt if not unicodedata.combining(z))


# Sortierbare Spalten der Liste; „-ort“ dreht die Reihenfolge um.
SORTIERUNG = {
    "nr": lambda k: k.nummer,
    "name": lambda k: _alphabetisch(k.anzeigename),
    "plz": lambda k: k.plz,
    "ort": lambda k: _alphabetisch(k.ort),
}

# Spalten, die jeder Benutzer neben Nummer und Name wählt (Spezifikation K-1), in
# dieser Reihenfolge; die Klasse blendet sie auf schmalen Bildschirmen aus.
SPALTEN = [
    ("strasse", "Straße", "col-ort"),
    ("plz", "PLZ", "col-ort"),
    ("ort", "Ort", "col-ort"),
    ("land", "Land", "col-ort"),
    ("kategorien", "Kategorien", "col-kat"),
    ("telefon", "Telefon", "col-kontakt"),
    ("email", "E-Mail", "col-kontakt"),
    ("website", "Website", "col-kontakt"),
    ("ust_id", "USt-IdNr.", "col-ort"),
]
SPALTEN_VORGABE = ["ort", "kategorien", "telefon"]


def _sortieren(kontakte, sortiert):
    """Gleiche Werte nach dem Namen, Adressen ohne Wert in beiden Richtungen am Ende."""
    feld = sortiert.removeprefix("-")
    schluessel = SORTIERUNG[feld]
    kontakte = sorted(kontakte, key=SORTIERUNG["name"])
    mit = [k for k in kontakte if schluessel(k)]
    ohne = [k for k in kontakte if not schluessel(k)]
    return sorted(mit, key=schluessel, reverse=sortiert != feld) + ohne


def _orte(kontakte):
    """Jeder Ort einmal, ohne Rücksicht auf Groß- und Kleinschreibung.

    Von mehreren Schreibweisen gilt die erste nach Zeichencode, also „Überlingen“
    vor „überlingen“.
    """
    orte = {}
    for ort in kontakte.exclude(ort="").order_by("ort").values_list("ort", flat=True):
        orte.setdefault(ort.casefold(), ort)
    return sorted(orte.values(), key=_alphabetisch)


def liste(request):
    q = request.GET.get("q", "").strip()
    wahl = request.GET.get("kategorie", "")
    kategorie = Kategorie.objects.filter(pk=wahl).first() if wahl.isdigit() else None
    ort = request.GET.get("ort", "").strip()
    sortiert = request.GET.get("sortiert", "")
    if sortiert.removeprefix("-") not in SORTIERUNG:
        sortiert = "name"
    archiv = request.GET.get("archiv") == "1"
    # Gesperrte Adressen (Art. 18 DSGVO) stehen nur in dieser Liste, nur für den Inhaber.
    gesperrt = request.GET.get("gesperrt") == "1" and request.user.ist_inhaber
    if gesperrt:
        kontakte = Kontakt.objects.filter(gesperrt_am__isnull=False)
    else:
        kontakte = Kontakt.objects.filter(archiviert=archiv, gesperrt_am__isnull=True)
    orte = _orte(kontakte)
    kontakte = (
        kontakte.select_related("firma")
        .prefetch_related("kontaktwege", "kategorien", "anschriften")
        .annotate(
            anzahl_belege=Count("altbelege", distinct=True),
            anzahl_eingang=Count("eingangsrechnungen", distinct=True),
        )
    )
    if kategorie:
        kontakte = kontakte.filter(kategorien=kategorie)
    if q:
        bedingung = (
            Q(anzeigename__icontains=q)
            | Q(vorname__icontains=q)
            | Q(nachname__icontains=q)
            | Q(strasse__icontains=q)
            | Q(ort__icontains=q)
            | Q(email__icontains=q)
            | Q(
                pk__in=Kontaktweg.objects.filter(
                    art=Kontaktweg.Art.EMAIL, wert__icontains=q
                ).values("kontakt")
            )
        )
        if (nummer := nummer_lesen(q)) is not None:
            bedingung |= Q(nummer=nummer)
        kontakte = kontakte.filter(bedingung)
    # In Python statt in SQLite: dort stünden „Ärzte“ hinter „Zahnarzt“ und
    # „Überlingen“ fände „überlingen“ nicht.
    if ort:
        kontakte = [k for k in kontakte if k.ort.casefold() == ort.casefold()]
    kontakte = _sortieren(kontakte, sortiert)
    endung = request.GET.get("format", "")
    if endung in tabelle.TYPEN and not gesperrt:
        titel = " ".join(str(t) for t in ("Adressen", kategorie, ort) if t)
        if archiv:
            titel = f"Archiv {titel}"
        return tabelle.antwort(
            endung, *_export(kontakte), f"{titel} {date.today():%d.%m.%Y}"
        )

    def spalte(feld):
        """Kopf einer Spalte: Ein Klick sortiert danach, ein zweiter dreht um."""
        neu = f"-{feld}" if sortiert == feld else feld
        werte = {
            "q": q,
            "kategorie": kategorie.pk if kategorie else "",
            "ort": ort,
            "archiv": "1" if archiv else "",
            "gesperrt": "1" if gesperrt else "",
            "sortiert": "" if neu == "name" else neu,
        }
        richtung = {feld: "ascending", f"-{feld}": "descending"}.get(sortiert, "")
        return {
            "adresse": "?" + urlencode({n: w for n, w in werte.items() if w != ""}),
            "richtung": richtung,
        }

    koepfe = {feld: spalte(feld) for feld in SORTIERUNG}
    gewaehlt = request.user.adressen_spalten
    if gewaehlt is None:
        gewaehlt = SPALTEN_VORGABE
    return render(
        request,
        "contacts/liste.html",
        {
            "bereich": "adressen",
            "kontakte": kontakte,
            "q": q,
            "kategorie": kategorie,
            "kategorien": Kategorie.objects.all(),
            "ort": ort,
            "orte": orte,
            "sortiert": "" if sortiert == "name" else sortiert,
            "koepfe": koepfe,
            "spalten": [
                {
                    "feld": feld,
                    "titel": titel,
                    "klasse": klasse,
                    "kopf": koepfe.get(feld),
                }
                for feld, titel, klasse in SPALTEN
                if feld in gewaehlt
            ],
            "spaltenwahl": [
                (feld, titel, feld in gewaehlt) for feld, titel, _ in SPALTEN
            ],
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


@require_POST
def spalten(request):
    """Spalten der Liste wählen; gilt für den Benutzer auf allen Geräten."""
    if request.POST.get("vorgabe"):
        request.user.adressen_spalten = None
    else:
        gewaehlt = request.POST.getlist("spalte")
        request.user.adressen_spalten = [f for f, _, _ in SPALTEN if f in gewaehlt]
    request.user.save(update_fields=["adressen_spalten"])
    abfrage = QueryDict(request.POST.get("abfrage", "")).urlencode()
    return redirect(reverse("contacts:liste") + (f"?{abfrage}" if abfrage else ""))


def moegliche_dubletten(kontakt, wege=()):
    """Gleiche E-Mail-Adresse oder gleicher Name am selben Ort.

    E-Mail-Adressen zählen auch unter den weiteren, bei beiden Adressen.
    """
    andere = Kontakt.objects.filter(gesperrt_am__isnull=True)
    if kontakt.pk:
        andere = andere.exclude(pk=kontakt.pk)
    bedingung = Q(anzeigename__iexact=kontakt.name_berechnen(), ort__iexact=kontakt.ort)
    emails = [kontakt.email] + [w.wert for w in wege if w.art == Kontaktweg.Art.EMAIL]
    for email in filter(None, emails):
        bedingung |= Q(email__iexact=email) | Q(
            pk__in=Kontaktweg.objects.filter(
                art=Kontaktweg.Art.EMAIL, wert__iexact=email
            ).values("kontakt")
        )
    return list(andere.filter(bedingung)[:3])


def bearbeiten(request, pk=None):
    kontakt = get_object_or_404(Kontakt, pk=pk) if pk else None
    if kontakt and kontakt.gesperrt_am:
        ds.zugriff(request, kontakt)
        return redirect("contacts:datenschutz", kontakt.pk)
    # „Ansprechpartner anlegen“ bei einer Firma: Person dieser Firma, gleiche Kategorien.
    firma = None
    if not kontakt and request.GET.get("firma", "").isdigit():
        firma = Kontakt.objects.filter(
            pk=request.GET["firma"], art=Kontakt.Art.FIRMA, gesperrt_am__isnull=True
        ).first()
    initial = None
    if firma:
        initial = {
            "art": Kontakt.Art.PERSON,
            "firma": firma.pk,
            "kategorien": firma.kategorien.all(),
        }
    elif not kontakt:
        initial = {"kategorien": [Kategorie.vorgabe(Kategorie.Kennung.KUNDE)]}
    form = KontaktForm(request.POST or None, instance=kontakt, initial=initial)
    if request.method == "POST":
        wege, fehler = kontaktwege_lesen(
            *(request.POST.getlist(f"weg_{n}") for n in ("art", "bezeichnung", "wert"))
        )
        anschriften, falsch = anschriften_lesen(
            kontakt,
            *(
                request.POST.getlist(f"anschrift_{n}")
                for n in ("id", "art", "zusatz", "strasse", "plz", "ort", "land")
            ),
        )
        fehler += falsch
    else:
        wege, fehler = list(kontakt.kontaktwege.all()) if kontakt else [], []
        anschriften = list(kontakt.anschriften.all()) if kontakt else []
    dubletten = []
    if request.method == "POST" and form.is_valid() and not fehler:
        dubletten = moegliche_dubletten(form.instance, wege)
        if not dubletten or request.POST.get("trotzdem"):
            with transaction.atomic():
                kontakt = form.save()
                kontaktwege_speichern(kontakt, wege)
                anschriften_speichern(kontakt, anschriften)
            aktion = "gespeichert" if pk else "angelegt"
            messages.success(request, f"Adresse {kontakt.kundennummer} {aktion}.")
            if firma and kontakt.firma_id == firma.pk:
                return redirect("historie:verlauf", firma.pk)
            return redirect(f"{reverse('contacts:liste')}?offen={kontakt.pk}")
    elif request.method == "POST":
        # Oben auf der Seite, sonst übersieht man eine Meldung weit unten im Formular.
        felder = [form.fields[n].label for n in form.errors if n in form.fields]
        messages.error(
            request,
            "Nicht gespeichert. Bitte die markierten Angaben prüfen"
            + (f": {', '.join(felder)}." if felder else "."),
        )
    return render(
        request,
        "contacts/formular.html",
        {
            "bereich": "adressen",
            "form": form,
            "kontakt": kontakt,
            "dubletten": dubletten,
            "wege": wege,
            "bezeichnungen": BEZEICHNUNGEN,
            "anschriften": anschriften,
            "anschrift_arten": Anschrift.Art.choices,
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


# ---------- Kategorien (Spezifikation K-1) ----------


def kategorien(request, pk=None):
    """Kategorien anlegen und umbenennen, mit der Zahl ihrer aktiven Adressen."""
    kategorie = get_object_or_404(Kategorie, pk=pk) if pk else None
    form = KategorieForm(request.POST or None, instance=kategorie)
    if request.method == "POST" and form.is_valid():
        form.save()
        aktion = "umbenannt" if kategorie else "angelegt"
        messages.success(request, f"Kategorie „{form.instance}“ {aktion}.")
        return redirect("contacts:kategorien")
    aktiv = Q(kontakte__archiviert=False, kontakte__gesperrt_am__isnull=True)
    return render(
        request,
        "contacts/kategorien.html",
        {
            "bereich": "adressen",
            "kategorien": Kategorie.objects.annotate(
                anzahl=Count("kontakte", filter=aktiv)
            ),
            "form": form,
            "bearbeitet": kategorie,
        },
    )


@require_POST
def kategorie_loeschen(request, pk):
    kategorie = get_object_or_404(Kategorie, pk=pk, kennung="")
    kategorie.delete()
    messages.success(
        request, f"Kategorie „{kategorie}“ gelöscht. Die Adressen bleiben erhalten."
    )
    return redirect("contacts:kategorien")


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
