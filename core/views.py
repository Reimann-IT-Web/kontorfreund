import threading
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from angebote.models import Angebot
from archive import fristen
from backups import sicherung
from contacts.models import Kontakt
from invoicing.models import Rechnung
from konten.rechte import nur_inhaber
from wiedervorlagen.models import DEMNAECHST, Wiedervorlage
from zahlungen import mahnen
from zahlungen.models import Mahnstufe

from . import firmen
from . import umsatz as umsaetze
from .forms import FirmendatenForm
from .hilfe import THEMEN
from .models import Firmendaten


def start(request):
    firma = Firmendaten.laden()
    kontakte = Kontakt.objects.filter(archiviert=False)
    anzahl = kontakte.count()
    jahr = date.today().year
    umsatz = umsaetze.umsatz(jahr)
    offen = [r for r in mahnen.posten() if r.offen > 0]
    ueberfaellig = [r for r in offen if r.ueberfaellig]
    mahnstufe = dict(mahnen.vorschlaege(ueberfaellig, Mahnstufe.alle()))
    for r in ueberfaellig:
        r.mahnstufe = mahnstufe.get(r)
    heute = date.today()
    aufgaben = Wiedervorlage.offen_fuer(request.user).select_related(
        "kontakt", "zustaendig", "angebot", "rechnung"
    )
    return render(
        request,
        "core/start.html",
        {
            "bereich": "start",
            "anzahl_kontakte": anzahl,
            "erste_schritte": not (firma.vollstaendig and anzahl),
            "zuletzt": kontakte.order_by("-geaendert")[:5],
            # Offene Posten: Summen in der Seitenleiste, Überfälliges in der Arbeitsliste.
            "posten": bool(offen)
            or Rechnung.objects.filter(status=Rechnung.Status.FESTGESCHRIEBEN).exists(),
            "summe_offen": sum((r.offen for r in offen), Decimal("0.00")),
            "summe_ueberfaellig": sum((r.offen for r in ueberfaellig), Decimal("0.00")),
            "anzahl_offen": len(offen),
            "ueberfaellig": sorted(ueberfaellig, key=lambda r: r.faellig),
            # Fertig, aber noch ohne Antwort; die zuerst ablaufen, stehen oben.
            "offene_angebote": sorted(
                Angebot.objects.filter(
                    status=Angebot.Status.FERTIG, antwort=""
                ).select_related("kontakt"),
                key=lambda a: a.gueltig_bis,
            ),
            "wiedervorlagen": aufgaben.filter(faellig__lte=heute),
            "demnaechst": aufgaben.filter(
                faellig__gt=heute, faellig__lte=heute + timedelta(days=DEMNAECHST)
            ),
            "umsatz": umsatz,
            "grenze": umsaetze.VORJAHR,
            "grenze_prozent": round(umsatz / umsaetze.VORJAHR * 100),
            "grenz_hinweise": umsaetze.hinweise(jahr) if firma.kleinunternehmer else [],
            "naechstes_jahr": jahr + 1,
            "fristen": fristen.hinweis() if request.user.ist_inhaber else None,
        },
    )


@nur_inhaber
def einstellungen(request):
    form = FirmendatenForm(
        request.POST or None, request.FILES or None, instance=Firmendaten.laden()
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Firmendaten gespeichert.")
        return redirect("core:einstellungen")
    return render(
        request, "core/einstellungen.html", {"bereich": "einstellungen", "form": form}
    )


def hilfe(request, thema=None):
    if thema is None:
        return render(
            request, "core/hilfe/start.html", {"bereich": "hilfe", "themen": THEMEN}
        )
    nr = next((i for i, t in enumerate(THEMEN) if t["slug"] == thema), None)
    if nr is None:
        raise Http404
    return render(
        request,
        f"core/hilfe/{thema}.html",
        {
            "bereich": "hilfe",
            "thema": THEMEN[nr],
            "zurueck": THEMEN[nr - 1] if nr else None,
            "weiter": THEMEN[nr + 1] if nr + 1 < len(THEMEN) else None,
        },
    )


# ---------- Mehrere Firmen (core/firmen.py) ----------


def _anmeldung_noetig(request):
    """Firmen wechseln geht auch vor der Anmeldung, denn jede Firma hat eigene Konten;
    im Netzwerk nur angemeldet."""
    return settings.NETZWERK and not request.user.is_authenticated


@login_not_required
def firmen_liste(request):
    if _anmeldung_noetig(request):
        return redirect_to_login(request.get_full_path())
    return render(
        request,
        "core/firmen.html",
        {
            "bereich": "firmen",
            "firmen": firmen.alle(settings.HAUPTORDNER),
            "offen": settings.FIRMA,
            "rahmen": "base.html"
            if request.user.is_authenticated
            else "konten/schlicht.html",
        },
    )


@login_not_required
@require_POST
def firma_oeffnen(request):
    if _anmeldung_noetig(request):
        return redirect_to_login(reverse("core:firmen"))
    alle = {f.kennung: f for f in firmen.alle(settings.HAUPTORDNER)}
    kennung = request.POST.get("firma", "")
    if kennung not in alle:
        raise Http404
    if kennung == settings.FIRMA:
        return redirect("core:start")
    return _wechseln(request, alle[kennung])


@require_POST
@nur_inhaber
def firma_anlegen(request):
    kennung = firmen.anlegen(settings.HAUPTORDNER)
    return _wechseln(
        request,
        firmen.Firma(kennung, firmen.ordner(settings.HAUPTORDNER, kennung), ""),
        neu=True,
    )


@require_POST
@nur_inhaber
def firma_entfernen(request):
    kennung = request.POST.get("firma", "")
    try:
        if kennung == settings.FIRMA:
            raise ValueError
        firmen.entfernen(settings.HAUPTORDNER, kennung)
    except ValueError:
        messages.error(
            request,
            "Entfernen lässt sich nur eine Firma, in der noch niemand ein Konto angelegt hat.",
        )
    else:
        messages.success(request, "Die leere Firma ist entfernt.")
    return redirect("core:firmen")


def _wechseln(request, firma, neu=False):
    firmen.waehlen(settings.HAUPTORDNER, firma.kennung)
    if not settings.NEUSTART:
        messages.info(
            request,
            f"{firma.anzeigename} öffnet sich beim nächsten Start von Kontorfreund.",
        )
        return redirect("core:firmen")
    neu_starten()
    return render(request, "core/wechseln.html", {"firma": firma, "neu": neu})


def neu_starten():
    """Den Server beenden, sobald die Antwort draußen ist. Das Startprogramm
    (kontorfreund.py) startet ihn mit der gewählten Firma neu."""
    threading.Timer(1, sicherung.beenden, args=[firmen.WECHSELN]).start()


@login_not_required
def firma_offen(request):
    """Welche Firma der Server geöffnet hat; die Seite zum Wechseln wartet darauf."""
    return HttpResponse(settings.FIRMA or "1", content_type="text/plain; charset=utf-8")
