from django import forms

from contacts.models import Kontakt
from invoicing.forms import ZAHLUNGSZIELE, RabattMixin, rabattfeld

from .models import Vertrag

DATUM = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class VertragForm(RabattMixin, forms.ModelForm):
    zahlungsziel = forms.TypedChoiceField(
        label="Zahlungsziel", choices=ZAHLUNGSZIELE, coerce=int, initial=14
    )
    rabatt_prozent = rabattfeld()

    class Meta:
        model = Vertrag
        fields = [
            "bezeichnung",
            "kontakt",
            "betreff",
            "rhythmus",
            "beginn",
            "ende",
            "nachfragen",
            "zahlungsziel",
            "steuerfall",
            "rabatt_prozent",
            "kopftext",
            "fusstext",
        ]
        widgets = {
            "beginn": DATUM,
            "ende": DATUM,
            "bezeichnung": forms.TextInput(
                attrs={"placeholder": "z. B. Wartung Server und Netzwerk"}
            ),
            "betreff": forms.TextInput(attrs={"placeholder": "z. B. Wartungsvertrag"}),
            "kopftext": forms.Textarea(attrs={"rows": 3}),
            "fusstext": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"steuerfall": "Umsatzsteuer"}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)
        # Gesperrte Adressen fehlen, die bisherige bleibt wählbar.
        self.fields["kontakt"].queryset = Kontakt.objects.filter(
            archiviert=False, gesperrt_am__isnull=True
        ) | Kontakt.objects.filter(pk=self.instance.kontakt_id or 0)
        self.rabatt_vorbelegen()

    def clean(self):
        daten = super().clean()
        beginn, ende = daten.get("beginn"), daten.get("ende")
        if beginn and ende and ende < beginn:
            self.add_error("ende", "Das Ende liegt vor dem Beginn.")
        return daten
