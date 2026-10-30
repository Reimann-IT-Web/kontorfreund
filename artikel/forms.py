from decimal import InvalidOperation

from django import forms

from invoicing.forms import dezimal

from .models import Artikel


class Betrag(forms.DecimalField):
    """Euro in deutscher Schreibweise wie im Rechnungseditor, z. B. 1.250,00."""

    def to_python(self, value):
        if isinstance(value, str) and value.strip():
            try:
                value = dezimal(value)
            except InvalidOperation:
                raise forms.ValidationError(
                    self.error_messages["invalid"], code="invalid"
                ) from None
        return super().to_python(value)


class ArtikelForm(forms.ModelForm):
    preis = Betrag(
        label="Einzelpreis",
        min_value=0,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        help_text="In Euro, ohne Umsatzsteuer.",
    )

    class Meta:
        model = Artikel
        fields = ["bezeichnung", "beschreibung", "einheit", "preis"]
        widgets = {
            "bezeichnung": forms.TextInput(
                attrs={"placeholder": "z. B. Stundensatz Webdesign"}
            ),
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "beschreibung": "Steht unter der Bezeichnung auf der Rechnung. In der Rechnung können Sie den Text noch anpassen, etwa um den Zeitraum.",
        }
