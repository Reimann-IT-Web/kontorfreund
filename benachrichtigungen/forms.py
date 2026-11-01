from django import forms

from . import telegram
from .models import Einstellung


class EinstellungForm(forms.ModelForm):
    class Meta:
        model = Einstellung
        fields = ["aktiv", "bot_schluessel", "uhrzeit", "vorlauf"]
        widgets = {
            "bot_schluessel": forms.PasswordInput(
                render_value=False, attrs={"autocomplete": "off"}
            ),
            "uhrzeit": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        help_texts = {
            "aktiv": "Jeden Tag eine Übersicht, wenn etwas ansteht, und eine Erinnerung vor Terminen.",
            "bot_schluessel": "Schickt Ihnen BotFather nach /newbot, z. B. 123456789:AAH…",
            "uhrzeit": "Kommt nur, wenn heute etwas ansteht.",
            "vorlauf": "Für Wiedervorlagen mit Uhrzeit, zusätzlich zur Übersicht.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.neuer_bot = None
        if self.instance.bot_schluessel:
            self.fields[
                "bot_schluessel"
            ].help_text = "Gespeichert. Leer lassen, um ihn zu behalten."

    def clean_bot_schluessel(self):
        # Ein leeres Feld behält den gespeicherten Schlüssel; er geht nie zurück an den Browser.
        schluessel = self.cleaned_data["bot_schluessel"].strip()
        if not schluessel or schluessel == self.instance.bot_schluessel:
            return self.instance.bot_schluessel
        if not telegram.SCHLUESSEL.fullmatch(schluessel):
            raise forms.ValidationError(
                "Das ist kein Bot-Schlüssel. Er sieht aus wie 123456789:AAH… und "
                "steht in der Nachricht von BotFather."
            )
        try:
            self.neuer_bot = telegram.bot(schluessel)
        except telegram.Fehler as fehler:
            raise forms.ValidationError(str(fehler)) from None
        return schluessel

    def save(self, commit=True):
        einstellung = super().save(commit=False)
        if self.neuer_bot:
            # Neuer Bot: neu verbinden, bis dahin keine Nachrichten.
            einstellung.bot_name = self.neuer_bot
            einstellung.trennen()
        if commit:
            einstellung.save()
        return einstellung
