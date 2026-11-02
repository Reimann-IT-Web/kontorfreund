"""Zugriff nach Rolle, eigenes Kennwort und die Pflicht zur Zwei-Faktor-Anmeldung im Netzwerk."""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from .sitzungen import abmelden


def nur_inhaber(view):
    """Einstellungen, Datensicherung und Benutzer: Mitarbeiter bekommen 403."""

    @wraps(view)
    def pruefen(request, *args, **kwargs):
        if not request.user.ist_inhaber:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return pruefen


def eigenes_kennwort(get_response):
    """Wer sich mit einem vom Inhaber vergebenen Kennwort anmeldet, wählt zuerst ein
    eigenes; so wird das erste Kennwort nie zum dauerhaften (ASVS 6.4.1)."""

    def middleware(request):
        benutzer = request.user
        if (
            benutzer.is_authenticated
            and benutzer.kennwort_vorlaeufig
            and request.path
            not in (reverse("konten:kennwort"), reverse("konten:abmelden"))
        ):
            return redirect("konten:kennwort")
        return get_response(request)

    return middleware


def zwei_faktor_pflicht(get_response):
    """Inhaber ohne Zwei-Faktor-Anmeldung richten sie im Netzwerkbetrieb zuerst ein."""

    def middleware(request):
        benutzer = request.user
        if (
            settings.NETZWERK
            and benutzer.is_authenticated
            and benutzer.ist_inhaber
            and not benutzer.zwei_faktor
            and request.path
            not in (reverse("konten:zwei_faktor"), reverse("konten:abmelden"))
        ):
            return redirect("konten:zwei_faktor")
        return get_response(request)

    return middleware


LESEN = ("GET", "HEAD")


def nur_lesen(get_response):
    """Prüfer sehen nur den Datenzugriff, schicken nichts ab außer der Abmeldung und dem
    eigenen Kennwort und verlieren den Zugang nach `zugang_bis`, auch mitten in einer
    Sitzung."""

    def middleware(request):
        benutzer = request.user
        if benutzer.is_authenticated and benutzer.ist_pruefer:
            if not benutzer.zugang_offen:
                abmelden(request, "Zugang abgelaufen")
                messages.info(
                    request, "Der Zugang für die Betriebsprüfung ist abgelaufen."
                )
                return redirect("konten:anmelden")
            if request.path in (reverse("konten:abmelden"), reverse("konten:kennwort")):
                pass
            elif not request.path.startswith(reverse("datenzugriff:start")):
                if request.method in LESEN:
                    return redirect("datenzugriff:start")
                raise PermissionDenied
            elif request.method not in LESEN:
                raise PermissionDenied
        return get_response(request)

    return middleware
