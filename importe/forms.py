from itertools import islice

from django import forms

from contacts.models import Kontakt

from .vorlagen import FELDER


class HochladenForm(forms.Form):
    datei = forms.FileField(
        label="Tabelle auswählen",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.txt,.xlsx,.ods"}),
    )


class ZuordnungForm(forms.Form):
    """Je Feld die Spalte der Datei (Feldname mit Vorsatz „spalte_“) und die Optionen."""

    kategorie = forms.ChoiceField(
        label="Kategorie, wenn die Datei keine angibt",
        choices=Kontakt.Kategorie.choices,
        widget=forms.RadioSelect,
    )
    dubletten_anlegen = forms.TypedChoiceField(
        label="Mögliche Dubletten",
        choices=[("", "überspringen"), ("1", "trotzdem anlegen")],
        coerce=bool,
        empty_value=False,
        required=False,
        widget=forms.RadioSelect,
    )
    speichern_als = forms.CharField(
        label="Zuordnung speichern als",
        max_length=100,
        required=False,
        help_text="Dann erkennt Kontorfreund Dateien mit denselben Spalten beim nächsten Mal selbst, z. B. „Kundenliste aus dem alten Programm“.",
    )

    def __init__(self, imp, *args, **kwargs):
        initial = {f"spalte_{feld}": spalte for feld, spalte in imp.zuordnung.items()}
        initial |= {
            "kategorie": imp.kategorie,
            "dubletten_anlegen": "1" if imp.dubletten_anlegen else "",
        }
        super().__init__(*args, initial=initial, **kwargs)
        self.imp = imp
        wahl = [("", "– nicht übernehmen –")] + [(s, s) for s in imp.spalten]
        for feld, titel in FELDER[imp.ziel]:
            self.fields[f"spalte_{feld}"] = forms.ChoiceField(
                label=titel, choices=wahl, required=False
            )
        if imp.ziel != "kontakte":
            del self.fields["kategorie"]

    def zuordnung(self):
        return {
            feld: self.cleaned_data[f"spalte_{feld}"]
            for feld, _ in FELDER[self.imp.ziel]
            if self.cleaned_data.get(f"spalte_{feld}")
        }

    def clean(self):
        daten = super().clean()
        zuordnung = self.zuordnung()
        if self.imp.ziel == "kontakte" and not {"firmenname", "nachname"} & set(
            zuordnung
        ):
            raise forms.ValidationError(
                "Bitte ordnen Sie mindestens den Firmennamen oder den Nachnamen zu."
            )
        if self.imp.ziel == "artikel":
            for feld, titel in FELDER["artikel"]:
                if feld in ("bezeichnung", "preis") and feld not in zuordnung:
                    self.add_error(
                        f"spalte_{feld}",
                        f"Ohne {titel} lässt sich kein Artikel anlegen.",
                    )
        return daten

    def felder(self):
        """(Formularfeld, Beispiele aus den ersten Zeilen) je Feld, für die Tabelle."""
        ergebnis = []
        for feld, _ in FELDER[self.imp.ziel]:
            f = self[f"spalte_{feld}"]
            spalte = f.value()
            beispiele = []
            if spalte in self.imp.spalten:
                i = self.imp.spalten.index(spalte)
                beispiele = list(islice((w[i] for _, w in self.imp.zeilen if w[i]), 2))
            ergebnis.append((f, beispiele))
        return ergebnis
