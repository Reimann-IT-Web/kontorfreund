from django import forms

from .models import Datev

ZAHL = forms.TextInput(attrs={"inputmode": "numeric"})


class DatevForm(forms.ModelForm):
    class Meta:
        model = Datev
        fields = [
            "beraternummer",
            "mandantennummer",
            "kontenrahmen",
            "debitoren",
            "sammelkonto",
            "erloes_kleinunternehmer",
            "erloes_regel",
            "erloes_13b",
        ]
        widgets = {
            "beraternummer": ZAHL,
            "mandantennummer": ZAHL,
            "sammelkonto": ZAHL,
            "erloes_kleinunternehmer": ZAHL,
            "erloes_regel": ZAHL,
            "erloes_13b": ZAHL,
        }
        help_texts = {
            "beraternummer": "Vier bis sieben Ziffern, von Ihrem Steuerberater.",
            "mandantennummer": "Ihre Nummer in der Kanzlei, bis zu fünf Ziffern.",
            "kontenrahmen": "Fragen Sie Ihren Steuerberater; kleine Betriebe buchen meist nach SKR 03.",
        }
