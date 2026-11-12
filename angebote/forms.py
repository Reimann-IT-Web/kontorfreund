from django import forms

from contacts.models import Kontakt
from invoicing.forms import RabattMixin, anschriften_pruefen, rabattfeld

from .models import Angebot

BINDEFRISTEN = [(14, "14 Tage"), (30, "30 Tage"), (60, "60 Tage"), (90, "90 Tage")]


class AngebotForm(RabattMixin, forms.ModelForm):
    bindefrist = forms.TypedChoiceField(
        label="Gültig", choices=BINDEFRISTEN, coerce=int, initial=30
    )
    rabatt_prozent = rabattfeld()

    class Meta:
        model = Angebot
        fields = [
            "kontakt",
            "anschrift",
            "lieferanschrift",
            "datum",
            "bindefrist",
            "steuerfall",
            "rabatt_prozent",
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
        self.fields["kontakt"].queryset = Kontakt.objects.filter(
            archiviert=False
        ).prefetch_related("anschriften")
        self.rabatt_vorbelegen()

    def clean(self):
        daten = super().clean()
        anschriften_pruefen(self, daten)
        return daten
