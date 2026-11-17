from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.utils import formats

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

    # Fallen nur an, wenn der Kunde am Datum des Schreibens in Verzug ist (mahnen.berechnen).
    NUR_IM_VERZUG = {"gebuehr": Decimal("0.00"), "zinsen": False, "pauschale": False}

    def __init__(self, *args, verzug_ab=None, **kwargs):
        """`verzug_ab`: erster Tag des Verzugs ohne dieses Schreiben (mahnen.verzug_vor).

        Ist der Kunde am Datum des Schreibens nicht in Verzug, sind Mahngebühr, Zinsen
        und Pauschale gesperrt und leer, damit nichts angekreuzt ist, das nicht wirkt.
        `verzug_tag` ist dann der erste Tag des Verzugs mit diesem Schreiben: Ablauf der
        Frist oder früher `verzug_ab`. Der Block `form[data-verzug-ab]` in
        static/js/app.js macht dasselbe, sobald sich Datum oder Frist ändern; `data-wert`
        hält die Vorgabe, die er beim Entsperren wieder einsetzt.
        """
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)
        self.initial = dict(self.initial)
        self.verzug_ab = verzug_ab
        datum, frist = self._datum("datum"), self._datum("frist")
        self.ohne_verzug = not (verzug_ab and datum and verzug_ab <= datum)
        ende = frist + timedelta(days=1) if frist else None
        tage = [t for t in (verzug_ab, ende) if t]
        self.verzug_tag = min(tage) if tage else None
        self.verzug_durch_frist = ende is not None and self.verzug_tag == ende
        for name, leer in self.NUR_IM_VERZUG.items():
            feld, vorgabe = self.fields[name], self.initial.get(name)
            if isinstance(leer, bool):
                feld.widget.attrs["data-wert"] = "1" if vorgabe else ""
            else:
                feld.widget.attrs["data-wert"] = formats.localize_input(vorgabe or leer)
            if self.ohne_verzug:
                feld.disabled = True
                self.initial[name] = leer

    def _datum(self, name):
        """Datum aus Eingabe oder Vorgabe, None, wenn es sich nicht lesen lässt."""
        if not self.is_bound:
            return self.initial.get(name)
        feld = self.fields[name]
        try:
            return feld.clean(
                feld.widget.value_from_datadict(
                    self.data, self.files, self.add_prefix(name)
                )
            )
        except forms.ValidationError:
            return None

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
        fields = ["abstand", "frist", "gebuehr", "zinsen", "pauschale", "text"]
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
