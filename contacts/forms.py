from django import forms
from django.urls import reverse_lazy

from .models import Kontakt

# Die PLZ füllt den Ort aus (static/js/app.js); dazu gehört ein Feld mit data-ort.
PLZ_ATTRS = {
    "inputmode": "numeric",
    "autocomplete": "postal-code",
    "data-plz": reverse_lazy("contacts:orte"),
}


class KontaktForm(forms.ModelForm):
    class Meta:
        model = Kontakt
        fields = [
            "art",
            "kategorie",
            "firmenname",
            "zusatz",
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
            "kaeuferreferenz",
            "xrechnung",
            "notiz",
        ]
        widgets = {
            "art": forms.RadioSelect,
            "kategorie": forms.RadioSelect,
            "telefon": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "plz": forms.TextInput(attrs=PLZ_ATTRS),
            "ort": forms.TextInput(
                attrs={"data-ort": "", "autocomplete": "address-level2"}
            ),
            "land": forms.TextInput(attrs={"data-land": ""}),
            "notiz": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "ust_id": "Nur nötig bei Geschäften mit Unternehmen im EU-Ausland oder § 13b.",
            "kaeuferreferenz": "Steht auf jeder Rechnung an diese Adresse. Behörden nennen Ihnen dafür ihre Leitweg-ID, z. B. 991-01234-38.",
            "xrechnung": "Für Behörden und Kunden, die eine XRechnung verlangen. Zu jeder Rechnung legt Kontorfreund dann die XML-Datei bei, die Sie im Portal der Behörde hochladen oder mitschicken.",
        }
