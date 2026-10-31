"""Anmelden, erstes Konto einrichten, eigenes Konto und Benutzerverwaltung (K-5)."""

import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import Firmendaten
from protokoll.erfassen import anmeldung
from protokoll.models import Eintrag

from . import totp
from .forms import (
    AnmeldenForm,
    BenutzerForm,
    CodeForm,
    EinrichtenForm,
    KennwortAendernForm,
    KennwortBestaetigenForm,
    NeuesKennwortForm,
)
from .models import FEHLVERSUCHE, Benutzer
from .rechte import nur_inhaber

logger = logging.getLogger(__name__)

# Kennwort stimmt, der Code aus der App fehlt noch: wer, wohin danach und seit wann.
AUSSTEHEND = "anmeldung_ausstehend"
CODE_FRIST = 300  # Sekunden
# Geheimnis für die Zwei-Faktor-Anmeldung, bis der erste Code es bestätigt.
NEUES_GEHEIMNIS = "zwei_faktor_geheimnis"


def _ziel(request):
    weiter = request.POST.get("next") or request.GET.get("next", "")
    if url_has_allowed_host_and_scheme(
        weiter, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return weiter
    return reverse("core:start")


def _gesperrt(benutzer):
    bis = timezone.localtime(benutzer.gesperrt_bis)
    return (
        f"Nach {FEHLVERSUCHE} Fehlversuchen ist die Anmeldung für dieses Konto "
        f"bis {bis:%H:%M} Uhr gesperrt."
    )


def _anmelden(request, benutzer, ziel):
    benutzer.entsperren()
    login(request, benutzer, backend="django.contrib.auth.backends.ModelBackend")
    logger.info("Angemeldet: %s", benutzer.email)
    anmeldung(Eintrag.Aktion.ANMELDUNG, str(benutzer), benutzer, benutzer.email)
    return redirect(ziel)


def _fehlversuch(benutzer, text, email, grund):
    anmeldung(Eintrag.Aktion.FEHLVERSUCH, email, benutzer, grund)
    if not benutzer:
        return text
    benutzer.fehlversuch()
    return _gesperrt(benutzer) if benutzer.gesperrt else text


@login_not_required
def anmelden(request):
    if not Benutzer.objects.exists():
        return redirect("konten:einrichten")
    if request.user.is_authenticated:
        return redirect(_ziel(request))
    form = AnmeldenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        benutzer = Benutzer.objects.filter(email__iexact=email, is_active=True).first()
        if benutzer and benutzer.gesperrt:
            anmeldung(Eintrag.Aktion.FEHLVERSUCH, email, benutzer, "Konto gesperrt")
            form.add_error(None, _gesperrt(benutzer))
        elif geprueft := authenticate(
            request, username=email, password=form.cleaned_data["kennwort"]
        ):
            if not geprueft.zwei_faktor:
                return _anmelden(request, geprueft, _ziel(request))
            request.session[AUSSTEHEND] = {
                "pk": geprueft.pk,
                "ziel": _ziel(request),
                "zeit": time.time(),
            }
            return redirect("konten:code")
        else:
            logger.warning("Anmeldung fehlgeschlagen: %s", email)
            form.add_error(
                None,
                _fehlversuch(
                    benutzer,
                    "E-Mail-Adresse oder Kennwort stimmt nicht.",
                    email,
                    "Kennwort falsch" if benutzer else "Unbekannte E-Mail-Adresse",
                ),
            )
    return render(
        request,
        "konten/anmelden.html",
        {"form": form, "weiter": request.GET.get("next", "")},
    )


@login_not_required
def code(request):
    ausstehend = request.session.get(AUSSTEHEND) or {}
    benutzer = Benutzer.objects.filter(pk=ausstehend.get("pk"), is_active=True).first()
    if not benutzer or time.time() - ausstehend["zeit"] > CODE_FRIST:
        request.session.pop(AUSSTEHEND, None)
        return redirect("konten:anmelden")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if benutzer.gesperrt:
            anmeldung(
                Eintrag.Aktion.FEHLVERSUCH, benutzer.email, benutzer, "Konto gesperrt"
            )
            form.add_error(None, _gesperrt(benutzer))
        elif schritt := totp.pruefen(
            benutzer.totp_geheimnis, form.cleaned_data["code"], benutzer.totp_schritt
        ):
            benutzer.totp_schritt = schritt
            benutzer.save(update_fields=["totp_schritt"])
            del request.session[AUSSTEHEND]
            return _anmelden(request, benutzer, ausstehend["ziel"])
        else:
            logger.warning("Falscher Code bei der Anmeldung: %s", benutzer.email)
            form.add_error(
                None,
                _fehlversuch(
                    benutzer,
                    "Der Code stimmt nicht. Geben Sie den aktuellen aus Ihrer App ein.",
                    benutzer.email,
                    "Code der Zwei-Faktor-Anmeldung falsch",
                ),
            )
    return render(request, "konten/code.html", {"form": form})


@require_POST
def abmelden(request):
    logout(request)
    messages.success(request, "Sie sind abgemeldet.")
    return redirect("konten:anmelden")


@login_not_required
def einrichten(request):
    """Erster Start: das Konto des Inhabers. Danach gibt es diese Seite nicht mehr."""
    if Benutzer.objects.exists():
        return redirect("konten:anmelden")
    firma = Firmendaten.laden()
    form = EinrichtenForm(
        request.POST or None, initial={"name": firma.inhaber, "email": firma.email}
    )
    if request.method == "POST" and form.is_valid():
        daten = form.cleaned_data
        benutzer = Benutzer.objects.create_user(
            daten["email"],
            daten["kennwort"],
            name=daten["name"],
            rolle=Benutzer.Rolle.INHABER,
        )
        messages.success(request, "Ihr Konto ist angelegt.")
        ziel = "core:start" if firma.vollstaendig else "core:einstellungen"
        return _anmelden(request, benutzer, reverse(ziel))
    return render(request, "konten/einrichten.html", {"form": form})


def _pflicht(benutzer):
    return settings.NETZWERK and benutzer.ist_inhaber


def konto(request):
    form = KennwortAendernForm(request.POST or None, benutzer=request.user)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["kennwort"])
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, "Ihr Kennwort ist geändert.")
        return redirect("konten:konto")
    return render(
        request,
        "konten/konto.html",
        {
            "bereich": "konto",
            "form": form,
            "aus_form": KennwortBestaetigenForm(benutzer=request.user),
            "pflicht": _pflicht(request.user),
        },
    )


def zwei_faktor(request):
    benutzer = request.user
    if benutzer.zwei_faktor:
        return redirect("konten:konto")
    geheimnis = request.session.setdefault(NEUES_GEHEIMNIS, totp.neues_geheimnis())
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if schritt := totp.pruefen(geheimnis, form.cleaned_data["code"]):
            benutzer.totp_geheimnis = geheimnis
            benutzer.totp_schritt = schritt
            benutzer.save(update_fields=["totp_geheimnis", "totp_schritt"])
            del request.session[NEUES_GEHEIMNIS]
            logger.info("Zwei-Faktor-Anmeldung eingeschaltet: %s", benutzer.email)
            messages.success(
                request,
                "Die Zwei-Faktor-Anmeldung ist eingeschaltet. Ab jetzt fragt "
                f"{settings.PRODUCT_NAME} nach dem Kennwort auch nach dem Code aus der App.",
            )
            return redirect("konten:konto")
        form.add_error(
            "code",
            "Der Code passt nicht. Nehmen Sie den aktuellen aus der App und prüfen "
            "Sie, ob die Uhrzeit auf dem Telefon stimmt.",
        )
    adresse = totp.einrichtungsadresse(geheimnis, benutzer.email, settings.PRODUCT_NAME)
    return render(
        request,
        "konten/zwei_faktor.html",
        {
            "bereich": "konto",
            "form": form,
            "qr": totp.qr_bild(adresse),
            "geheimnis": " ".join(geheimnis[i : i + 4] for i in range(0, 32, 4)),
            "pflicht": _pflicht(benutzer),
        },
    )


@require_POST
def zwei_faktor_aus(request):
    if _pflicht(request.user):
        raise PermissionDenied
    form = KennwortBestaetigenForm(request.POST, benutzer=request.user)
    if form.is_valid():
        request.user.totp_geheimnis = ""
        request.user.save(update_fields=["totp_geheimnis"])
        logger.info("Zwei-Faktor-Anmeldung ausgeschaltet: %s", request.user.email)
        messages.success(request, "Die Zwei-Faktor-Anmeldung ist ausgeschaltet.")
    else:
        messages.error(request, form.errors["kennwort"][0])
    return redirect("konten:konto")


@nur_inhaber
def benutzer(request):
    form = BenutzerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        daten = form.cleaned_data
        neu = Benutzer.objects.create_user(
            daten["email"], daten["kennwort"], name=daten["name"], rolle=daten["rolle"]
        )
        messages.success(
            request,
            f"Das Konto für {neu.name} ist angelegt. Geben Sie das erste Kennwort "
            "persönlich weiter; ändern lässt es sich unter „Mein Konto“.",
        )
        return redirect("konten:benutzer")
    return render(
        request,
        "konten/benutzer.html",
        {"bereich": "einstellungen", "konten": Benutzer.objects.all(), "form": form},
    )


@nur_inhaber
def benutzer_bearbeiten(request, pk):
    konto = get_object_or_404(Benutzer, pk=pk)
    selbst = konto == request.user
    aktion = request.POST.get("aktion")
    kennwort_form = NeuesKennwortForm(
        request.POST if aktion == "kennwort" else None, benutzer=konto
    )
    if request.method == "POST":
        if aktion == "kennwort" and kennwort_form.is_valid():
            konto.set_password(kennwort_form.cleaned_data["kennwort"])
            konto.save()
            konto.entsperren()
            meldung = f"Das Kennwort von {konto.name} ist neu gesetzt."
        elif (
            aktion == "rolle"
            and not selbst
            and request.POST.get("rolle") in Benutzer.Rolle
        ):
            konto.rolle = request.POST["rolle"]
            konto.save(update_fields=["rolle"])
            meldung = f"{konto.name} ist jetzt {konto.get_rolle_display()}."
        elif aktion == "zugang" and not selbst:
            konto.is_active = not konto.is_active
            konto.save(update_fields=["is_active"])
            meldung = (
                f"{konto.name} kann sich wieder anmelden."
                if konto.is_active
                else f"{konto.name} kann sich nicht mehr anmelden."
            )
        elif aktion == "entsperren":
            konto.entsperren()
            meldung = f"Die Sperre für {konto.name} ist aufgehoben."
        elif aktion == "zwei_faktor":
            konto.totp_geheimnis = ""
            konto.save(update_fields=["totp_geheimnis"])
            meldung = f"Die Zwei-Faktor-Anmeldung von {konto.name} ist zurückgesetzt."
        else:
            meldung = None
        if meldung:
            logger.info(
                "Benutzer %s geändert (%s) von %s",
                konto.email,
                aktion,
                request.user.email,
            )
            messages.success(request, meldung)
            return redirect("konten:benutzer_bearbeiten", konto.pk)
    return render(
        request,
        "konten/benutzer_bearbeiten.html",
        {
            "bereich": "einstellungen",
            "konto": konto,
            "selbst": selbst,
            "kennwort_form": kennwort_form,
            "rollen": Benutzer.Rolle.choices,
        },
    )
