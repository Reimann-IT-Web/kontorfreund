from django import forms

from .models import Firmendaten


class FirmendatenForm(forms.ModelForm):
    class Meta:
        model = Firmendaten
        fields = [
            "name",
            "inhaber",
            "strasse",
            "plz",
            "ort",
            "steuernummer",
            "ust_id",
            "kleinunternehmer",
            "email",
            "telefon",
            "iban",
            "bank",
            "mail_server",
            "mail_port",
            "mail_verschluesselung",
            "mail_benutzer",
            "mail_passwort",
        ]
        widgets = {
            "telefon": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "plz": forms.TextInput(
                attrs={"inputmode": "numeric", "autocomplete": "postal-code"}
            ),
            "mail_passwort": forms.PasswordInput(
                render_value=False, attrs={"autocomplete": "new-password"}
            ),
        }
        help_texts = {
            "steuernummer": "Steht auf jeder Rechnung. Alternativ genügt die USt-IdNr.",
            "kleinunternehmer": "Dann weist Kontorfreund keine Umsatzsteuer aus und druckt den Hinweis nach § 19 UStG.",
            "iban": "Erscheint in der Fußzeile und im GiroCode.",
            "email": "Absender beim Versand von Rechnungen.",
            "mail_server": "Steht in der Hilfe Ihres E-Mail-Anbieters, z. B. smtp.ionos.de.",
            "mail_benutzer": "Meist Ihre vollständige E-Mail-Adresse.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.mail_passwort:
            self.fields[
                "mail_passwort"
            ].help_text = "Gespeichert. Leer lassen, um es zu behalten."

    def clean_mail_passwort(self):
        # Ein leeres Feld behält das gespeicherte Passwort; es wird nie zurück an den Browser geschickt.
        return self.cleaned_data["mail_passwort"] or self.instance.mail_passwort
