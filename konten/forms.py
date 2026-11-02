from datetime import timedelta

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from datenzugriff.daten import jahre

from .models import Benutzer

# Höchstens so lange gilt ein Zugang für die Betriebsprüfung am Stück.
LAENGSTENS = timedelta(days=365)


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
                # Neue Konten gibt es noch nicht; die Regeln brauchen Name und Adresse.
                benutzer = self.benutzer or Benutzer(
                    name=daten.get("name", ""), email=daten.get("email", "")
                )
                try:
                    validate_password(kennwort, benutzer)
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
        choices=[
            (wert, text)
            for wert, text in Benutzer.Rolle.choices
            if wert != Benutzer.Rolle.PRUEFER
        ],
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


class PrueferForm(BenutzerForm):
    """Konto für einen Betriebsprüfer; Zeitraum und Ablauf stehen in PruefungForm."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["rolle"]
        self.fields[
            "name"
        ].help_text = (
            "Wie in der Prüfungsanordnung, z. B. Frau Beispiel, Finanzamt Mitte."
        )


class PruefungForm(forms.ModelForm):
    """Prüfungszeitraum und Ablauf des Zugangs eines Prüfers."""

    class Meta:
        model = Benutzer
        fields = ["pruefung_von", "pruefung_bis", "zugang_bis"]
        widgets = {
            "zugang_bis": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        }
        help_texts = {
            "pruefung_bis": "Die Jahre stehen in der Prüfungsanordnung.",
            "zugang_bis": "Danach kann sich der Prüfer nicht mehr anmelden, höchstens ein Jahr ab heute.",
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)
        auswahl = [(j, str(j)) for j in jahre()]
        for name in ("pruefung_von", "pruefung_bis", "zugang_bis"):
            self.fields[name].required = True
        for name in ("pruefung_von", "pruefung_bis"):
            self.fields[name] = forms.TypedChoiceField(
                label=self.fields[name].label,
                help_text=self.fields[name].help_text,
                choices=auswahl,
                coerce=int,
            )
        if not self.instance.pk:
            # Meist prüft das Finanzamt die letzten drei abgeschlossenen Jahre.
            vorjahr = auswahl[-2][0] if len(auswahl) > 1 else auswahl[-1][0]
            self.initial |= {
                "pruefung_von": max(vorjahr - 2, auswahl[0][0]),
                "pruefung_bis": vorjahr,
                "zugang_bis": timezone.localdate() + timedelta(days=30),
            }

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("pruefung_von"), daten.get("pruefung_bis")
        if von and bis and von > bis:
            self.add_error("pruefung_bis", "Das letzte Jahr liegt vor dem ersten.")
        zugang = daten.get("zugang_bis")
        heute = timezone.localdate()
        if zugang and not heute <= zugang <= heute + LAENGSTENS:
            self.add_error(
                "zugang_bis",
                f"Bitte ein Datum zwischen heute und dem {heute + LAENGSTENS:%d.%m.%Y}.",
            )
        return daten


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

    def clean(self):
        daten = super().clean()
        if daten.get("kennwort") and daten.get("kennwort") == daten.get("bisher"):
            self.add_error(
                "kennwort", "Bitte wählen Sie ein anderes als das bisherige Kennwort."
            )
        return daten


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


class EinschaltenForm(KennwortBestaetigenForm, CodeForm):
    """Kennwort und erster Code aus der App: Wer die Anmeldung ändert, bestätigt sich
    vorher (ASVS 7.5.1)."""

    field_order = ["kennwort", "code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, auto_id="%s", **kwargs)
        self.fields["kennwort"].label = "Ihr Kennwort"
        self.fields["code"].widget.attrs.pop("autofocus")
