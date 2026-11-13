from django import forms

from invoicing.forms import Betrag

from .models import Artikel


class ArtikelForm(forms.ModelForm):
    preis = Betrag(
        label="Einzelpreis",
        min_value=0,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        help_text="In Euro, ohne Umsatzsteuer.",
    )

    class Meta:
        model = Artikel
        fields = ["bezeichnung", "beschreibung", "einheit", "preis", "steuersatz"]
        widgets = {
            "bezeichnung": forms.TextInput(
                attrs={"placeholder": "z. B. Stundensatz Webdesign"}
            ),
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"steuersatz": "Umsatzsteuer"}
        help_texts = {
            "beschreibung": "Steht unter der Bezeichnung auf der Rechnung. In der Rechnung können Sie den Text noch anpassen, etwa um den Zeitraum.",
            "steuersatz": "Gilt auf Belegen, die Umsatzsteuer ausweisen. 7 % nur, wo § 12 Abs. 2 UStG den ermäßigten Satz vorsieht.",
        }

    def __init__(self, *args, mit_steuersatz=True, **kwargs):
        """Ohne `mit_steuersatz` (Kleinunternehmer) fehlt das Feld; der Satz bleibt, wie er ist."""
        super().__init__(*args, **kwargs)
        if not mit_steuersatz:
            del self.fields["steuersatz"]
