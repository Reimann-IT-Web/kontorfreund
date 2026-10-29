from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import forms

from contacts.models import Kontakt

from .models import Position, Rechnung

ZAHLUNGSZIELE = [(0, "sofort"), (7, "7 Tage"), (14, "14 Tage"), (30, "30 Tage")]


def dezimal(text):
    """Deutsche Schreibweise wie im Editor: Punkte sind Tausender, Komma trennt Dezimalen."""
    return Decimal(text.strip().replace(".", "").replace(",", ".") or "0")


class RechnungForm(forms.ModelForm):
    zahlungsziel = forms.TypedChoiceField(
        label="Zahlungsziel", choices=ZAHLUNGSZIELE, coerce=int, initial=14
    )

    class Meta:
        model = Rechnung
        fields = [
            "kontakt",
            "datum",
            "leistung_von",
            "leistung_bis",
            "zahlungsziel",
            "steuerfall",
            "referenz",
            "betreff",
            "kopftext",
            "fusstext",
            "girocode",
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


def positionen_lesen(post):
    """Positionszeilen aus dem Editor; leere Zeilen fallen weg."""
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
        if menge < 0 or preis < 0:
            fehler.append(
                f"Position {zeile}: Menge und Preis dürfen nicht negativ sein."
            )
            continue
        positionen.append(
            Position(
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
