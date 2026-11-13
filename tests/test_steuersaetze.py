"""Steuersätze je Position: 19 % und 7 % auf einem Beleg (Spezifikation B-4) – erfundene Daten."""

import re
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.urls import reverse
from pypdf import PdfReader

from angebote import beleg as angebotsbeleg
from angebote.models import Angebot
from angebote.models import Position as Angebotsposition
from artikel.models import Artikel
from auftraege import beleg as auftragsbeleg
from auswertungen import buch, datev
from auswertungen.models import Datev
from contacts.models import Kontakt
from core.models import Firmendaten
from importe import lesen, uebernahme, vorlagen
from importe.models import Import
from invoicing.beleg import beleg_steuern, druck_summen, druckdaten
from invoicing.models import Position, Rechnung, steuergruppen, summen
from protokoll.erfassen import positionen_text
from vertraege import abrechnen
from vertraege.models import Position as Vertragsposition
from vertraege.models import Vertrag

pytestmark = pytest.mark.django_db

# Eine Stornorechnung trägt immer das heutige Datum; alle Belege richten sich danach.
HEUTE = date.today()


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster Medien"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.email = "post@muster.test"
    f.iban = "DE02120300000000202051"
    f.umsatzsteuer = Firmendaten.Umsatzsteuer.REGEL
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Buchhandlung Seite", strasse="Markt 3", plz="55116", ort="Mainz"
    )


def formular(kunde, aktion="festschreiben", **mehr):
    """Webdesign 10 × 80 € zu 19 % und zwei Fachbücher zu je 24,95 € zu 7 %."""
    return {
        "kontakt": kunde.pk,
        "datum": HEUTE.isoformat(),
        "leistung_von": HEUTE.isoformat(),
        "zahlungsziel": "14",
        "steuerfall": "regel",
        "kopftext": "Sehr geehrte Damen und Herren,",
        "fusstext": "Mit freundlichen Grüßen",
        "bezeichnung": ["Webdesign", "Fachbuch Typografie"],
        "beschreibung": ["", ""],
        "menge": ["10", "2"],
        "einheit": ["Std.", "Stück"],
        "preis": ["80,00", "24,95"],
        "steuersatz": ["19", "7"],
        "aktion": aktion,
        **mehr,
    }


def festschreiben(client, kunde, **mehr):
    client.post(reverse("invoicing:neu"), formular(kunde, **mehr))
    rechnung = Rechnung.objects.latest("pk")
    assert not rechnung.ist_entwurf
    return rechnung


def pdf(settings, beleg):
    return PdfReader(BytesIO((settings.DATA_DIR / beleg.datei).read_bytes()))


def seitentext(settings, beleg):
    return " ".join(pdf(settings, beleg).pages[0].extract_text().split())


def xml(settings, beleg):
    return pdf(settings, beleg).attachments["factur-x.xml"][0].decode()


def positionen(*zeilen):
    """Ungespeicherte Positionen aus (Menge, Preis, Satz)."""
    return [
        Position(menge=Decimal(m), preis=Decimal(p), steuersatz=s) for m, p, s in zeilen
    ]


def test_rabatt_und_steuer_je_satz():
    gruppen = steuergruppen(
        positionen(("10", "80", 19), ("2", "24.95", 7)), "regel", Decimal("8")
    )

    assert [(g.satz, g.zwischensumme, g.rabatt, g.netto, g.ust) for g in gruppen] == [
        (19, Decimal("800.00"), Decimal("64.00"), Decimal("736.00"), Decimal("139.84")),
        (7, Decimal("49.90"), Decimal("3.99"), Decimal("45.91"), Decimal("3.21")),
    ]


def test_keine_negative_null_bei_storno():
    (gruppe,) = steuergruppen(positionen(("-2", "24.95", 7)), "kleinunternehmer")

    assert str(gruppe.ust) == "0.00"


def test_ohne_umsatzsteuer_zaehlt_der_satz_nicht():
    alle = positionen(("10", "80", 19), ("2", "24.95", 7))

    for fall in ("kleinunternehmer", "13b", "steuerfrei"):
        (gruppe,) = steuergruppen(alle, fall)
        assert (gruppe.satz, gruppe.netto, gruppe.ust) == (
            0,
            Decimal("849.90"),
            Decimal("0.00"),
        )
        assert summen(alle, fall) == (
            Decimal("849.90"),
            Decimal("0.00"),
            Decimal("849.90"),
        )


def test_rechnung_mit_19_und_7_prozent(client, firma, kunde, settings):
    rechnung = festschreiben(client, kunde)

    assert (rechnung.netto, rechnung.ust, rechnung.brutto) == (
        Decimal("849.90"),
        Decimal("155.49"),
        Decimal("1005.39"),
    )
    assert [p.steuersatz for p in rechnung.positionen.all()] == [19, 7]
    assert [p["steuersatz"] for p in rechnung.beleg["positionen"]] == [19, 7]
    assert [(g["satz"], g["netto"], g["ust"]) for g in rechnung.beleg["steuern"]] == [
        (19, "800.00", "152.00"),
        (7, "49.90", "3.49"),
    ]

    # § 14 Abs. 4 Nr. 7 und 8 UStG: Entgelt und Steuer je Satz, Satz je Position.
    druck = druckdaten(rechnung.beleg)
    assert druck["ust_spalte"]
    assert [p["satz"] for p in druck["positionen"]] == ["19 %", "7 %"]
    assert druck["summen"] == [
        ["Nettobetrag zu 19 %", "800,00\xa0€"],
        ["Umsatzsteuer 19 %", "152,00\xa0€"],
        ["Nettobetrag zu 7 %", "49,90\xa0€"],
        ["Umsatzsteuer 7 %", "3,49\xa0€"],
    ]
    text = seitentext(settings, rechnung)
    for teil in ("USt Gesamt", "Nettobetrag zu 7 %", "Umsatzsteuer 7 %", "1.005,39 €"):
        assert teil in text

    # Zeilen mit ihrem Satz, Aufschlüsselung je Satz (BG-23).
    daten = xml(settings, rechnung)
    assert re.findall(r"<ram:RateApplicablePercent>([\d.]+)<", daten) == [
        "19",
        "7",
        "19",
        "7",
    ]
    assert "<ram:CalculatedAmount>152.00</ram:CalculatedAmount>" in daten
    assert "<ram:CalculatedAmount>3.49</ram:CalculatedAmount>" in daten
    assert '<ram:TaxTotalAmount currencyID="EUR">155.49</ram:TaxTotalAmount>' in daten
    assert "<ram:GrandTotalAmount>1005.39</ram:GrandTotalAmount>" in daten


def test_rabatt_je_steuersatz_in_der_e_rechnung(client, firma, kunde, settings):
    rechnung = festschreiben(client, kunde, rabatt_prozent="8")

    assert (rechnung.netto, rechnung.ust, rechnung.brutto) == (
        Decimal("781.91"),
        Decimal("143.05"),
        Decimal("924.96"),
    )
    assert rechnung.beleg["rabatt"] == {
        "prozent": "8.00",
        "zwischensumme": "849.90",
        "betrag": "67.99",
    }
    # Ein Abschlag je Steuersatz (BG-20), mit dessen Satz (BR-S-08).
    daten = xml(settings, rechnung)
    abschlaege = re.findall(
        r"<ram:SpecifiedTradeAllowanceCharge>.*?</ram:SpecifiedTradeAllowanceCharge>",
        daten,
        re.S,
    )
    assert len(abschlaege) == 2
    assert "<ram:ActualAmount>64.00</ram:ActualAmount>" in abschlaege[0]
    assert "<ram:RateApplicablePercent>19" in abschlaege[0]
    assert "<ram:ActualAmount>3.99</ram:ActualAmount>" in abschlaege[1]
    assert "<ram:RateApplicablePercent>7" in abschlaege[1]
    assert "<ram:AllowanceTotalAmount>67.99</ram:AllowanceTotalAmount>" in daten


def test_nur_7_prozent_ohne_extra_spalte(client, firma, kunde, settings):
    rechnung = festschreiben(client, kunde, steuersatz=["7", "7"])

    assert (rechnung.netto, rechnung.ust) == (Decimal("849.90"), Decimal("59.49"))
    druck = druckdaten(rechnung.beleg)
    assert not druck["ust_spalte"]
    assert druck["summen"] == [
        ["Nettobetrag", "849,90\xa0€"],
        ["Umsatzsteuer 7 %", "59,49\xa0€"],
    ]
    assert "Umsatzsteuer 7 %" in seitentext(settings, rechnung)


def test_kleinunternehmer_ignoriert_den_satz(client, firma, kunde, settings):
    rechnung = festschreiben(client, kunde, steuerfall="kleinunternehmer")

    assert (rechnung.ust, rechnung.brutto) == (Decimal("0.00"), Decimal("849.90"))
    assert [p.steuersatz for p in rechnung.positionen.all()] == [19, 7]
    assert not druckdaten(rechnung.beleg)["ust_spalte"]
    assert re.findall(
        r"<ram:RateApplicablePercent>([\d.]+)<", xml(settings, rechnung)
    ) == ["0", "0", "0"]


def test_storno_behaelt_die_saetze(client, firma, kunde):
    original = festschreiben(client, kunde)

    client.post(reverse("invoicing:stornieren", args=[original.pk]))

    storno = Rechnung.objects.get(storno_zu=original)
    assert [p.steuersatz for p in storno.positionen.all()] == [19, 7]
    assert storno.brutto == Decimal("-1005.39")
    assert [g["ust"] for g in storno.beleg["steuern"]] == ["-152.00", "-3.49"]


def test_unbekannter_satz_wird_abgelehnt(client, firma, kunde):
    antwort = client.post(
        reverse("invoicing:neu"),
        formular(kunde, aktion="speichern", steuersatz=["19", "16"]),
        follow=True,
    )

    assert "Position 2: Steuersatz bitte 19 % oder 7 %." in antwort.text
    assert not Rechnung.objects.exists()


def test_editor_zeigt_den_satz_nur_mit_umsatzsteuer(client, firma):
    for adresse in ("invoicing:neu", "angebote:neu", "auftraege:neu", "vertraege:neu"):
        html = client.get(reverse(adresse)).text
        assert '<select name="steuersatz" aria-label="Umsatzsteuer">' in html, adresse
        assert "data-satz-spalte hidden" not in html, adresse

    firma.umsatzsteuer = Firmendaten.Umsatzsteuer.KLEINUNTERNEHMER
    firma.save()
    html = client.get(reverse("invoicing:neu")).text
    assert '<select name="steuersatz"' in html, "gesendet wird der Satz immer"
    assert "data-satz-spalte hidden" in html


def test_angebot_auftrag_und_vertrag_reichen_den_satz_weiter(firma, kunde):
    angebot = Angebot.objects.create(kontakt=kunde, steuerfall="regel")
    for nr, (bezeichnung, preis, satz) in enumerate(
        [("Webdesign", "800", 19), ("Fachbuch", "49.90", 7)], 1
    ):
        Angebotsposition.objects.create(
            angebot=angebot,
            nr=nr,
            bezeichnung=bezeichnung,
            preis=preis,
            steuersatz=satz,
        )

    b = angebotsbeleg.beleg_daten(angebot, firma, "T-1")
    assert [g["satz"] for g in b["steuern"]] == [19, 7]
    assert angebotsbeleg.druckdaten(b)["ust_spalte"]
    assert [p.steuersatz for p in angebot.kopieren().positionen.all()] == [19, 7]

    rechnung = angebotsbeleg.rechnung_erstellen(angebot, firma)
    assert [p.steuersatz for p in rechnung.positionen.all()] == [19, 7]
    auftrag = auftragsbeleg.aus_angebot(angebot, firma)
    assert [p.steuersatz for p in auftrag.positionen.all()] == [19, 7]

    vertrag = Vertrag.objects.create(
        bezeichnung="Wartung", kontakt=kunde, beginn=HEUTE, steuerfall="regel"
    )
    Vertragsposition.objects.create(vertrag=vertrag, nr=1, preis=10, steuersatz=7)
    entwurf = abrechnen.entwurf(vertrag, HEUTE, HEUTE)
    assert [p.steuersatz for p in entwurf.positionen.all()] == [7]


def test_artikel_mit_ermaessigtem_satz(client, firma):
    client.post(
        reverse("artikel:neu"),
        {
            "bezeichnung": "Fachbuch Typografie",
            "einheit": "Stück",
            "preis": "24,95",
            "steuersatz": "7",
        },
    )

    artikel = Artikel.objects.get()
    assert artikel.steuersatz == 7
    assert "7 % USt" in client.get(reverse("artikel:liste")).text
    assert (
        'data-preis="24,95" data-steuersatz="7"'
        in client.get(reverse("invoicing:neu")).text
    )


def test_kleinunternehmer_sieht_keinen_satz_am_artikel(client, firma):
    firma.umsatzsteuer = Firmendaten.Umsatzsteuer.KLEINUNTERNEHMER
    firma.save()

    assert 'name="steuersatz"' not in client.get(reverse("artikel:neu")).text
    client.post(
        reverse("artikel:neu"),
        {"bezeichnung": "Beratung", "einheit": "Std.", "preis": "80"},
    )
    assert Artikel.objects.get().steuersatz == 19

    # Ein ermäßigter Satz bleibt sichtbar, damit er sich zurücksetzen lässt.
    buch = Artikel.objects.create(bezeichnung="Buch", preis=10, steuersatz=7)
    seite = client.get(reverse("artikel:bearbeiten", args=[buch.pk])).text
    assert 'name="steuersatz"' in seite


def test_import_versteht_den_steuersatz(inhaber):
    inhalt = (
        "Artikel;VK netto;MwSt\n"
        "Fachbuch;24,95;7 %\n"
        "Beratung;80;\n"
        "Zeitschrift;4,50;0,07\n"
        "Kochbuch;19,90;ermäßigt\n"
        "Wein;9;16\n"
    ).encode()
    spalten, zeilen = lesen.lesen(inhalt)
    _, zuordnung = vorlagen.vorschlagen("artikel", spalten, [])
    assert zuordnung["steuersatz"] == "MwSt"

    bericht = uebernahme.pruefen(
        Import.objects.create(
            ziel="artikel",
            dateiname="liste.csv",
            spalten=spalten,
            zeilen=zeilen,
            zuordnung=zuordnung,
            benutzer=inhaber,
            bestaetigt=True,
        )
    )

    assert [(a.bezeichnung, a.steuersatz) for a in bericht.neu] == [
        ("Fachbuch", 7),
        ("Beratung", 19),
        ("Zeitschrift", 7),
        ("Kochbuch", 7),
    ]
    ((nr, meldungen),) = bericht.fehler
    assert nr == 6 and "Steuersatz: „16“" in meldungen[0]


def test_datev_bucht_je_steuersatz(client, firma, kunde):
    einstellung = Datev.laden()
    einstellung.beraternummer = 1001
    einstellung.mandantennummer = 7
    einstellung.save()
    rechnung = festschreiben(client, kunde)

    buchungen = datev.buchungen(HEUTE, HEUTE, einstellung)

    assert [(b.gegenkonto, b.betrag, b.soll_haben) for b in buchungen] == [
        (8400, Decimal("952.00"), "S"),
        (8300, Decimal("53.39"), "S"),
    ]
    assert sum(b.betrag for b in buchungen) == rechnung.brutto
    einstellung.kontenrahmen = Datev.Kontenrahmen.SKR04
    assert einstellung.erloeskonto("regel", 7) == 4300
    einstellung.erloes_regel7 = 8310
    assert einstellung.erloeskonto("regel", 7) == 8310

    paket = datev.mit_rechnungen(b"", "EXTF.csv", buchungen)
    namen = zipfile.ZipFile(BytesIO(paket)).namelist()
    assert namen == ["EXTF.csv", f"Rechnungen/Rechnung-{rechnung.nummer}.pdf"]


def test_ausgangsbuch_nennt_die_saetze(client, firma, kunde):
    rechnung = festschreiben(client, kunde)

    assert buch.steuer_text(rechnung) == "19 % und 7 %"
    zeile, _ = buch.zeilen(HEUTE, HEUTE)[0]
    assert zeile.steuer == "19 % und 7 %"


def test_aeltere_belege_haben_19_prozent():
    """Belege vor den Steuersätzen je Position: kein „steuern“, kein Satz je Position."""
    alt = {
        "steuerfall": "regel",
        "rabatt": None,
        "netto": "100.00",
        "ust": "19.00",
        "positionen": [],
    }

    assert beleg_steuern(alt) == [
        {
            "satz": 19,
            "zwischensumme": "100.00",
            "rabatt": "0.00",
            "netto": "100.00",
            "ust": "19.00",
        }
    ]
    assert druck_summen(alt) == [
        ["Nettobetrag", "100,00\xa0€"],
        ["Umsatzsteuer 19 %", "19,00\xa0€"],
    ]
    assert buch.steuer_text(Rechnung(steuerfall="regel", beleg={})) == "19 %"


def test_protokoll_nennt_den_ermaessigten_satz():
    text = positionen_text(
        [
            Position(nr=1, bezeichnung="Webdesign", menge=1, preis=80, steuersatz=19),
            Position(nr=2, bezeichnung="Fachbuch", menge=1, preis=20, steuersatz=7),
        ]
    )

    assert text.splitlines()[0].endswith("80,00\xa0€")
    assert text.splitlines()[1].endswith("(7 % USt)")
