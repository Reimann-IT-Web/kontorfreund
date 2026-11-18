from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django import forms
from django.core.exceptions import SuspiciousFileOperation
from django.utils.text import get_valid_filename
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from invoicing.forms import ZAHLUNGSZIELE, Betrag
from invoicing.models import Steuersatz

from . import texte
from .auswertung import FELDER, PFLICHT
from .models import BEILAGE_MB, Vorlage


class AngabenForm(forms.Form):
    """Was für alle Rechnungen der Serie gilt (B-11, Schritt 2)."""

    termin = forms.CharField(label="Termin", max_length=100)
    thema = forms.CharField(label="Thema", max_length=300)
    link = forms.CharField(label="Link", max_length=500, required=False)
    leistungsdatum = forms.DateField(
        label="Leistungsdatum",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        help_text="Der Tag der Veranstaltung; aus dem Termin vorgeschlagen.",
    )
    datum = forms.DateField(
        label="Rechnungsdatum",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    preis = Betrag(
        label="Preis je Teilnehmer",
        min_value=Decimal("0.01"),
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        help_text="Steht nicht in der Liste; vorgeschlagen ist der Preis der letzten Serie.",
        error_messages={"min_value": "Bitte einen Preis eintragen."},
    )
    zahlungsziel = forms.TypedChoiceField(
        label="Zahlungsziel",
        choices=ZAHLUNGSZIELE,
        coerce=int,
        help_text="Bei Lastschrift der Tag des Einzugs.",
    )
    steuersatz = forms.TypedChoiceField(
        label="Steuersatz",
        choices=Steuersatz.choices,
        coerce=int,
        required=False,
        empty_value=Steuersatz.VOLL,
    )

    def clean_termin(self):
        # Zeilenumbrüche aus einer Excel-Zelle gehören nicht in Betreff und Position.
        return " ".join(self.cleaned_data["termin"].split())

    def clean_thema(self):
        return " ".join(self.cleaned_data["thema"].split())

    def clean_link(self):
        return "".join(self.cleaned_data["link"].split())


class ZuordnungForm(forms.Form):
    """Je Feld die Spalte der Liste; gespeichert wird sie beim Anlegen."""

    def __init__(self, *args, spalten, **kwargs):
        super().__init__(*args, **kwargs)
        wahl = [("", "– keine –")] + [(t, t) for t in spalten]
        for feld, (bezeichnung, _) in FELDER.items():
            self.fields[f"spalte_{feld}"] = forms.ChoiceField(
                label=bezeichnung, choices=wahl, required=False
            )

    def clean(self):
        daten = super().clean()
        for feld in PFLICHT:
            if not daten.get(f"spalte_{feld}"):
                self.add_error(
                    f"spalte_{feld}",
                    "Ohne diese Spalte erkennt Kontorfreund niemanden.",
                )
        gewaehlt = [t for t in daten.values() if t]
        if len(gewaehlt) != len(set(gewaehlt)):
            raise forms.ValidationError("Jede Spalte bitte nur einem Feld zuordnen.")
        return daten

    def zuordnung(self):
        return {
            feld: titel
            for name, titel in self.cleaned_data.items()
            if titel and (feld := name.removeprefix("spalte_"))
        }


class HochladenForm(forms.Form):
    datei = forms.FileField(label="Teilnehmerliste")


def _platzhalter_pruefen(text, erlaubt):
    if unbekannt := texte.unbekannte(text, erlaubt):
        namen = ", ".join("{" + n + "}" for n in unbekannt)
        raise forms.ValidationError(
            f"{'Diesen Platzhalter' if len(unbekannt) == 1 else 'Diese Platzhalter'} "
            f"kennt Kontorfreund hier nicht: {namen}. Möglich sind {texte.liste(erlaubt)}."
        )
    return text.strip()


class VorlageForm(forms.ModelForm):
    beilage_datei = forms.FileField(
        label="PDF-Datei",
        required=False,
        help_text=f"Höchstens {BEILAGE_MB} MB. Geht mit jeder E-Mail als eigene Datei mit, "
        "etwa Hinweise für Einsteiger; die Rechnung selbst bleibt unverändert.",
        widget=forms.FileInput(attrs={"accept": ".pdf,application/pdf"}),
    )
    beilage_entfernen = forms.BooleanField(label="Beilage entfernen", required=False)

    class Meta:
        model = Vorlage
        fields = [
            "betreff",
            "position",
            "kopftext",
            "fusstext",
            "mail_betreff",
            "mail_text",
        ]
        widgets = {
            "kopftext": forms.Textarea(attrs={"rows": 3}),
            "fusstext": forms.Textarea(attrs={"rows": 3}),
            "mail_text": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {
            "kopftext": "Die Briefanrede setzt Kontorfreund selbst davor.",
            "fusstext": "Ihre Grußformel setzt Kontorfreund selbst dahinter.",
            "mail_text": "Briefanrede und Gruß setzt Kontorfreund selbst dazu.",
        }

    def _rechnungstext(self, name):
        return _platzhalter_pruefen(self.cleaned_data[name], texte.RECHNUNG)

    def clean_betreff(self):
        return self._rechnungstext("betreff")

    def clean_position(self):
        return self._rechnungstext("position")

    def clean_kopftext(self):
        return self._rechnungstext("kopftext")

    def clean_fusstext(self):
        return self._rechnungstext("fusstext")

    def clean_mail_betreff(self):
        return _platzhalter_pruefen(self.cleaned_data["mail_betreff"], texte.MAIL)

    def clean_mail_text(self):
        return _platzhalter_pruefen(self.cleaned_data["mail_text"], texte.MAIL)

    def clean_beilage_datei(self):
        datei = self.cleaned_data.get("beilage_datei")
        if not datei:
            return None
        if datei.size > BEILAGE_MB * 1024 * 1024:
            raise forms.ValidationError(f"Die Datei ist größer als {BEILAGE_MB} MB.")
        inhalt = datei.read()
        if not inhalt.startswith(b"%PDF"):
            raise forms.ValidationError("Bitte eine PDF-Datei wählen.")
        # Sie wird beim Drucken an Rechnungen gehängt; was pypdf nicht liest, gilt nicht.
        try:
            if not PdfReader(BytesIO(inhalt)).pages:
                raise PdfReadError
        except (PdfReadError, ValueError, OSError):
            raise forms.ValidationError(
                "Die PDF-Datei lässt sich nicht lesen. Bitte neu speichern und erneut "
                "hochladen."
            ) from None
        try:
            name = get_valid_filename(Path(datei.name).name)[-200:]
        except SuspiciousFileOperation:
            name = "Beilage.pdf"
        return name if name.lower().endswith(".pdf") else f"{name}.pdf", inhalt

    def save(self, commit=True):
        vorlage = super().save(commit=False)
        if neu := self.cleaned_data.get("beilage_datei"):
            vorlage.beilage_name, vorlage.beilage = neu
        elif self.cleaned_data.get("beilage_entfernen"):
            vorlage.beilage_name, vorlage.beilage = "", b""
        if commit:
            vorlage.save()
        return vorlage
