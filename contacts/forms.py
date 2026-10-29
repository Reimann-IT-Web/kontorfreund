from django import forms

from .models import Kontakt


class KontaktForm(forms.ModelForm):
    class Meta:
        model = Kontakt
        fields = [
            "art",
            "kategorie",
            "firmenname",
            "anrede",
            "titel",
            "vorname",
            "nachname",
            "strasse",
            "plz",
            "ort",
            "land",
            "email",
            "telefon",
            "website",
            "ust_id",
            "notiz",
        ]
        widgets = {
            "art": forms.RadioSelect,
            "kategorie": forms.RadioSelect,
            "telefon": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "plz": forms.TextInput(
                attrs={"inputmode": "numeric", "autocomplete": "postal-code"}
            ),
            "notiz": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "ust_id": "Nur nötig bei Geschäften mit Unternehmen im EU-Ausland oder § 13b.",
        }
