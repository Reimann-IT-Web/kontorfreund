from django import forms

from contacts.models import Kontakt
from invoicing.forms import RabattMixin, anschriften_pruefen, rabattfeld

from .models import Auftragsbestaetigung


class AuftragForm(RabattMixin, forms.ModelForm):
    rabatt_prozent = rabattfeld()

    class Meta:
        model = Auftragsbestaetigung
        fields = [
            "kontakt",
            "anschrift",
            "lieferanschrift",
            "datum",
            "leistung_von",
            "leistung_bis",
            "steuerfall",
            "rabatt_prozent",
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
        self.fields["kontakt"].queryset = Kontakt.objects.filter(
            archiviert=False
        ).prefetch_related("anschriften")
        self.rabatt_vorbelegen()

    def clean(self):
        daten = super().clean()
        anschriften_pruefen(self, daten)
        return daten
