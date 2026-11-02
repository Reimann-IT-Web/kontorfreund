"""Schutz für alle Seiten nach OWASP ASVS (docs/sicherheit.md): nur die nötigen
HTTP-Methoden, nichts im Cache des Browsers, verweigerte Zugriffe im Protokoll."""

from django.http import HttpResponseNotAllowed
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers

from protokoll.erfassen import eintragen
from protokoll.models import Eintrag

METHODEN = ("GET", "HEAD", "POST")


def methoden(get_response):
    """TRACE, PUT, DELETE und alle übrigen braucht das Programm nicht (ASVS 13.4.4)."""

    def middleware(request):
        if request.method not in METHODEN:
            return HttpResponseNotAllowed(METHODEN)
        return get_response(request)

    return middleware


def nicht_speichern(get_response):
    """Seiten und Belege bleiben nicht im Cache des Browsers, auch nicht nach dem
    Abmelden (ASVS 14.3.2). Statische Dateien liefert WhiteNoise vorher aus."""

    def middleware(request):
        antwort = get_response(request)
        add_never_cache_headers(antwort)
        return antwort

    return middleware


def _verweigert(request, grund, vorlage, status=403):
    eintragen(
        Eintrag.Aktion.VERWEIGERT,
        beschreibung=f"{request.method} {request.path} – {grund}"[:300],
    )
    return render(request, vorlage, status=status)


def kein_zugriff(request, exception=None):
    """handler403: Seite für fehlende Rechte; der Versuch kommt ins Protokoll (ASVS 16.3.2)."""
    return _verweigert(request, "keine Berechtigung", "403.html")


def formular_abgelaufen(request, reason=""):
    """CSRF_FAILURE_VIEW: Formular ohne gültigen Sicherheitsschlüssel, etwa von einer
    fremden Seite abgeschickt oder lange offen (ASVS 16.3.3)."""
    return _verweigert(request, f"Formular abgelehnt ({reason})", "403_formular.html")
