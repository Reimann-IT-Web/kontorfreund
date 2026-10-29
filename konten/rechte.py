"""Zugriff nach Rolle und die Pflicht zur Zwei-Faktor-Anmeldung im Netzwerk."""

from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse


def nur_inhaber(view):
    """Einstellungen, Datensicherung und Benutzer: Mitarbeiter bekommen 403."""

    @wraps(view)
    def pruefen(request, *args, **kwargs):
        if not request.user.ist_inhaber:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return pruefen


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
