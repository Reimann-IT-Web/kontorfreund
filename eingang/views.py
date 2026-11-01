import base64
import binascii
from io import BytesIO
from pathlib import PurePosixPath

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_POST

from contacts.models import Kontakt

from . import lesen
from .models import Doppelt, Eingangsrechnung

GROESSTE_DATEI = 20 * 1024 * 1024
# Anhänge werden immer heruntergeladen, nie im Browser geöffnet. Die Endung folgt
# dem Typ, nicht dem Dateinamen des Absenders: Aus „Rechnung.pdf.exe“ wird so keine
# Datei, die Windows per Doppelklick startet. Andere Typen werden zur einfachen Datei.
ANHANG_TYPEN = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/csv": ".csv",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.oasis.opendocument.spreadsheet": ".ods",
}


def liste(request):
    q = request.GET.get("q", "").strip()
    jahr = request.GET.get("jahr", "")
    kontakt = request.GET.get("kontakt", "")
    rechnungen = Eingangsrechnung.objects.select_related("kontakt")
    if jahr.isdigit():
        rechnungen = rechnungen.filter(datum__year=int(jahr))
    if kontakt.isdigit():
        rechnungen = rechnungen.filter(kontakt_id=int(kontakt))
    if q:
        rechnungen = rechnungen.filter(
            Q(nummer__icontains=q)
            | Q(lieferant__icontains=q)
            | Q(kontakt__anzeigename__icontains=q)
        )
    return render(
        request,
        "eingang/liste.html",
        {
            "bereich": "eingang",
            "rechnungen": rechnungen,
            "q": q,
            "jahr": jahr,
            "kontakt": kontakt,
            "jahre": [
                d.year
                for d in Eingangsrechnung.objects.dates("datum", "year", order="DESC")
            ],
            "gesamt": Eingangsrechnung.objects.count(),
        },
    )


@require_POST
def hochladen(request):
    dateien = request.FILES.getlist("dateien")
    if not dateien:
        messages.error(request, "Bitte wählen Sie eine E-Rechnung aus.")
        return redirect("eingang:liste")
    abgelegt, vorhanden = [], []
    for datei in dateien:
        if datei.size > GROESSTE_DATEI:
            messages.error(request, f"{datei.name}: Die Datei ist größer als 20 MB.")
            continue
        try:
            rechnung = Eingangsrechnung.ablegen(datei.name, datei.read())
        except Doppelt as fehler:
            messages.info(request, f"{datei.name}: {fehler}")
            vorhanden.append(fehler.vorhanden)
            continue
        except lesen.Unlesbar as fehler:
            messages.error(request, f"{datei.name}: {fehler}")
            continue
        abgelegt.append(rechnung)
        doppelt = Eingangsrechnung.objects.filter(
            lieferant=rechnung.lieferant, nummer=rechnung.nummer
        ).exclude(pk=rechnung.pk)
        if doppelt.exists():
            messages.warning(
                request,
                f"Von {rechnung.lieferant} ist schon eine Rechnung {rechnung.nummer} "
                "abgelegt. Bitte prüfen Sie vor dem Bezahlen, ob sie doppelt kam.",
            )
    if len(abgelegt) == 1:
        r = abgelegt[0]
        messages.success(
            request,
            f"{r} von {r.lieferant} ist abgelegt"
            + (f" und der Adresse {r.kontakt} zugeordnet." if r.kontakt else "."),
        )
    elif abgelegt:
        messages.success(request, f"{len(abgelegt)} E-Rechnungen sind abgelegt.")
    if len(dateien) == 1 and (abgelegt or vorhanden):
        return redirect("eingang:anzeigen", (abgelegt or vorhanden)[0].pk)
    return redirect("eingang:liste")


def anzeigen(request, pk):
    rechnung = get_object_or_404(
        Eingangsrechnung.objects.select_related("kontakt"), pk=pk
    )
    d, fehler = None, ""
    try:
        d = rechnung.lesen()[1]
    except lesen.Unlesbar as f:
        fehler = str(f)
    except OSError:
        fehler = (
            "Die Datei fehlt im Archiv. Spielen Sie bitte eine Datensicherung zurück."
        )
    adressen = Kontakt.objects.filter(archiviert=False)
    return render(
        request,
        "eingang/anzeigen.html",
        {
            "bereich": "eingang",
            "r": rechnung,
            "d": d,
            "fehler": fehler,
            "lieferanten": adressen.filter(kategorie=Kontakt.Kategorie.LIEFERANT),
            "weitere": adressen.exclude(kategorie=Kontakt.Kategorie.LIEFERANT),
        },
    )


@require_POST
def zuordnen(request, pk):
    rechnung = get_object_or_404(Eingangsrechnung, pk=pk)
    if "neu" in request.POST:
        kontakt = _adresse_anlegen(rechnung.lesen()[1]["verkaeufer"])
        messages.success(
            request,
            f"Die Adresse {kontakt.kundennummer} {kontakt} ist angelegt. "
            "Fehlende Angaben ergänzen Sie unter Adressen.",
        )
    else:
        wahl = request.POST.get("kontakt", "")
        kontakt = get_object_or_404(Kontakt, pk=int(wahl)) if wahl.isdigit() else None
        messages.success(
            request,
            f"Zugeordnet zu {kontakt}." if kontakt else "Die Zuordnung ist aufgehoben.",
        )
    rechnung.kontakt = kontakt
    rechnung.save(update_fields=["kontakt"])
    return redirect("eingang:anzeigen", rechnung.pk)


def _adresse_anlegen(v):
    """Lieferant als neue Adresse mit den Angaben aus der Rechnung."""
    email = v["email"] or (v["elektronisch"] if "@" in v["elektronisch"] else "")
    try:
        validate_email(email)
    except ValidationError:
        email = ""
    return Kontakt.objects.create(
        kategorie=Kontakt.Kategorie.LIEFERANT,
        firmenname=v["name"][:200],
        strasse=(v["zeilen"] or [""])[0][:200],
        plz=v["plz"][:10],
        ort=v["ort"][:100],
        land=v["landname"][:100],
        email=email,
        telefon=v["telefon"][:50],
        ust_id=v["ust_id"].replace(" ", "")[:20],
    )


# Der eingebaute PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def datei(request, pk):
    """Die Originaldatei, unverändert: PDF zum Ansehen, XML zum Herunterladen."""
    rechnung = get_object_or_404(Eingangsrechnung, pk=pk)
    if not rechnung.pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    pdf = rechnung.format == Eingangsrechnung.Format.PDF
    return FileResponse(
        rechnung.pfad.open("rb"),
        content_type="application/pdf" if pdf else "application/xml",
        as_attachment=not pdf or "herunterladen" in request.GET,
        filename=rechnung.originalname,
    )


def anhang(request, pk, nr):
    """Eine in der E-Rechnung eingebettete Datei (BG-24), immer als Download."""
    rechnung = get_object_or_404(Eingangsrechnung, pk=pk)
    try:
        anhaenge = rechnung.lesen()[1]["anhaenge"]
    except (lesen.Unlesbar, OSError):
        raise Http404("Die E-Rechnung lässt sich nicht lesen.") from None
    if nr >= len(anhaenge) or not anhaenge[nr]["base64"]:
        raise Http404("Diesen Anhang gibt es nicht.")
    a = anhaenge[nr]
    try:
        inhalt = base64.b64decode(a["base64"], validate=True)
    except binascii.Error:
        raise Http404("Der Anhang ist beschädigt.") from None
    stamm = PurePosixPath(a["dateiname"].replace("\\", "/")).stem.strip()
    return FileResponse(
        BytesIO(inhalt),
        as_attachment=True,
        filename=(stamm or f"Anhang {nr + 1}") + ANHANG_TYPEN.get(a["mime"], ".bin"),
        content_type=a["mime"]
        if a["mime"] in ANHANG_TYPEN
        else "application/octet-stream",
    )
