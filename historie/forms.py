from django import forms

from .models import Vorgang


class VorgangForm(forms.ModelForm):
    class Meta:
        model = Vorgang
        fields = ["art", "zeitpunkt", "betreff", "text"]
        widgets = {
            "art": forms.RadioSelect,
            "zeitpunkt": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "text": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        daten = super().clean()
        if not (daten.get("betreff", "").strip() or daten.get("text", "").strip()):
            raise forms.ValidationError("Bitte einen Betreff oder einen Text eingeben.")
        return daten
