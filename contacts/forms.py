import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.urls import reverse_lazy

from archive import fristen
from protokoll.erfassen import eintragen
from protokoll.models import Eintrag

from .models import Anschrift, Kategorie, Kontakt, Kontaktweg

# Die PLZ füllt den Ort aus (static/js/app.js); dazu gehört ein Feld mit data-ort.
PLZ_ATTRS = {
    "inputmode": "numeric",
    "autocomplete": "postal-code",
    "data-plz": reverse_lazy("contacts:orte"),
}

# Wie HOECHSTE_NUMMER beim Import.
HOECHSTE_KUNDENNUMMER = 999_999_999


def nummer_lesen(text):
    """„K-0012“ oder „12“ → 12, sonst None."""
    treffer = re.fullmatch(r"(?:K-?)?0*(\d+)", text.strip(), flags=re.IGNORECASE)
    return int(treffer.group(1)) if treffer else None


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
    # Änderbar, solange es keinen Beleg gibt (Spezifikation K-1): Belege nennen sie,
    # und bei DATEV ist sie das Debitorenkonto.
    kundennummer = forms.CharField(
        label="Kundennummer",
        max_length=20,
        required=False,
        help_text="Leer lassen, dann vergibt Kontorfreund die nächste Nummer.",
    )
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
        nummer = self.fields["kundennummer"]
        if self.instance.pk:
            nummer.initial = self.instance.kundennummer
            if fristen.belege(self.instance):
                nummer.disabled = True
                nummer.help_text = (
                    "Steht schon auf Belegen und lässt sich deshalb nicht mehr ändern."
                )
            else:
                nummer.help_text = (
                    "Änderbar, solange es keinen Beleg an diese Adresse gibt."
                )

    def clean_kundennummer(self):
        """None für die nächste Nummer, bei einer Adresse für ihre bisherige."""
        text = self.cleaned_data["kundennummer"].strip()
        if not text:
            return None
        nummer = nummer_lesen(text)
        if not nummer or nummer > HOECHSTE_KUNDENNUMMER:
            raise ValidationError("Bitte eine Nummer wie K-0012 oder 12.")
        if Kontakt.objects.filter(nummer=nummer).exclude(pk=self.instance.pk).exists():
            raise ValidationError(f"K-{nummer:04d} ist schon vergeben.")
        return nummer

    def clean_neue_kategorie(self):
        name = self.cleaned_data["neue_kategorie"]
        return kategorie_neu(name) if name.strip() else None

    def save(self):
        """Mit der neuen Kategorie, wenn eine eingetragen ist."""
        vorher = self.instance.kategorien_text if self.instance.pk else ""
        alt = self.instance.kundennummer if self.instance.pk else ""
        if (nummer := self.cleaned_data["kundennummer"]) is not None:
            self.instance.nummer = nummer
        kontakt = super().save()
        # Die Nummer ist kein Feld, das das Protokoll von selbst erfasst.
        if alt and kontakt.kundennummer != alt:
            eintragen(
                Eintrag.Aktion.GEAENDERT,
                kontakt,
                [["Kundennummer", alt, kontakt.kundennummer]],
            )
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


HOECHSTENS_ANSCHRIFTEN = 20


def anschriften_lesen(kontakt, ids, arten, zusaetze, strassen, plzs, orte, laender):
    """Weitere Anschriften aus den Zeilen des Formulars, vorhandene mit ihrer ID.

    Wie `kontaktwege_lesen`: Leere Zeilen fallen weg, fehlerhafte behalten ihre
    Meldung in `fehler`. Eine Anschrift, die auf einem festgeschriebenen oder
    fertigen Beleg steht, lässt sich nicht entfernen, nur ändern, denn Storno und
    Korrektur übernehmen sie; entfernt kommt sie mit einer Meldung zurück.
    """
    vorhanden = (
        {a.pk: a for a in Anschrift.objects.filter(kontakt=kontakt)} if kontakt else {}
    )
    anschriften = []
    zeilen = zip(ids, arten, zusaetze, strassen, plzs, orte, laender, strict=False)
    for nr, art, *werte in zeilen:
        zusatz, strasse, plz, ort, land = (t.strip() for t in werte)
        if not (zusatz or strasse or plz or ort):
            continue
        anschrift = (
            vorhanden.pop(int(nr), None) if nr.isdigit() else None
        ) or Anschrift()
        anschrift.art = art if art in Anschrift.Art.values else Anschrift.Art.SONSTIGE
        anschrift.zusatz = zusatz[:200]
        anschrift.strasse = strasse[:200]
        anschrift.plz = plz[:10]
        anschrift.ort = ort[:100]
        anschrift.land = land[:100]
        anschrift.fehler = (
            ""
            if anschrift.anschrift_vollstaendig
            else "Bitte Straße, PLZ und Ort angeben."
        )
        anschriften.append(anschrift)
    if vorhanden:
        auf_belegen = {}
        for beleg in fristen.belege(kontakt):
            for feld in ("anschrift_id", "lieferanschrift_id"):
                auf_belegen.setdefault(getattr(beleg.objekt, feld, None), beleg)
        for pk, anschrift in vorhanden.items():
            if beleg := auf_belegen.get(pk):
                anschrift.fehler = (
                    f"Steht auf {beleg.art} {beleg.nummer} und bleibt deshalb. "
                    "Ändern können Sie sie."
                )
                anschriften.append(anschrift)
    if len(anschriften) > HOECHSTENS_ANSCHRIFTEN and not anschriften[-1].fehler:
        anschriften[
            -1
        ].fehler = f"Höchstens {HOECHSTENS_ANSCHRIFTEN} weitere Anschriften je Adresse."
    return anschriften, [a.fehler for a in anschriften if a.fehler]


def anschriften_speichern(kontakt, anschriften):
    """Ändert, ergänzt und entfernt die weiteren Anschriften.

    Als Ganzes ins Protokoll wie die weiteren Telefonnummern. Entwürfe mit einer
    entfernten Anschrift nehmen wieder die Standardanschrift bzw. keine Lieferanschrift.
    """
    vorher = kontakt.anschriften_text
    kontakt.anschriften.exclude(pk__in=[a.pk for a in anschriften if a.pk]).delete()
    for anschrift in anschriften:
        anschrift.kontakt = kontakt
        anschrift.save()
    nachher = kontakt.anschriften_text
    if nachher != vorher:
        eintragen(
            Eintrag.Aktion.GEAENDERT,
            kontakt,
            [["Weitere Anschriften", vorher, nachher]],
        )
