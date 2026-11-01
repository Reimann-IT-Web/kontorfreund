from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from konten.rechte import nur_inhaber

from . import autostart, sms
from .forms import EinstellungForm
from .models import Einstellung

TEST = "Kontorfreund: Testnachricht. So kommen künftig Ihre Erinnerungen an."


@nur_inhaber
def einstellungen(request):
    einstellung = Einstellung.laden()
    test = "test" in request.POST
    form = EinstellungForm(request.POST or None, instance=einstellung, test=test)
    if request.method == "POST" and form.is_valid():
        einstellung = form.save(commit=False)
        # Wer einschaltet, bekommt seine Wiedervorlagen (nachrichten.py).
        einstellung.empfaenger = request.user
        einstellung.save()
        if not test:
            messages.success(request, "Benachrichtigungen gespeichert.")
        else:
            try:
                sms.senden(einstellung.api_schluessel, einstellung.handy, TEST)
            except sms.Fehler as fehler:
                messages.error(request, f"Die Testnachricht kam nicht an: {fehler}")
            else:
                messages.success(
                    request, "Testnachricht gesendet. Sie sollte gleich ankommen."
                )
        return redirect("benachrichtigungen:einstellungen")
    return render(
        request,
        "benachrichtigungen/einstellungen.html",
        {
            "bereich": "einstellungen",
            "form": form,
            "einstellung": einstellung,
            "autostart": autostart.moeglich() and autostart.an(),
            "autostart_moeglich": autostart.moeglich(),
        },
    )


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
