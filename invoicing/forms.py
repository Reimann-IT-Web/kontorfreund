from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import forms

from contacts.models import Kontakt

from .models import Position, Rechnung

ZAHLUNGSZIELE = [(0, "sofort"), (7, "7 Tage"), (14, "14 Tage"), (30, "30 Tage")]


def dezimal(text):
    """Deutsche Schreibweise wie im Editor: Punkte sind Tausender, Komma trennt Dezimalen."""
    return Decimal(text.strip().replace(".", "").replace(",", ".") or "0")


class Betrag(forms.DecimalField):
    """Euro in deutscher Schreibweise wie im Rechnungseditor, z. B. 1.250,00."""

    def to_python(self, value):
        if isinstance(value, str) and value.strip():
            try:
                value = dezimal(value)
            except InvalidOperation:
                raise forms.ValidationError(
                    self.error_messages["invalid"], code="invalid"
                ) from None
        return super().to_python(value)


class RechnungForm(forms.ModelForm):
    zahlungsziel = forms.TypedChoiceField(
        label="Zahlungsziel", choices=ZAHLUNGSZIELE, coerce=int, initial=14
    )
    skonto_prozent = Betrag(
        label="Skonto in Prozent",
        required=False,
        min_value=0,
        max_value=10,
        decimal_places=2,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "placeholder": "0"}),
    )
    skonto_tage = forms.IntegerField(
        label="Skonto innerhalb von Tagen",
        required=False,
        min_value=0,
        widget=forms.TextInput(attrs={"inputmode": "numeric"}),
    )

    class Meta:
        model = Rechnung
        fields = [
            "kontakt",
            "datum",
            "leistung_von",
            "leistung_bis",
            "zahlungsziel",
            "skonto_prozent",
            "skonto_tage",
            "steuerfall",
            "referenz",
            "betreff",
            "kopftext",
            "fusstext",
            "girocode",
            "verzugshinweis",
        ]
        widgets = {
            "datum": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "leistung_von": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "aria-describedby": "zeitraum-hinweis"},
            ),
            "leistung_bis": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "aria-describedby": "zeitraum-hinweis"},
            ),
            "referenz": forms.TextInput(attrs={"aria-describedby": "referenz-hinweis"}),
            "betreff": forms.TextInput(
                attrs={"placeholder": "z. B. Leistungen im Oktober"}
            ),
            "kopftext": forms.Textarea(attrs={"rows": 4}),
            "fusstext": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "%s")
        super().__init__(*args, **kwargs)
        self.fields["kontakt"].queryset = Kontakt.objects.filter(archiviert=False)
        if not self.instance.skonto_prozent:
            # Leere Felder statt „0“, sonst wird aus einer eingetippten 2 eine 20.
            self.initial["skonto_prozent"] = self.initial["skonto_tage"] = None
        if self.instance.ist_korrektur:
            # Die Korrektur gilt für Empfänger und Steuerfall des Originals; zu zahlen ist nichts.
            for name in (
                "kontakt",
                "steuerfall",
                "zahlungsziel",
                "skonto_prozent",
                "skonto_tage",
                "girocode",
            ):
                self.fields[name].disabled = True

    def clean(self):
        daten = super().clean()
        prozent = daten.get("skonto_prozent") or Decimal("0")
        tage = daten.get("skonto_tage") or 0
        ziel = daten.get("zahlungsziel")
        if not prozent:
            tage = 0
        elif ziel == 0:
            self.add_error("skonto_prozent", "Bei „sofort“ gibt es kein Skonto.")
        elif not tage:
            self.add_error("skonto_tage", "Bitte die Tage für das Skonto eintragen.")
        elif ziel is not None and tage >= ziel:
            self.add_error(
                "skonto_tage", "Die Skontofrist muss kürzer sein als das Zahlungsziel."
            )
        daten["skonto_prozent"], daten["skonto_tage"] = prozent, tage
        return daten


def positionen_lesen(post, korrektur=False, modell=Position):
    """Positionszeilen aus dem Editor; leere Zeilen fallen weg.

    Negative Mengen nur in einer Rechnungskorrektur, negative Preise nie (BR-27).
    `modell` ist die Positionsklasse der Belegart, z. B. die des Angebots.
    """
    spalten = [
        post.getlist(name)
        for name in ("bezeichnung", "beschreibung", "menge", "einheit", "preis")
    ]
    positionen, fehler = [], []
    for zeile, (bez, besch, menge, einheit, preis) in enumerate(
        zip(*spalten, strict=False), 1
    ):
        if not (bez.strip() or besch.strip() or preis.strip()):
            continue
        try:
            menge = dezimal(menge).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            preis = dezimal(preis).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            fehler.append(f"Position {zeile}: Menge und Preis bitte als Zahl eingeben.")
            continue
        if preis < 0 or (menge < 0 and not korrektur):
            fehler.append(
                f"Position {zeile}: Menge und Preis dürfen nicht negativ sein."
            )
            continue
        positionen.append(
            modell(
                nr=len(positionen) + 1,
                bezeichnung=bez.strip()[:200],
                beschreibung=besch.strip(),
                menge=menge,
                einheit=einheit.strip()[:20],
                preis=preis,
            )
        )
    return positionen, fehler


class VersandForm(forms.Form):
    an = forms.EmailField(label="An")
    betreff = forms.CharField(label="Betreff", max_length=200)
    text = forms.CharField(label="Nachricht", widget=forms.Textarea(attrs={"rows": 8}))
    kopie = forms.BooleanField(label="Kopie an mich", required=False, initial=True)
