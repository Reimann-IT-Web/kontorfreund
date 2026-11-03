from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.urls import reverse_lazy

from protokoll.erfassen import eintragen
from protokoll.models import Eintrag

from .models import Kategorie, Kontakt, Kontaktweg

# Die PLZ füllt den Ort aus (static/js/app.js); dazu gehört ein Feld mit data-ort.
PLZ_ATTRS = {
    "inputmode": "numeric",
    "autocomplete": "postal-code",
    "data-plz": reverse_lazy("contacts:orte"),
}


HOECHSTENS_KATEGORIEN = 100


def kategorie_finden(name):
    """Die Kategorie dieses Namens, ohne Groß- und Kleinschreibung, sonst None."""
    name = name.casefold()
    return next((k for k in Kategorie.objects.all() if k.name.casefold() == name), None)


def kategorie_name(name):
    """Name einer neuen oder umbenannten Kategorie, bereinigt; sonst ValidationError."""
    name = " ".join(name.split())
    if "," in name or ";" in name:
        raise ValidationError(
            "Bitte ohne Komma und Semikolon, die trennen mehrere Kategorien."
        )
    return name


def kategorie_neu(name):
    """Vorhandene oder neue, noch nicht gespeicherte Kategorie; sonst ValidationError."""
    name = kategorie_name(name)
    if kategorie := kategorie_finden(name):
        return kategorie
    if Kategorie.objects.count() >= HOECHSTENS_KATEGORIEN:
        raise ValidationError(f"Höchstens {HOECHSTENS_KATEGORIEN} Kategorien.")
    return Kategorie(name=name)


def kategorien_protokollieren(kontakt, vorher):
    """Geänderte Kategorien als Ganzes, denn sie hängen nicht an einem Feld."""
    nachher = kontakt.kategorien_text
    if nachher != vorher:
        eintragen(Eintrag.Aktion.GEAENDERT, kontakt, [["Kategorien", vorher, nachher]])


class KategorieForm(forms.ModelForm):
    class Meta:
        model = Kategorie
        fields = ["name"]

    def clean_name(self):
        name = kategorie_name(self.cleaned_data["name"])
        gleich = kategorie_finden(name)
        if gleich and gleich.pk != self.instance.pk:
            raise ValidationError(f"Die Kategorie „{gleich}“ gibt es schon.")
        if not self.instance.pk and Kategorie.objects.count() >= HOECHSTENS_KATEGORIEN:
            raise ValidationError(f"Höchstens {HOECHSTENS_KATEGORIEN} Kategorien.")
        return name


class KontaktForm(forms.ModelForm):
    neue_kategorie = forms.CharField(
        label="Neue Kategorie",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "z. B. Wartungsvertrag"}),
    )

    class Meta:
        model = Kontakt
        fields = [
            "art",
            "kategorien",
            "firmenname",
            "zusatz",
            "anrede",
            "titel",
            "vorname",
            "nachname",
            "position",
            "firma",
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
            "kategorien": forms.CheckboxSelectMultiple,
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
            "firma": "Dann steht die Person bei der Firma, und ihre Einträge erscheinen auch im Verlauf der Firma.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Archivierte Firmen nur, wenn die Person schon zu einer gehört.
        firmen = Kontakt.objects.filter(
            Q(archiviert=False) | Q(pk=self.instance.firma_id),
            art=Kontakt.Art.FIRMA,
            gesperrt_am__isnull=True,
        )
        if self.instance.pk:
            firmen = firmen.exclude(pk=self.instance.pk)
        self.fields["firma"].queryset = firmen
        self.fields["firma"].empty_label = "– keiner Firma –"

    def clean_neue_kategorie(self):
        name = self.cleaned_data["neue_kategorie"]
        return kategorie_neu(name) if name.strip() else None

    def save(self):
        """Mit der neuen Kategorie, wenn eine eingetragen ist."""
        vorher = self.instance.kategorien_text if self.instance.pk else ""
        kontakt = super().save()
        if neu := self.cleaned_data["neue_kategorie"]:
            if neu.pk is None:
                neu.save()
            kontakt.kategorien.add(neu)
        kategorien_protokollieren(kontakt, vorher)
        return kontakt


HOECHSTENS_KONTAKTWEGE = 20
# Vorschläge für die Bezeichnung im Formular.
BEZEICHNUNGEN = ["Büro", "Mobil", "Privat", "Fax", "Zentrale", "Buchhaltung"]


def kontaktwege_lesen(arten, bezeichnungen, werte):
    """Weitere Telefonnummern und E-Mail-Adressen aus den Zeilen des Formulars.

    Leere Zeilen fallen weg; fehlerhafte bleiben in der Liste, damit das Formular
    sie zum Verbessern wieder zeigt, mit der Meldung in `fehler` an der Zeile.
    """
    wege = []
    for art, bezeichnung, wert in zip(arten, bezeichnungen, werte, strict=False):
        wert = wert.strip()
        if art not in Kontaktweg.Art.values or not wert:
            continue
        weg = Kontaktweg(art=art, bezeichnung=bezeichnung.strip()[:50], wert=wert[:254])
        weg.fehler = ""
        if art == Kontaktweg.Art.EMAIL:
            try:
                validate_email(wert)
            except ValidationError:
                weg.fehler = f"„{wert[:60]}“ ist keine gültige E-Mail-Adresse."
        elif len(wert) > 50:
            weg.fehler = (
                f"Die Telefonnummer „{wert[:20]}…“ ist zu lang, höchstens 50 Zeichen."
            )
        wege.append(weg)
    if len(wege) > HOECHSTENS_KONTAKTWEGE and not wege[-1].fehler:
        wege[-1].fehler = (
            f"Höchstens {HOECHSTENS_KONTAKTWEGE} weitere Telefonnummern und "
            "E-Mail-Adressen je Adresse."
        )
    return wege, [w.fehler for w in wege if w.fehler]


def kontaktwege_speichern(kontakt, wege):
    """Ersetzt die weiteren Nummern und Adressen; das Protokoll vermerkt Änderungen.

    Als Ganzes wie die Positionen einer Rechnung, weil sie neu angelegt werden.
    """
    vorher = kontakt.kontaktwege_text
    kontakt.kontaktwege.all().delete()
    for weg in wege:
        weg.kontakt = kontakt
        weg.save()
    nachher = "\n".join(str(w) for w in wege)
    if nachher != vorher:
        eintragen(
            Eintrag.Aktion.GEAENDERT,
            kontakt,
            [["Weitere Telefonnummern und E-Mail-Adressen", vorher, nachher]],
        )
