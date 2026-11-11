from django import forms

from contacts.forms import PLZ_ATTRS
from invoicing.beleg import (
    ZAHLUNG_BEISPIEL,
    ZAHLUNG_PLATZHALTER,
    logo_lesbar,
    unbekannte_platzhalter,
)

from .models import Firmendaten

BILD_GROESSE = 1024 * 1024
BILDARTEN = ".svg,.png,.jpg,.jpeg,image/svg+xml,image/png,image/jpeg"
PLATZHALTER_TEXT = (
    ", ".join("{" + n + "}" for n in ZAHLUNG_PLATZHALTER[:-1])
    + " und {"
    + ZAHLUNG_PLATZHALTER[-1]
    + "}"
)


def bilddatei_lesen(datei, name):
    """Inhalt der hochgeladenen Bilddatei; leer, wenn keine gewählt ist."""
    if not datei:
        return b""
    if datei.size > BILD_GROESSE:
        raise forms.ValidationError(f"{name} darf höchstens 1 MB groß sein.")
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


class FirmendatenForm(forms.ModelForm):
    logo_datei = forms.FileField(
        label="Bilddatei",
        required=False,
        help_text="SVG, PNG oder JPG bis 1 MB. Steht oben links auf jeder Rechnung.",
        widget=forms.FileInput(attrs={"accept": BILDARTEN}),
    )
    logo_entfernen = forms.BooleanField(label="Logo entfernen", required=False)
    unterschrift_datei = forms.FileField(
        label="Bilddatei",
        required=False,
        help_text="PNG, JPG oder SVG bis 1 MB. Steht am Ende von Rechnungen, Angeboten, Auftragsbestätigungen und Mahnungen.",
        widget=forms.FileInput(attrs={"accept": BILDARTEN}),
    )
    unterschrift_entfernen = forms.BooleanField(
        label="Unterschrift entfernen", required=False
    )

    class Meta:
        model = Firmendaten
        fields = [
            "name",
            "marke",
            "unterschrift_text",
            "inhaber",
            "strasse",
            "plz",
            "ort",
            "steuernummer",
            "ust_id",
            "umsatzsteuer",
            "steuerfrei_hinweis",
            "email",
            "telefon",
            "internetadresse",
            "iban",
            "bank",
            "zahlungstext",
            "mail_server",
            "mail_port",
            "mail_verschluesselung",
            "mail_benutzer",
            "mail_passwort",
        ]
        widgets = {
            "telefon": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            # Kein type="url": Der Browser lehnte sonst „beispiel.de“ ab, das Formular ergänzt https://.
            "internetadresse": forms.TextInput(
                attrs={"inputmode": "url", "autocomplete": "url"}
            ),
            "plz": forms.TextInput(attrs=PLZ_ATTRS),
            "ort": forms.TextInput(
                attrs={"data-ort": "", "autocomplete": "address-level2"}
            ),
            "mail_passwort": forms.PasswordInput(
                render_value=False, attrs={"autocomplete": "new-password"}
            ),
            "unterschrift_text": forms.Textarea(attrs={"rows": 2}),
            "umsatzsteuer": forms.RadioSelect,
            "steuerfrei_hinweis": forms.TextInput(
                attrs={"placeholder": "Umsatzsteuerfrei nach § 4 Nr. 21 UStG"}
            ),
            "zahlungstext": forms.Textarea(
                attrs={"rows": 3, "placeholder": ZAHLUNG_BEISPIEL}
            ),
        }
        help_texts = {
            "marke": "Steht klein unter dem Firmennamen neben dem Logo, z. B. Ihr Markenname.",
            "unterschrift_text": "Zum Beispiel Ihr Name und in der zweiten Zeile Ihre Funktion.",
            "steuernummer": "Steht auf jeder Rechnung. Alternativ genügt die USt-IdNr.",
            "steuerfrei_hinweis": "Steht auf jedem Beleg mit steuerfreien Leistungen. "
            "Welche Befreiung für Sie gilt, klären Sie am besten mit Ihrem Steuerberater.",
            "iban": "Erscheint in der Fußzeile und im GiroCode.",
            "email": "Absender beim Versand von Rechnungen.",
            "internetadresse": "Steht auf jedem Beleg in der Fußzeile unter Telefon und E-Mail.",
            "zahlungstext": "Ersetzt auf Rechnungen die Zeilen unter dem Rechnungsbetrag. "
            f"Platzhalter: {PLATZHALTER_TEXT}. Leer lassen für den Text im Beispiel.",
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

    def clean_steuerfrei_hinweis(self):
        return self.cleaned_data["steuerfrei_hinweis"].strip()

    def clean(self):
        daten = super().clean()
        if daten.get(
            "umsatzsteuer"
        ) == Firmendaten.Umsatzsteuer.STEUERFREI and not daten.get(
            "steuerfrei_hinweis"
        ):
            self.add_error(
                "steuerfrei_hinweis",
                "Bitte tragen Sie ein, welcher Hinweis auf steuerfreien Belegen stehen soll.",
            )
        return daten

    def clean_zahlungstext(self):
        text = self.cleaned_data["zahlungstext"].strip()
        if unbekannt := unbekannte_platzhalter(text):
            namen = ", ".join("{" + n + "}" for n in unbekannt)
            raise forms.ValidationError(
                f"{'Diesen Platzhalter' if len(unbekannt) == 1 else 'Diese Platzhalter'} "
                f"kennt Kontorfreund nicht: {namen}. "
                f"Möglich sind {PLATZHALTER_TEXT}."
            )
        return text

    def clean_logo_datei(self):
        return bilddatei_lesen(self.cleaned_data["logo_datei"], "Das Logo")

    def clean_unterschrift_datei(self):
        return bilddatei_lesen(
            self.cleaned_data["unterschrift_datei"], "Die Unterschrift"
        )

    def save(self, commit=True):
        for feld in ("logo", "unterschrift"):
            if self.cleaned_data[f"{feld}_datei"]:
                setattr(self.instance, feld, self.cleaned_data[f"{feld}_datei"])
            elif self.cleaned_data[f"{feld}_entfernen"]:
                setattr(self.instance, feld, b"")
        return super().save(commit)
