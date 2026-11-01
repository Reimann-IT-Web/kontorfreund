from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from konten.rechte import nur_inhaber
from konten.totp import qr_bild

from . import autostart, telegram
from .forms import EinstellungForm
from .models import Einstellung

VERBUNDEN = "Kontorfreund ist verbunden. Hier kommen ab jetzt Ihre Erinnerungen an."
TEST = "Kontorfreund: Testnachricht. So kommen Ihre Erinnerungen an."


@nur_inhaber
def einstellungen(request):
    einstellung = Einstellung.laden()
    form = EinstellungForm(request.POST or None, instance=einstellung)
    if request.method == "POST" and form.is_valid():
        einstellung = form.save(commit=False)
        # Wer einrichtet, bekommt seine Wiedervorlagen (nachrichten.py).
        einstellung.empfaenger = request.user
        einstellung.save()
        messages.success(request, "Benachrichtigungen gespeichert.")
        return redirect("benachrichtigungen:einstellungen")
    return render(
        request,
        "benachrichtigungen/einstellungen.html",
        {
            "bereich": "einstellungen",
            "form": form,
            "einstellung": einstellung,
            "qr": qr_bild(einstellung.link) if einstellung.bot_name else "",
            "autostart": autostart.moeglich() and autostart.an(),
            "autostart_moeglich": autostart.moeglich(),
        },
    )


@require_POST
@nur_inhaber
def verbinden(request):
    einstellung = Einstellung.laden()
    try:
        chat = telegram.chat_finden(einstellung.bot_schluessel, einstellung.code)
        if chat:
            telegram.senden(einstellung.bot_schluessel, chat, VERBUNDEN)
    except telegram.Fehler as fehler:
        messages.error(request, str(fehler))
    else:
        if chat:
            einstellung.chat = chat
            einstellung.aktiv = True
            einstellung.empfaenger = request.user
            einstellung.save()
            messages.success(
                request, "Verbunden. In Telegram sollte gerade eine Nachricht da sein."
            )
        else:
            messages.error(
                request,
                "Noch nicht gefunden. Öffnen Sie den Link oder QR-Code, tippen Sie in "
                "Telegram auf „Starten“ und dann hier noch einmal auf „Verbindung prüfen“.",
            )
    return redirect("benachrichtigungen:einstellungen")


@require_POST
@nur_inhaber
def testen(request):
    einstellung = Einstellung.laden()
    try:
        telegram.senden(einstellung.bot_schluessel, einstellung.chat, TEST)
    except telegram.Fehler as fehler:
        messages.error(request, f"Die Testnachricht kam nicht an: {fehler}")
    else:
        messages.success(request, "Testnachricht gesendet.")
    return redirect("benachrichtigungen:einstellungen")


@require_POST
@nur_inhaber
def trennen(request):
    einstellung = Einstellung.laden()
    einstellung.trennen()
    einstellung.save()
    messages.success(
        request, "Telegram ist getrennt; es kommen keine Nachrichten mehr."
    )
    return redirect("benachrichtigungen:einstellungen")


@require_POST
@nur_inhaber
def autostart_setzen(request):
    if autostart.moeglich():
        ein = request.POST.get("ein") == "1"
        autostart.setzen(ein)
        messages.success(
            request,
            "Kontorfreund startet jetzt beim Anmelden an Windows im Hintergrund."
            if ein
            else "Kontorfreund startet nicht mehr von selbst.",
        )
    return redirect("benachrichtigungen:einstellungen")
