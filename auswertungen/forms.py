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
            "erloes_regel7",
            "erloes_13b",
            "erloes_steuerfrei",
        ]
        widgets = {
            "beraternummer": ZAHL,
            "mandantennummer": ZAHL,
            "sammelkonto": ZAHL,
            "erloes_kleinunternehmer": ZAHL,
            "erloes_regel": ZAHL,
            "erloes_regel7": ZAHL,
            "erloes_13b": ZAHL,
            "erloes_steuerfrei": ZAHL,
        }
        help_texts = {
            "beraternummer": "Vier bis sieben Ziffern, von Ihrem Steuerberater.",
            "mandantennummer": "Ihre Nummer in der Kanzlei, bis zu fünf Ziffern.",
            "kontenrahmen": "Fragen Sie Ihren Steuerberater; kleine Betriebe buchen meist nach SKR 03.",
        }
