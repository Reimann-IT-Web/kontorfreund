from pathlib import Path

from django import forms
from django.conf import settings

from .sicherung import AUFBEWAHREN


class KennwortForm(forms.Form):
    kennwort = forms.CharField(
        label="Kennwort",
        min_length=12,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Mindestens 12 Zeichen. Gut zu merken und trotzdem sicher ist ein Satz aus mehreren Wörtern.",
    )
    wiederholung = forms.CharField(
        label="Kennwort wiederholen",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    notiert = forms.BooleanField(
        label="Ich habe das Kennwort aufgeschrieben und bewahre es getrennt vom Rechner auf.",
        error_messages={
            "required": "Bitte bestätigen Sie, dass Sie das Kennwort aufbewahren."
        },
    )

    def clean(self):
        daten = super().clean()
        if daten.get("kennwort") and daten.get("wiederholung") != daten["kennwort"]:
            self.add_error("wiederholung", "Die beiden Eingaben stimmen nicht überein.")
        return daten


class OrtForm(forms.Form):
    ziel = forms.CharField(
        label="Zweiter Speicherort",
        required=False,
        max_length=500,
        help_text="Ein Ordner auf einer USB-Platte, einem NAS oder in einem Cloud-Ordner bei einem Anbieter in der EU, z. B. E:\\Kontorfreund-Sicherung.",
    )
    aufbewahren = forms.IntegerField(
        label="Sicherungen aufbewahren",
        min_value=3,
        max_value=100,
        initial=AUFBEWAHREN,
        help_text="So viele bleiben an jedem Ort erhalten, ältere löscht Kontorfreund.",
    )

    def clean_ziel(self):
        # „Als Pfad kopieren“ im Windows-Explorer setzt Anführungszeichen.
        ziel = self.cleaned_data["ziel"].strip().strip('"')
        if not ziel:
            return ""
        pfad = Path(ziel).expanduser()
        if not pfad.is_absolute():
            raise forms.ValidationError(
                "Bitte den vollständigen Pfad eingeben, z. B. E:\\Kontorfreund-Sicherung oder /Volumes/USB/Kontorfreund."
            )
        if not pfad.is_dir():
            raise forms.ValidationError(
                "Diesen Ordner gibt es nicht, oder er ist gerade nicht erreichbar."
            )
        if pfad.resolve().is_relative_to(Path(settings.DATA_DIR).resolve()):
            raise forms.ValidationError(
                "Der Ordner liegt bei den Daten von Kontorfreund. Wählen Sie einen anderen Datenträger."
            )
        probe = pfad / ".kontorfreund-probe"
        try:
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            raise forms.ValidationError(
                "In diesen Ordner kann Kontorfreund nicht schreiben."
            ) from None
        return str(pfad)


class EinlesenForm(forms.Form):
    datei = forms.FileField(
        label="Sicherungsdatei",
        widget=forms.FileInput(attrs={"accept": ".sicherung"}),
    )


class WiederherstellenForm(forms.Form):
    kennwort = forms.CharField(
        label="Kennwort der Sicherung",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
