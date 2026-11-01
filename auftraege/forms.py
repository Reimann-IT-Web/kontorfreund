from django import forms

from contacts.models import Kontakt

from .models import Auftragsbestaetigung


class AuftragForm(forms.ModelForm):
    class Meta:
        model = Auftragsbestaetigung
        fields = [
            "kontakt",
            "datum",
            "leistung_von",
            "leistung_bis",
            "steuerfall",
            "betreff",
            "kopftext",
            "fusstext",
        ]
        widgets = {
            "datum": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "leistung_von": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "aria-describedby": "zeitraum-hinweis"},
            ),
            "leistung_bis": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "aria-describedby": "zeitraum-hinweis"},
            ),
            "betreff": forms.TextInput(
                attrs={"placeholder": "z. B. Neue Website für Ihr Geschäft"}
            ),
            "kopftext": forms.Textarea(attrs={"rows": 4}),
            "fusstext": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)
        self.fields["kontakt"].queryset = Kontakt.objects.filter(archiviert=False)
