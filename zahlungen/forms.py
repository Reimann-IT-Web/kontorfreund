from datetime import date
from decimal import Decimal

from django import forms

from invoicing.forms import Betrag

from .models import Basiszins, Mahnstufe, Zahlung

DATUM = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


def betrag(label, **mehr):
    return Betrag(
        label=label,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        **mehr,
    )


class ZahlungForm(forms.Form):
    datum = forms.DateField(label="Eingegangen am", initial=date.today, widget=DATUM)
    betrag = betrag(
        "Betrag",
        help_text="Was auf dem Konto eingegangen ist. Mit Minus für eine "
        "Rückzahlung an den Kunden.",
    )
    art = forms.ChoiceField(
        label="Art",
        choices=[
            c
            for c in Zahlung.Art.choices
            if c[0] not in (Zahlung.Art.AUSBUCHUNG, Zahlung.Art.SKONTO)
        ],
    )
    notiz = forms.CharField(label="Notiz", required=False, max_length=200)

    def clean_betrag(self):
        wert = self.cleaned_data["betrag"]
        if wert == 0:
            raise forms.ValidationError("Bitte einen Betrag eingeben.")
        return wert


class AusbuchenForm(forms.Form):
    datum = forms.DateField(label="Datum", initial=date.today, widget=DATUM)
    betrag = betrag("Betrag", min_value=Decimal("0.01"))
    grund = forms.CharField(
        label="Grund",
        max_length=200,
        widget=forms.TextInput(
            attrs={"placeholder": "z. B. Bankgebühr abgezogen, Kunde zahlungsunfähig"}
        ),
    )


class MahnungForm(forms.Form):
    datum = forms.DateField(label="Datum des Schreibens", widget=DATUM)
    frist = forms.DateField(label="Zahlen bis", widget=DATUM)
    text = forms.CharField(
        label="Text", widget=forms.Textarea(attrs={"rows": 6}), max_length=3000
    )
    gebuehr = betrag(
        "Mahngebühr",
        min_value=0,
        help_text="Ersatzfähig sind nur tatsächliche Kosten wie Porto, nicht Ihre "
        "Arbeitszeit. Für ein Schreiben, das den Verzug erst auslöst, nichts.",
    )
    zinsen = forms.BooleanField(label="Verzugszinsen berechnen", required=False)
    pauschale = forms.BooleanField(
        label="Verzugspauschale 40 € (nur gegenüber Unternehmen)", required=False
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)

    def clean(self):
        daten = super().clean()
        if (
            daten.get("datum")
            and daten.get("frist")
            and daten["frist"] <= daten["datum"]
        ):
            self.add_error(
                "frist", "Die Frist muss nach dem Datum des Schreibens liegen."
            )
        return daten


class MahnstufeForm(forms.ModelForm):
    gebuehr = betrag("Mahngebühr", min_value=0)

    class Meta:
        model = Mahnstufe
        fields = ["abstand", "frist", "gebuehr", "zinsen", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 5})}


class BasiszinsForm(forms.ModelForm):
    satz = betrag("Basiszinssatz in Prozent")

    class Meta:
        model = Basiszins
        fields = ["gueltig_ab", "satz"]
        widgets = {"gueltig_ab": DATUM}

    def clean_gueltig_ab(self):
        tag = self.cleaned_data["gueltig_ab"]
        if (tag.month, tag.day) not in ((1, 1), (7, 1)):
            raise forms.ValidationError(
                "Der Basiszinssatz ändert sich nur zum 1. Januar und 1. Juli."
            )
        return tag
