from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Benutzer


class Formular(forms.Form):
    """Feld-IDs ohne Vorsilbe (kennwort statt id_kennwort), wie in den übrigen Formularen."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)


class AnmeldenForm(Formular):
    email = forms.EmailField(
        label="E-Mail-Adresse",
        widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
    )
    kennwort = forms.CharField(
        label="Kennwort",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class CodeForm(Formular):
    code = forms.CharField(
        label="Code aus der Authenticator-App",
        max_length=9,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "autofocus": True,
                "aria-describedby": "code_helptext",
            }
        ),
        help_text="Sechs Ziffern, alle 30 Sekunden neu.",
    )


class NeuesKennwortForm(Formular):
    """Neues Kennwort zweimal; geprüft nach den Kennwortregeln (konten.kennwort)."""

    kennwort = forms.CharField(
        label="Neues Kennwort",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Mindestens 12 Zeichen. Gut merken lassen sich drei, vier Wörter, "
        "die nichts miteinander zu tun haben.",
    )
    wiederholung = forms.CharField(
        label="Kennwort wiederholen",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, benutzer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.benutzer = benutzer

    def clean(self):
        daten = super().clean()
        kennwort = daten.get("kennwort")
        if kennwort:
            if kennwort != daten.get("wiederholung"):
                self.add_error(
                    "wiederholung", "Die beiden Kennwörter sind nicht gleich."
                )
            else:
                try:
                    validate_password(kennwort, self.benutzer)
                except forms.ValidationError as fehler:
                    self.add_error("kennwort", fehler)
        return daten


class EinrichtenForm(NeuesKennwortForm):
    name = forms.CharField(
        label="Ihr Name",
        max_length=100,
        widget=forms.TextInput(attrs={"autocomplete": "name", "autofocus": True}),
    )
    email = forms.EmailField(
        label="E-Mail-Adresse",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
        help_text="Damit melden Sie sich an.",
    )
    field_order = ["name", "email", "kennwort", "wiederholung"]


class BenutzerForm(EinrichtenForm):
    """Ein Inhaber legt ein weiteres Konto an und gibt das erste Kennwort weiter."""

    rolle = forms.ChoiceField(
        label="Rolle",
        choices=Benutzer.Rolle.choices,
        initial=Benutzer.Rolle.MITARBEITER,
    )
    field_order = ["name", "email", "rolle", "kennwort", "wiederholung"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].label = "Name"
        self.fields["name"].widget.attrs.pop("autofocus")
        self.fields["kennwort"].label = "Erstes Kennwort"
        self.fields["email"].help_text = ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Benutzer.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Für diese Adresse gibt es schon ein Konto.")
        return email


class KennwortAendernForm(NeuesKennwortForm):
    bisher = forms.CharField(
        label="Bisheriges Kennwort",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    field_order = ["bisher", "kennwort", "wiederholung"]

    def clean_bisher(self):
        if not self.benutzer.check_password(self.cleaned_data["bisher"]):
            raise forms.ValidationError("Das bisherige Kennwort stimmt nicht.")
        return self.cleaned_data["bisher"]


class KennwortBestaetigenForm(forms.Form):
    kennwort = forms.CharField(
        label="Ihr Kennwort zur Bestätigung",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, benutzer, **kwargs):
        kwargs.setdefault("auto_id", "aus_%s")
        super().__init__(*args, **kwargs)
        self.benutzer = benutzer

    def clean_kennwort(self):
        if not self.benutzer.check_password(self.cleaned_data["kennwort"]):
            raise forms.ValidationError("Das Kennwort stimmt nicht.")
        return self.cleaned_data["kennwort"]
