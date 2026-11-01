import logging
import smtplib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_POST

from auswertungen import buch, tabelle
from contacts.models import Kontakt
from core.models import Firmendaten
from core.templatetags.kf import euro, zahl
from invoicing import versand
from invoicing.beleg import seitenbilder
from invoicing.forms import VersandForm
from invoicing.models import Rechnung
from konten.rechte import nur_inhaber

from . import mahnen
from .forms import AusbuchenForm, BasiszinsForm, MahnstufeForm, MahnungForm, ZahlungForm
from .models import STUFEN, Basiszins, Mahnstufe, Mahnung, Zahlung

logger = logging.getLogger(__name__)

ANSICHTEN = [
    ("offen", "Offen"),
    ("ueberfaellig", "Überfällig"),
    ("bezahlt", "Bezahlt"),
    ("alle", "Alle"),
]
EXPORT_TITEL = {
    "offen": "Offene Posten",
    "ueberfaellig": "Überfällige Posten",
    "bezahlt": "Bezahlte Rechnungen",
    "alle": "Alle Rechnungen",
}
# Export der Liste (Spezifikation M-5)
EXPORT = [
    ("Rechnung", "text"),
    ("Datum", "datum"),
    ("Fällig am", "datum"),
    ("Kundennummer", "text"),
    ("Kunde", "text"),
    ("Betrag", "betrag"),
    ("Bezahlt", "betrag"),
    ("Offen", "betrag"),
    ("Stand", "text"),
    ("Zuletzt gemahnt", "text"),
    ("Gemahnt am", "datum"),
]


def _export(rechnungen):
    zeilen = []
    for r in rechnungen:
        mahnungen = list(r.mahnungen.all())
        letzte = max(mahnungen, key=lambda m: m.stufe) if mahnungen else None
        zeilen.append(
            [
                r.nummer,
                r.datum,
                r.faellig,
                r.kontakt.kundennummer,
                str(r.kontakt),
                r.korrigierter_betrag,
                r.bezahlt,
                r.offen,
                buch.STAND[r.zahlstand],
                letzte.bezeichnung if letzte else None,
                letzte.datum if letzte else None,
            ]
        )
    return zeilen


def liste(request):
    kunde = request.GET.get("kunde", "")
    kontakt = Kontakt.objects.filter(pk=kunde).first() if kunde.isdigit() else None
    alle = mahnen.posten(kontakt)
    offen = [r for r in alle if r.offen != 0]
    zeigen = request.GET.get("zeigen", "offen")
    if zeigen not in dict(ANSICHTEN):
        zeigen = "offen"
    rechnungen = {
        "offen": offen,
        "ueberfaellig": [r for r in offen if r.ueberfaellig],
        "bezahlt": [
            r for r in reversed(alle) if r.offen == 0 and r.zahlstand != "storniert"
        ],
        "alle": list(reversed(alle)),
    }[zeigen]
    if zeigen in ("offen", "ueberfaellig"):
        rechnungen.sort(key=lambda r: r.faellig)
    endung = request.GET.get("format", "")
    if endung in tabelle.TYPEN:
        titel = f"{EXPORT_TITEL[zeigen]} {date.today():%d.%m.%Y}"
        return tabelle.antwort(endung, EXPORT, _export(rechnungen), titel)
    ueberfaellig = [r for r in offen if r.ueberfaellig]
    return render(
        request,
        "zahlungen/liste.html",
        {
            "bereich": "offene-posten",
            "rechnungen": rechnungen,
            "zeigen": zeigen,
            "ansichten": ANSICHTEN,
            "kontakt": kontakt,
            "kunden": Kontakt.objects.filter(
                rechnungen__status=Rechnung.Status.FESTGESCHRIEBEN
            ).distinct(),
            "summe_offen": sum((r.offen for r in offen if r.offen > 0), Decimal("0")),
            "summe_ueberfaellig": sum((r.offen for r in ueberfaellig), Decimal("0")),
            "anzahl_offen": sum(1 for r in offen if r.offen > 0),
            "anzahl_ueberfaellig": len(ueberfaellig),
            "vorschlaege": mahnen.vorschlaege(offen, Mahnstufe.alle()),
            "basiszins_veraltet": Basiszins.veraltet(),
            "zahlung_form": ZahlungForm(prefix="zahlung"),
            "exporte": tabelle.links(request),
        },
    )


def kontoauszug(request, pk):
    """Alle Rechnungen und Zahlungen eines Kunden mit laufendem Saldo."""
    kontakt = get_object_or_404(Kontakt, pk=pk)
    eintraege = []
    for r in Rechnung.objects.filter(
        kontakt=kontakt, status=Rechnung.Status.FESTGESCHRIEBEN
    ).select_related("storno_zu", "korrektur_zu"):
        bezug = r.storno_zu or r.korrektur_zu
        eintraege.append(
            {
                "datum": r.datum,
                "folge": 0,
                "text": f"{r.bezeichnung} {r.nummer}"
                + (f" zu Rechnung {bezug.nummer}" if bezug else ""),
                "url": reverse("invoicing:bearbeiten", args=[r.pk]),
                "soll": r.brutto,
                "haben": None,
            }
        )
    for z in Zahlung.objects.filter(rechnung__kontakt=kontakt).select_related(
        "rechnung"
    ):
        text = (
            f"Skonto zu Rechnung {z.rechnung.nummer}"
            if z.ist_skonto
            else f"Ausgebucht: {z.notiz}"
            if z.ist_ausbuchung
            else f"{z.get_art_display()} zu Rechnung {z.rechnung.nummer}"
        )
        if z.nebenkosten:
            text += f" (dazu {euro(z.nebenkosten)} Mahnkosten und Zinsen)"
        eintraege.append(
            {
                "datum": z.datum,
                "folge": 1,
                "text": text,
                "url": reverse("invoicing:bearbeiten", args=[z.rechnung_id]),
                "soll": None,
                "haben": z.betrag,
            }
        )
    eintraege.sort(key=lambda e: (e["datum"], e["folge"]))
    saldo = Decimal("0.00")
    for e in eintraege:
        saldo += (e["soll"] or 0) - (e["haben"] or 0)
        e["saldo"] = saldo
    return render(
        request,
        "zahlungen/kontoauszug.html",
        {
            "bereich": "offene-posten",
            "kontakt": kontakt,
            "eintraege": eintraege,
            "saldo": saldo,
            "zu_viel": -saldo,
        },
    )


def _posten(pk):
    return get_object_or_404(
        Rechnung.objects.select_related("kontakt", "stornorechnung").prefetch_related(
            "zahlungen", "korrekturen", "mahnungen"
        ),
        pk=pk,
        status=Rechnung.Status.FESTGESCHRIEBEN,
        storno_zu__isnull=True,
        korrektur_zu__isnull=True,
    )


def _zurueck(request, rechnung):
    weiter = request.POST.get("weiter", "")
    if url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}):
        return redirect(weiter)
    return redirect("invoicing:bearbeiten", rechnung.pk)


def _fehler(request, form, was):
    gruende = [f for fehler in form.errors.values() for f in fehler]
    messages.error(request, f"{was}: {' '.join(gruende)}")


@require_POST
def buchen(request, pk):
    rechnung = _posten(pk)
    form = ZahlungForm(request.POST, prefix="zahlung")
    if not form.is_valid():
        _fehler(request, form, "Die Zahlung ist nicht gebucht")
        return _zurueck(request, rechnung)
    d = form.cleaned_data
    eingang = d["betrag"]
    # Was über den offenen Betrag hinausgeht, deckt zuerst Mahnkosten und Zinsen.
    neben = Decimal("0.00")
    if eingang > 0:
        rest = eingang - max(rechnung.offen, Decimal("0"))
        if rest > 0:
            neben = min(rest, mahnen.offene_nebenkosten(rechnung))
    skonto = _skonto(rechnung, eingang, d["datum"])
    Zahlung.objects.create(
        rechnung=rechnung,
        datum=d["datum"],
        betrag=eingang - neben,
        nebenkosten=neben,
        art=d["art"],
        notiz=d["notiz"],
    )
    if skonto:
        Zahlung.objects.create(
            rechnung=rechnung,
            datum=d["datum"],
            betrag=skonto,
            art=Zahlung.Art.SKONTO,
            notiz=f"{zahl(rechnung.skonto_prozent)} % bei Zahlung bis "
            f"{rechnung.skonto_bis:%d.%m.%Y}",
        )
    offen = _posten(pk).offen
    meldung = f"Zahlung über {euro(eingang)} zu Rechnung {rechnung.nummer} gebucht."
    if neben:
        meldung += f" Davon {euro(neben)} für Mahnkosten und Zinsen."
    if skonto:
        meldung += f" {euro(skonto)} Skonto abgezogen."
    if offen == 0:
        meldung += " Die Rechnung ist bezahlt."
    elif offen > 0:
        meldung += f" Offen bleiben {euro(offen)}."
    else:
        meldung += f" Der Kunde hat {euro(-offen)} zu viel gezahlt."
    messages.success(request, meldung)
    return _zurueck(request, rechnung)


def _skonto(rechnung, eingang, datum):
    """Was in der Skontofrist am offenen Betrag fehlt, höchstens das vereinbarte Skonto.

    Nur wenn die Zahlung die Rechnung damit ausgleicht und noch kein Skonto gebucht ist.
    """
    if (
        rechnung.skonto_prozent <= 0
        or datum > rechnung.skonto_bis
        or any(z.ist_skonto for z in rechnung.zahlungen.all())
    ):
        return Decimal("0.00")
    fehlt = rechnung.offen - eingang
    return fehlt if 0 < fehlt <= rechnung.skonto else Decimal("0.00")


@require_POST
def ausbuchen(request, pk):
    rechnung = _posten(pk)
    form = AusbuchenForm(request.POST, prefix="ausbuchen")
    if not form.is_valid():
        _fehler(request, form, "Nichts ausgebucht")
        return _zurueck(request, rechnung)
    d = form.cleaned_data
    if d["betrag"] > rechnung.offen:
        messages.error(
            request,
            f"Ausbuchen lässt sich höchstens der offene Betrag von {euro(rechnung.offen)}.",
        )
        return _zurueck(request, rechnung)
    Zahlung.objects.create(
        rechnung=rechnung,
        datum=d["datum"],
        betrag=d["betrag"],
        art=Zahlung.Art.AUSBUCHUNG,
        notiz=d["grund"],
    )
    offen = _posten(pk).offen
    messages.success(
        request,
        f"{euro(d['betrag'])} ausgebucht. "
        + (
            f"Rechnung {rechnung.nummer} ist erledigt."
            if offen == 0
            else f"Offen bleiben {euro(offen)}."
        ),
    )
    return _zurueck(request, rechnung)


@require_POST
def zahlung_loeschen(request, pk):
    zahlung = get_object_or_404(Zahlung.objects.select_related("rechnung"), pk=pk)
    rechnung = zahlung.rechnung
    zahlung.delete()
    messages.success(
        request,
        f"Buchung über {euro(zahlung.eingang)} vom {zahlung.datum:%d.%m.%Y} gelöscht.",
    )
    return redirect("invoicing:bearbeiten", rechnung.pk)


def mahnung_neu(request, pk):
    rechnung = _posten(pk)
    naechste = mahnen.naechste_stufe(rechnung, Mahnstufe.alle())
    if not naechste:
        messages.info(
            request,
            f"Für Rechnung {rechnung.nummer} ist kein weiteres Schreiben vorgesehen.",
        )
        return redirect("invoicing:bearbeiten", rechnung.pk)
    stufe = naechste[0]
    firma = Firmendaten.laden()
    heute = date.today()
    vorgabe = {
        "datum": heute,
        "frist": heute + timedelta(days=stufe.frist),
        "text": stufe.text_fuer(rechnung),
        "gebuehr": stufe.gebuehr,
        "zinsen": stufe.zinsen,
        "pauschale": False,
    }
    form = MahnungForm(request.POST or None, initial=vorgabe)
    gueltig = request.method == "POST" and form.is_valid()
    werte = form.cleaned_data if gueltig else vorgabe
    aufstellung = mahnen.berechnen(
        rechnung,
        stufe.stufe,
        werte["datum"],
        werte["gebuehr"],
        werte["zinsen"],
        werte["pauschale"],
    )
    vorschau = []
    if gueltig and request.POST.get("aktion") == "erstellen":
        if aufstellung["fehler"]:
            for meldung in aufstellung["fehler"]:
                messages.error(request, meldung)
        else:
            try:
                mahnung = mahnen.erstellen(rechnung, firma, stufe.stufe, **werte)
            except Exception:
                logger.exception("Mahnung erstellen fehlgeschlagen")
                messages.error(request, "Das PDF konnte nicht erzeugt werden.")
            else:
                messages.success(
                    request, f"{mahnung} ist erstellt und als PDF abgelegt."
                )
                return redirect("zahlungen:mahnung", mahnung.pk)
    elif gueltig:
        b = mahnen.beleg_daten(
            rechnung,
            firma,
            stufe.stufe,
            werte["datum"],
            werte["frist"],
            werte["text"],
            aufstellung,
        )
        vorschau = seitenbilder(mahnen.pdf(b, entwurf=True, logo=bytes(firma.logo)))
    return render(
        request,
        "zahlungen/mahnen.html",
        {
            "bereich": "offene-posten",
            "rechnung": rechnung,
            "stufe": stufe,
            "form": form,
            "aufstellung": aufstellung,
            "vorschau": vorschau,
            "basiszins_veraltet": Basiszins.veraltet(),
        },
    )


def mahnung(request, pk):
    mahnung = get_object_or_404(
        Mahnung.objects.select_related("rechnung__kontakt"), pk=pk
    )
    firma = Firmendaten.laden()
    form = VersandForm(
        request.POST or None, initial=mahnen.mail_vorschlag(mahnung, firma)
    )
    if request.method == "POST" and form.is_valid() and firma.mail_bereit:
        try:
            versand.senden(mahnung, firma, **form.cleaned_data)
        except (smtplib.SMTPException, OSError) as fehler:
            logger.warning("Versand fehlgeschlagen: %s", fehler)
            messages.error(request, versand.fehlertext(fehler))
        else:
            messages.success(
                request, f"{mahnung} wurde an {mahnung.versendet_an} gesendet."
            )
            return redirect("zahlungen:mahnung", mahnung.pk)
    pfad = Path(settings.DATA_DIR) / mahnung.datei
    letzte = mahnung.rechnung.mahnungen.order_by("-stufe").first()
    return render(
        request,
        "zahlungen/mahnung.html",
        {
            "bereich": "offene-posten",
            "mahnung": mahnung,
            "firma": firma,
            "form": form,
            "loeschbar": letzte == mahnung,
            "seiten": seitenbilder(pfad.read_bytes()) if pfad.is_file() else [],
        },
    )


# Der PDF-Betrachter des Browsers scheitert an der strengen Richtlinie der Seiten.
@csp_override({})
def mahnung_pdf(request, pk):
    mahnung = get_object_or_404(Mahnung.objects.select_related("rechnung"), pk=pk)
    pfad = Path(settings.DATA_DIR) / mahnung.datei
    if not pfad.is_file():
        raise Http404("Die Datei fehlt im Archiv.")
    return FileResponse(
        pfad.open("rb"),
        content_type="application/pdf",
        filename=mahnung.dateiname,
        as_attachment="herunterladen" in request.GET,
    )


@require_POST
def mahnung_loeschen(request, pk):
    """Nur das letzte Schreiben, damit keine Stufe fehlt; gedacht für Versehen."""
    mahnung = get_object_or_404(Mahnung.objects.select_related("rechnung"), pk=pk)
    rechnung = mahnung.rechnung
    if rechnung.mahnungen.order_by("-stufe").first() != mahnung:
        raise Http404("Nur das letzte Schreiben lässt sich löschen.")
    (Path(settings.DATA_DIR) / mahnung.datei).unlink(missing_ok=True)
    mahnung.delete()
    messages.success(request, f"{mahnung.bezeichnung} gelöscht.")
    return redirect("invoicing:bearbeiten", rechnung.pk)


@nur_inhaber
def einstellungen(request):
    aktion = request.POST.get("aktion") if request.method == "POST" else None
    stufen = Mahnstufe.alle()
    formulare = [
        MahnstufeForm(
            request.POST if aktion == "stufen" else None,
            instance=stufe,
            prefix=f"s{nummer}",
        )
        for nummer, stufe in stufen.items()
    ]
    zins_form = BasiszinsForm(request.POST if aktion == "basiszins" else None)
    if aktion == "stufen" and all(f.is_valid() for f in formulare):
        for f in formulare:
            f.save()
        messages.success(request, "Mahnstufen gespeichert.")
        return redirect("zahlungen:einstellungen")
    if aktion == "basiszins" and zins_form.is_valid():
        eintrag = zins_form.save()
        messages.success(request, f"Basiszinssatz {eintrag} eingetragen.")
        return redirect("zahlungen:einstellungen")
    if aktion:
        messages.error(request, "Bitte die markierten Angaben prüfen.")
    return render(
        request,
        "zahlungen/einstellungen.html",
        {
            "bereich": "offene-posten",
            "stufen": [(STUFEN[n], f) for n, f in zip(stufen, formulare, strict=True)],
            "zins_form": zins_form,
            "basiszinsen": Basiszins.objects.all()[:8],
            "veraltet": Basiszins.veraltet(),
        },
    )


@nur_inhaber
@require_POST
def basiszins_loeschen(request, pk):
    eintrag = get_object_or_404(Basiszins, pk=pk)
    eintrag.delete()
    messages.success(request, f"Basiszinssatz {eintrag} gelöscht.")
    return redirect("zahlungen:einstellungen")
