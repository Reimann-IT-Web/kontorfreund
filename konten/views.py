"""Anmelden, erstes Konto einrichten, eigenes Konto und Benutzerverwaltung (K-5)."""

import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import Firmendaten
from protokoll.erfassen import anmeldung, eintragen
from protokoll.models import Eintrag

from . import sitzungen, totp
from .forms import (
    AnmeldenForm,
    BenutzerForm,
    CodeForm,
    EinrichtenForm,
    EinschaltenForm,
    KennwortAendernForm,
    KennwortBestaetigenForm,
    NeuesKennwortForm,
    PrueferForm,
    PruefungForm,
)
from .models import FEHLVERSUCHE, Benutzer
from .rechte import nur_inhaber

logger = logging.getLogger(__name__)

# Kennwort stimmt, der Code aus der App fehlt noch: wer, wohin danach und seit wann.
AUSSTEHEND = "anmeldung_ausstehend"
CODE_FRIST = 300  # Sekunden
# Geheimnis für die Zwei-Faktor-Anmeldung, bis der erste Code es bestätigt.
NEUES_GEHEIMNIS = "zwei_faktor_geheimnis"
# Wechseln lässt sich nur zwischen diesen; ein Prüfer-Konto bleibt eines.
ROLLEN = (Benutzer.Rolle.INHABER, Benutzer.Rolle.MITARBEITER)


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


def _bestaetigung_falsch(request, form, feld, grund):
    """Ein falsches Kennwort zum Bestätigen zählt wie bei der Anmeldung (ASVS 6.3.1).
    Nach dem letzten Fehlversuch ist man abgemeldet; dann die Weiterleitung, sonst None."""
    if not form.data.get(form.add_prefix(feld)) or feld not in form.errors:
        return None
    benutzer = request.user
    _fehlversuch(benutzer, "", benutzer.email, grund)
    if not benutzer.gesperrt:
        return None
    sitzungen.abmelden(request, "nach Fehlversuchen gesperrt")
    messages.error(request, _gesperrt(benutzer))
    return redirect("konten:anmelden")


def _zwei_faktor_vermerken(benutzer, vorher, nachher):
    eintragen(
        Eintrag.Aktion.GEAENDERT, benutzer, [["Zwei-Faktor-Anmeldung", vorher, nachher]]
    )


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
            if not geprueft.zugang_offen:
                anmeldung(
                    Eintrag.Aktion.FEHLVERSUCH, email, geprueft, "Zugang abgelaufen"
                )
                form.add_error(
                    None,
                    "Der Zugang für die Betriebsprüfung ist am "
                    f"{geprueft.zugang_bis:%d.%m.%Y} abgelaufen.",
                )
            elif not geprueft.zwei_faktor:
                return _anmelden(request, geprueft, _ziel(request))
            else:
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
    sitzungen.abmelden(request)
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


def _kennwort_aendern(request, form):
    """Neues Kennwort speichern; alle anderen Sitzungen enden, diese bleibt."""
    benutzer = request.user
    benutzer.set_password(form.cleaned_data["kennwort"])
    benutzer.kennwort_vorlaeufig = False
    benutzer.save()
    update_session_auth_hash(request, benutzer)


def konto(request):
    form = KennwortAendernForm(request.POST or None, benutzer=request.user)
    if request.method == "POST":
        if form.is_valid():
            _kennwort_aendern(request, form)
            messages.success(
                request,
                "Ihr Kennwort ist geändert. Auf anderen Geräten sind Sie abgemeldet.",
            )
            return redirect("konten:konto")
        if antwort := _bestaetigung_falsch(
            request, form, "bisher", "Bisheriges Kennwort falsch"
        ):
            return antwort
    return render(
        request,
        "konten/konto.html",
        {
            "bereich": "konto",
            "form": form,
            "aus_form": KennwortBestaetigenForm(benutzer=request.user),
            "geraete_form": KennwortBestaetigenForm(
                benutzer=request.user, auto_id="geraete_%s"
            ),
            "geraete": sitzungen.liste(request.user, request.session.session_key),
            "abmelden_nach": settings.SESSION_COOKIE_AGE // 3600,
            "hoechstens": sitzungen.HOECHSTENS // 3600,
            "pflicht": _pflicht(request.user),
        },
    )


def kennwort(request):
    """Eigenes Kennwort statt des vom Inhaber vergebenen; für Prüfer der einzige Weg,
    es zu ändern, weil sie „Mein Konto“ nicht sehen."""
    benutzer = request.user
    if not (benutzer.kennwort_vorlaeufig or benutzer.ist_pruefer):
        return redirect("konten:konto")
    vorlaeufig = benutzer.kennwort_vorlaeufig
    form = KennwortAendernForm(request.POST or None, benutzer=benutzer)
    if vorlaeufig:
        form.fields["bisher"].label = "Kennwort, mit dem Sie sich eben angemeldet haben"
    if request.method == "POST":
        if form.is_valid():
            _kennwort_aendern(request, form)
            messages.success(
                request,
                "Ihr eigenes Kennwort ist gespeichert."
                if vorlaeufig
                else "Ihr Kennwort ist geändert.",
            )
            return redirect("core:start")
        if antwort := _bestaetigung_falsch(
            request, form, "bisher", "Bisheriges Kennwort falsch"
        ):
            return antwort
    return render(
        request, "konten/kennwort.html", {"form": form, "vorlaeufig": vorlaeufig}
    )


@require_POST
def geraete_abmelden(request):
    """Auf allen anderen Geräten abmelden, nach Bestätigung mit dem Kennwort (ASVS 7.5.2)."""
    form = KennwortBestaetigenForm(
        request.POST, benutzer=request.user, auto_id="geraete_%s"
    )
    if form.is_valid():
        anzahl = sitzungen.beenden(request.user, ausser=request.session.session_key)
        anmeldung(
            Eintrag.Aktion.ABMELDUNG,
            str(request.user),
            request.user,
            f"auf anderen Geräten ({anzahl})",
        )
        messages.success(
            request,
            "Sie sind auf allen anderen Geräten abgemeldet."
            if anzahl
            else "Sie waren auf keinem anderen Gerät angemeldet.",
        )
    elif antwort := _bestaetigung_falsch(
        request, form, "kennwort", "Kennwort zum Abmelden der Geräte falsch"
    ):
        return antwort
    else:
        messages.error(request, form.errors["kennwort"][0])
    return redirect(reverse("konten:konto") + "#geraete")


def zwei_faktor(request):
    benutzer = request.user
    if benutzer.zwei_faktor:
        return redirect("konten:konto")
    geheimnis = request.session.setdefault(NEUES_GEHEIMNIS, totp.neues_geheimnis())
    form = EinschaltenForm(request.POST or None, benutzer=benutzer)
    if request.method == "POST" and form.is_valid():
        if schritt := totp.pruefen(geheimnis, form.cleaned_data["code"]):
            benutzer.totp_geheimnis = geheimnis
            benutzer.totp_schritt = schritt
            benutzer.save(update_fields=["totp_geheimnis", "totp_schritt"])
            update_session_auth_hash(request, benutzer)
            del request.session[NEUES_GEHEIMNIS]
            _zwei_faktor_vermerken(benutzer, "aus", "ein")
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
    elif request.method == "POST" and (
        antwort := _bestaetigung_falsch(
            request,
            form,
            "kennwort",
            "Kennwort beim Einrichten der Zwei-Faktor-Anmeldung falsch",
        )
    ):
        return antwort
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
        update_session_auth_hash(request, request.user)
        _zwei_faktor_vermerken(request.user, "ein", "aus")
        messages.success(request, "Die Zwei-Faktor-Anmeldung ist ausgeschaltet.")
    elif antwort := _bestaetigung_falsch(
        request,
        form,
        "kennwort",
        "Kennwort beim Ausschalten der Zwei-Faktor-Anmeldung falsch",
    ):
        return antwort
    else:
        messages.error(request, form.errors["kennwort"][0])
    return redirect("konten:konto")


@nur_inhaber
def benutzer(request):
    pruefer = request.POST.get("aktion") == "pruefer"
    form = BenutzerForm(None if pruefer else request.POST or None)
    pruefer_form = PrueferForm(request.POST if pruefer else None, prefix="p")
    pruefung_form = PruefungForm(request.POST if pruefer else None, prefix="p")
    # Beide prüfen, damit alle Fehler auf einmal erscheinen.
    if pruefer and pruefer_form.is_valid() & pruefung_form.is_valid():
        konto = pruefer_form.cleaned_data
        neu = Benutzer.objects.create_user(
            konto["email"],
            konto["kennwort"],
            name=konto["name"],
            rolle=Benutzer.Rolle.PRUEFER,
            kennwort_vorlaeufig=True,
            **pruefung_form.cleaned_data,
        )
        messages.success(
            request,
            f"Der Zugang für {neu.name} ist angelegt und gilt bis zum "
            f"{neu.zugang_bis:%d.%m.%Y}. Geben Sie E-Mail-Adresse und Kennwort "
            "persönlich weiter; bei der ersten Anmeldung wählt der Prüfer ein eigenes.",
        )
        return redirect("konten:benutzer")
    if not pruefer and request.method == "POST" and form.is_valid():
        daten = form.cleaned_data
        neu = Benutzer.objects.create_user(
            daten["email"],
            daten["kennwort"],
            name=daten["name"],
            rolle=daten["rolle"],
            kennwort_vorlaeufig=True,
        )
        messages.success(
            request,
            f"Das Konto für {neu.name} ist angelegt. Geben Sie das erste Kennwort "
            f"persönlich weiter; bei der ersten Anmeldung wählt {neu.name} ein eigenes.",
        )
        return redirect("konten:benutzer")
    return render(
        request,
        "konten/benutzer.html",
        {
            "bereich": "einstellungen",
            "konten": Benutzer.objects.all(),
            "form": form,
            "pruefer_form": pruefer_form,
            "pruefung_form": pruefung_form,
            "pruefer_offen": pruefer,
        },
    )


@nur_inhaber
def benutzer_bearbeiten(request, pk):
    konto = get_object_or_404(Benutzer, pk=pk)
    selbst = konto == request.user
    aktion = request.POST.get("aktion")
    kennwort_form = NeuesKennwortForm(
        request.POST if aktion == "kennwort" else None, benutzer=konto
    )
    pruefung_form = (
        PruefungForm(request.POST if aktion == "pruefung" else None, instance=konto)
        if konto.ist_pruefer
        else None
    )
    if request.method == "POST":
        if aktion == "kennwort" and kennwort_form.is_valid():
            konto.set_password(kennwort_form.cleaned_data["kennwort"])
            konto.kennwort_vorlaeufig = not selbst
            konto.save()
            konto.entsperren()
            if selbst:
                update_session_auth_hash(request, konto)
                meldung = "Ihr Kennwort ist neu gesetzt."
            else:
                meldung = (
                    f"Das Kennwort von {konto.name} ist neu gesetzt und alle Geräte "
                    f"sind abgemeldet. Bei der nächsten Anmeldung wählt {konto.name} "
                    "ein eigenes."
                )
        elif aktion == "pruefung" and pruefung_form and pruefung_form.is_valid():
            pruefung_form.save()
            meldung = (
                f"Der Zugang für {konto.name} gilt bis zum {konto.zugang_bis:%d.%m.%Y}."
            )
        elif (
            aktion == "rolle"
            and not selbst
            and not konto.ist_pruefer
            and request.POST.get("rolle") in ROLLEN
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
        elif aktion == "zwei_faktor" and konto.zwei_faktor:
            konto.totp_geheimnis = ""
            konto.save(update_fields=["totp_geheimnis"])
            if selbst:
                update_session_auth_hash(request, konto)
            _zwei_faktor_vermerken(konto, "ein", "zurückgesetzt")
            meldung = f"Die Zwei-Faktor-Anmeldung von {konto.name} ist zurückgesetzt."
        elif aktion == "abmelden" and not selbst:
            anzahl = sitzungen.beenden(konto)
            anmeldung(
                Eintrag.Aktion.ABMELDUNG,
                str(konto),
                konto,
                f"vom Inhaber auf allen Geräten ({anzahl})",
            )
            meldung = f"{konto.name} ist auf allen Geräten abgemeldet."
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
            "pruefung_form": pruefung_form,
            "rollen": [(r, Benutzer.Rolle(r).label) for r in ROLLEN],
            "geraete": [] if selbst else sitzungen.liste(konto),
        },
    )
