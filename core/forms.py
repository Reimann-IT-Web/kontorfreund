from django import forms

from contacts.forms import PLZ_ATTRS
from invoicing.beleg import logo_lesbar

from .models import Firmendaten

LOGO_GROESSE = 1024 * 1024


class FirmendatenForm(forms.ModelForm):
    logo_datei = forms.FileField(
        label="Bilddatei",
        required=False,
        help_text="SVG, PNG oder JPG bis 1 MB. Steht oben links auf jeder Rechnung.",
        widget=forms.FileInput(
            attrs={"accept": ".svg,.png,.jpg,.jpeg,image/svg+xml,image/png,image/jpeg"}
        ),
    )
    logo_entfernen = forms.BooleanField(label="Logo entfernen", required=False)

    class Meta:
        model = Firmendaten
        fields = [
            "name",
            "marke",
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
            "plz": forms.TextInput(attrs=PLZ_ATTRS),
            "ort": forms.TextInput(
                attrs={"data-ort": "", "autocomplete": "address-level2"}
            ),
            "mail_passwort": forms.PasswordInput(
                render_value=False, attrs={"autocomplete": "new-password"}
            ),
        }
        help_texts = {
            "marke": "Steht klein unter dem Firmennamen neben dem Logo, z. B. Ihr Markenname.",
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

    def clean_logo_datei(self):
        datei = self.cleaned_data["logo_datei"]
        if not datei:
            return b""
        if datei.size > LOGO_GROESSE:
            raise forms.ValidationError("Das Logo darf höchstens 1 MB groß sein.")
        daten = datei.read()
        kopf = daten[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
        bekannt = daten.startswith((b"\x89PNG", b"\xff\xd8")) or (
            kopf.startswith(b"<") and b"<svg" in daten
        )
        if not (bekannt and logo_lesbar(daten)):
            raise forms.ValidationError(
                "Die Datei lässt sich nicht als Bild lesen. Bitte SVG, PNG oder JPG verwenden."
            )
        return daten

    def save(self, commit=True):
        if self.cleaned_data["logo_datei"]:
            self.instance.logo = self.cleaned_data["logo_datei"]
        elif self.cleaned_data["logo_entfernen"]:
            self.instance.logo = b""
        return super().save(commit)
