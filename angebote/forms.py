from django import forms

from contacts.models import Kontakt

from .models import Angebot

BINDEFRISTEN = [(14, "14 Tage"), (30, "30 Tage"), (60, "60 Tage"), (90, "90 Tage")]


class AngebotForm(forms.ModelForm):
    bindefrist = forms.TypedChoiceField(
        label="Gültig", choices=BINDEFRISTEN, coerce=int, initial=30
    )

    class Meta:
        model = Angebot
        fields = [
            "kontakt",
            "datum",
            "bindefrist",
            "steuerfall",
            "betreff",
            "kopftext",
            "fusstext",
        ]
        widgets = {
            "datum": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
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
