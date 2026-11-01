from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from angebote.models import Angebot
from contacts.models import Kontakt
from invoicing.models import Rechnung
from konten.models import Benutzer

from .forms import ErledigenForm, WiedervorlageForm
from .models import DEMNAECHST, VERSCHIEBEN, Wiedervorlage


def gruppen(offen):
    """Offene Wiedervorlagen als [(Überschrift, Liste)]: Überfällig, Heute, Demnächst, Später."""
    heute = date.today()
    bald = heute + timedelta(days=DEMNAECHST)
    einteilung = [
        ("Überfällig", lambda w: w.faellig < heute),
        ("Heute", lambda w: w.faellig == heute),
        ("Demnächst", lambda w: heute < w.faellig <= bald),
        ("Später", lambda w: w.faellig > bald),
    ]
    offen = list(offen)
    return [
        (titel, liste)
        for titel, passt in einteilung
        if (liste := [w for w in offen if passt(w)])
    ]


def _weiter(request):
    """Rücksprung nach dem Speichern, nur innerhalb von Kontorfreund."""
    weiter = request.POST.get("weiter") or request.GET.get("weiter", "")
    if url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}):
        return weiter
    return ""


def _zurueck(request):
    return redirect(_weiter(request) or "wiedervorlagen:liste")


def liste(request):
    erledigt = request.GET.get("zeigen") == "erledigt"
    alle = request.GET.get("wer") == "alle"
    eintraege = Wiedervorlage.objects.select_related(
        "kontakt", "zustaendig", "angebot", "rechnung"
    )
    if not alle:
        eintraege = eintraege.filter(
            Q(zustaendig=request.user) | Q(zustaendig__isnull=True)
        )
    if erledigt:
        eintraege = eintraege.filter(erledigt_am__isnull=False).order_by("-erledigt_am")
    else:
        eintraege = eintraege.filter(erledigt_am__isnull=True)
    return render(
        request,
        "wiedervorlagen/liste.html",
        {
            "bereich": "wiedervorlagen",
            "erledigt": erledigt,
            "alle": alle,
            "mehrere": Benutzer.objects.filter(is_active=True).count() > 1,
            "gruppen": [("Erledigt", list(eintraege[:100]))]
            if erledigt
            else gruppen(eintraege),
            "weiter": request.get_full_path(),
        },
    )


def bearbeiten(request, pk=None):
    w = get_object_or_404(Wiedervorlage, pk=pk) if pk else Wiedervorlage()
    if not pk:
        _vorbelegen(request, w)
    form = WiedervorlageForm(request.POST or None, instance=w)
    if request.method == "POST" and form.is_valid():
        w = form.save(commit=False)
        if not w.kontakt and w.beleg:
            w.kontakt = w.beleg.kontakt
        w.save()
        messages.success(
            request,
            f"Wiedervorlage „{w}“ für {w.faellig:%d.%m.%Y} gespeichert."
            if not pk
            else f"Wiedervorlage „{w}“ gespeichert.",
        )
        return _zurueck(request)
    return render(
        request,
        "wiedervorlagen/formular.html",
        {
            "bereich": "wiedervorlagen",
            "w": w,
            "form": form,
            "erledigen_form": ErledigenForm(),
            "weiter": _weiter(request),
        },
    )


def _vorbelegen(request, w):
    """Neue Wiedervorlage aus Adresse, Angebot, Rechnung oder Eintrag der Historie."""
    w.zustaendig = request.user
    if (nr := request.GET.get("angebot", "")).isdigit():
        w.angebot = get_object_or_404(Angebot, pk=nr)
        w.kontakt = w.angebot.kontakt
    if (nr := request.GET.get("rechnung", "")).isdigit():
        w.rechnung = get_object_or_404(Rechnung, pk=nr)
        w.kontakt = w.rechnung.kontakt
    if (nr := request.GET.get("kontakt", "")).isdigit():
        w.kontakt = get_object_or_404(Kontakt, pk=nr)
    w.titel = request.GET.get("titel", "")[:200]
    if (tage := request.GET.get("in", "")).isdigit():
        w.faellig = date.today() + timedelta(days=min(int(tage), 3650))


@require_POST
def aendern(request, pk):
    """Verschieben, erledigen oder wieder öffnen, direkt aus einer Liste."""
    w = get_object_or_404(Wiedervorlage, pk=pk)
    aktion = request.POST.get("aktion", "")
    if (wohin := request.POST.get("verschieben", "")) in VERSCHIEBEN:
        w.verschieben(wohin)
        messages.success(request, f"„{w}“ ist jetzt am {w.faellig:%d.%m.%Y} fällig.")
    elif aktion == "erledigen" and not w.erledigt:
        w.erledigen(request.user, request.POST.get("ergebnis", "").strip())
        messages.success(
            request,
            f"„{w}“ ist erledigt."
            + (" Sie steht jetzt im Verlauf der Adresse." if w.kontakt else ""),
        )
    elif aktion == "oeffnen" and w.erledigt:
        w.oeffnen()
        messages.success(request, f"„{w}“ ist wieder offen.")
    return _zurueck(request)


@require_POST
def loeschen(request, pk):
    w = get_object_or_404(Wiedervorlage, pk=pk)
    w.delete()
    messages.success(request, f"Wiedervorlage „{w}“ gelöscht.")
    return redirect("wiedervorlagen:liste")
