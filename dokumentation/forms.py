from django import forms

from archive.models import Altbeleg

from .inhalt import MASSNAHMEN
from .models import Angaben

TEXT = [
    "taetigkeit",
    "gewinnermittlung",
    "zahlungsverkehr",
    "belege",
    "email",
    "rechner",
]
DATENSCHUTZ = ["datenschutzbeauftragter", "weitere_verarbeitungen"]


class AngabenForm(forms.ModelForm):
    class Meta:
        model = Angaben
        fields = [*TEXT, "altprogramm", *DATENSCHUTZ, *MASSNAHMEN, "tom_weitere"]
        widgets = {
            name: forms.Textarea(attrs={"rows": 3})
            for name in [*TEXT, "altprogramm", *DATENSCHUTZ, "tom_weitere"]
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Die Frage nach dem bisherigen Programm stellt sich nur mit übernommenen Belegen.
        if not Altbeleg.objects.exists():
            del self.fields["altprogramm"]
