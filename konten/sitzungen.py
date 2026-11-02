"""Sitzungen: angemeldete Geräte ansehen und beenden, Höchstdauer, Abmelden mit Vermerk.

Die Sitzungen liegen in der Datenbank (django.contrib.sessions). Beim Anmelden merkt sich
die Sitzung Zeitpunkt und Browser (`merken`). Nach HOECHSTENS meldet sich jeder neu an,
auch wer ständig arbeitet; ohne Anfrage endet eine Sitzung schon nach
SESSION_COOKIE_AGE (OWASP ASVS 7.3). Ein neues Kennwort oder eine geänderte
Zwei-Faktor-Anmeldung beendet alle übrigen Sitzungen (Benutzer._get_session_auth_hash).
"""

import time
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, logout
from django.contrib.auth.views import redirect_to_login
from django.contrib.sessions.models import Session
from django.utils import timezone

from protokoll.erfassen import anmeldung
from protokoll.models import Eintrag

HOECHSTENS = 12 * 3600  # Sekunden seit der Anmeldung
SEIT = "angemeldet_um"
GERAET = "geraet"

BROWSER = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
SYSTEME = (
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Windows", "Windows"),
    ("Mac OS X", "macOS"),
    ("CrOS", "ChromeOS"),
    ("Linux", "Linux"),
)


def geraet(kennung):
    """„Firefox unter Windows“ aus dem User-Agent; genauer muss es nicht sein."""
    browser = next((n for k, n in BROWSER if k in kennung), "Browser")
    system = next((n for k, n in SYSTEME if k in kennung), "")
    return f"{browser} unter {system}" if system else browser


def merken(sender, request, user, **kwargs):
    """Signal user_logged_in: wann und womit angemeldet."""
    request.session[SEIT] = time.time()
    request.session[GERAET] = geraet(request.headers.get("User-Agent", ""))


def abmelden(request, grund=""):
    """Abmelden und im Protokoll vermerken, auch wenn das Programm abmeldet."""
    benutzer = request.user
    logout(request)
    anmeldung(Eintrag.Aktion.ABMELDUNG, str(benutzer), benutzer, grund)


def hoechstdauer(get_response):
    def middleware(request):
        if request.user.is_authenticated:
            # Sitzungen von vor diesem Update kennen den Zeitpunkt nicht: ab jetzt.
            seit = request.session.setdefault(SEIT, time.time())
            if time.time() - seit > HOECHSTENS:
                abmelden(request, f"nach {HOECHSTENS // 3600} Stunden")
                messages.info(
                    request,
                    f"Sie waren {HOECHSTENS // 3600} Stunden angemeldet. "
                    "Bitte melden Sie sich neu an.",
                )
                return redirect_to_login(request.get_full_path())
        return get_response(request)

    return middleware


def liste(benutzer, aktuell=None):
    """Gültige Sitzungen des Benutzers, die aktuelle zuerst, dann die zuletzt aktiven."""
    kennung = benutzer.get_session_auth_hash()
    frist = time.time() - HOECHSTENS
    alle = []
    for sitzung in Session.objects.filter(expire_date__gt=timezone.now()):
        daten = sitzung.get_decoded()
        if (
            daten.get(SESSION_KEY) == str(benutzer.pk)
            and daten.get(HASH_SESSION_KEY) == kennung
            and daten.get(SEIT, time.time()) > frist
        ):
            alle.append(
                {
                    "schluessel": sitzung.session_key,
                    "aktuell": sitzung.session_key == aktuell,
                    "geraet": daten.get(GERAET, "Browser"),
                    "seit": daten.get(SEIT)
                    and timezone.localtime(datetime.fromtimestamp(daten[SEIT], UTC)),
                    # Jede Anfrage verlängert die Sitzung um SESSION_COOKIE_AGE.
                    "zuletzt": sitzung.expire_date
                    - timedelta(seconds=settings.SESSION_COOKIE_AGE),
                }
            )
    return sorted(alle, key=lambda s: (not s["aktuell"], -s["zuletzt"].timestamp()))


def beenden(benutzer, ausser=None):
    """Alle Sitzungen des Benutzers außer `ausser` beenden; gibt ihre Zahl zurück."""
    schluessel = [s["schluessel"] for s in liste(benutzer) if s["schluessel"] != ausser]
    Session.objects.filter(session_key__in=schluessel).delete()
    return len(schluessel)
