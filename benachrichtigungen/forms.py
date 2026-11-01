import re

from django import forms

from .models import Einstellung


class EinstellungForm(forms.ModelForm):
    class Meta:
        model = Einstellung
        fields = ["aktiv", "handy", "api_schluessel", "uhrzeit", "vorlauf"]
        widgets = {
            "handy": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "api_schluessel": forms.PasswordInput(
                render_value=False, attrs={"autocomplete": "off"}
            ),
            "uhrzeit": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }
        help_texts = {
            "aktiv": "Jeden Tag eine Übersicht, wenn etwas ansteht, und eine Erinnerung vor Terminen.",
            "handy": "Ihre eigene Nummer, z. B. 0171 1234567.",
            "api_schluessel": "Aus Ihrem Kundenkonto bei seven.io, Bereich „Developer“.",
            "uhrzeit": "Kommt nur, wenn heute etwas ansteht.",
            "vorlauf": "Für Wiedervorlagen mit Uhrzeit, zusätzlich zur Übersicht.",
        }

    def __init__(self, *args, test=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.test = test
        if self.instance.api_schluessel:
            self.fields[
                "api_schluessel"
            ].help_text = "Gespeichert. Leer lassen, um ihn zu behalten."

    def clean_handy(self):
        nummer = re.sub(r"[\s/().-]", "", self.cleaned_data["handy"])
        if not nummer:
            return ""
        if nummer.startswith("00"):
            nummer = "+" + nummer[2:]
        elif nummer.startswith("0"):
            nummer = "+49" + nummer[1:]
        if not re.fullmatch(r"\+[1-9]\d{7,14}", nummer):
            raise forms.ValidationError(
                "Bitte eine Handynummer eingeben, z. B. 0171 1234567."
            )
        return nummer

    def clean_api_schluessel(self):
        # Ein leeres Feld behält den gespeicherten Schlüssel; er geht nie zurück an den Browser.
        return (
            self.cleaned_data["api_schluessel"].strip() or self.instance.api_schluessel
        )

    def clean(self):
        daten = super().clean()
        if daten.get("aktiv") or self.test:
            for feld in ("handy", "api_schluessel"):
                if not daten.get(feld) and feld not in self.errors:
                    self.add_error(feld, "Bitte ausfüllen, damit SMS ankommen.")
        return daten
