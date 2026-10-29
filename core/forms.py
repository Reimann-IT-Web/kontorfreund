from django import forms

from .models import Firmendaten


class FirmendatenForm(forms.ModelForm):
    class Meta:
        model = Firmendaten
        fields = [
            "name",
            "inhaber",
            "strasse",
            "plz",
            "ort",
            "steuernummer",
            "ust_id",
            "kleinunternehmer",
            "email",
            "telefon",
            "iban",
            "bank",
        ]
        widgets = {
            "telefon": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "plz": forms.TextInput(
                attrs={"inputmode": "numeric", "autocomplete": "postal-code"}
            ),
        }
        help_texts = {
            "steuernummer": "Steht auf jeder Rechnung. Alternativ genügt die USt-IdNr.",
            "kleinunternehmer": "Dann weist Kontorfreund keine Umsatzsteuer aus und druckt den Hinweis nach § 19 UStG.",
            "iban": "Erscheint in der Fußzeile und im GiroCode.",
        }
