from django import forms

from contacts.models import Kontakt
from konten.models import Benutzer

from .models import Wiedervorlage


class WiedervorlageForm(forms.ModelForm):
    class Meta:
        model = Wiedervorlage
        fields = ["titel", "faellig", "uhrzeit", "kontakt", "zustaendig", "notiz"]
        widgets = {
            "faellig": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "uhrzeit": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "notiz": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "titel": "Zum Beispiel: Angebot nachfassen, Rückruf, Termin bestätigen."
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kontakte = Kontakt.objects.filter(archiviert=False)
        if self.instance.kontakt_id:
            kontakte = Kontakt.objects.filter(pk=self.instance.kontakt_id) | kontakte
        self.fields["kontakt"].queryset = kontakte
        self.fields["kontakt"].empty_label = "ohne Adresse"
        self.fields["zustaendig"].queryset = Benutzer.objects.filter(is_active=True)
        self.fields["zustaendig"].empty_label = "alle"


class ErledigenForm(forms.Form):
    ergebnis = forms.CharField(
        label="Ergebnis",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Steht danach in der Kontakthistorie der Adresse.",
    )
