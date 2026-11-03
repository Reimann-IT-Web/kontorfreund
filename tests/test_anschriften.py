"""Mehrere Anschriften je Adresse: Rechnung, Lieferung, Sonstige (Spezifikation K-1) – mit erfundenen Daten."""

import csv
import re
from datetime import date
from io import BytesIO, StringIO

import pytest
from django.urls import reverse
from pypdf import PdfReader

from angebote.models import Angebot
from auftraege import beleg as auftragsbeleg
from backups import gesamtexport
from contacts import datenschutz
from contacts.models import Anschrift, Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from protokoll.models import Eintrag
from zahlungen import mahnen

pytestmark = pytest.mark.django_db

FIRMA = {"art": "firma", "firmenname": "Muster Bäckerei GmbH", "land": "Deutschland"}
WEITERE = "Weitere Anschriften"


def anschriften(*zeilen):
    """Formularfelder für Zeilen (ID, Art, Zusatz, Straße, PLZ, Ort, Land)."""
    namen = ("id", "art", "zusatz", "strasse", "plz", "ort", "land")
    return {
        f"anschrift_{name}": spalte
        for name, spalte in zip(namen, zip(*zeilen, strict=True), strict=True)
    }


def eintraege(kontakt):
    """Protokolleinträge zu den weiteren Anschriften: (vorher, nachher)."""
    return [
        tuple(e.aenderungen[0][1:])
        for e in Eintrag.objects.filter(
            aktion=Eintrag.Aktion.GEAENDERT, objekt_id=str(kontakt.pk)
        ).order_by("pk")
        if e.aenderungen[0][0] == WEITERE
    ]


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.email = "post@muster.test"
    f.iban = "DE02120300000000202051"
    f.save()
    return f


@pytest.fixture
def kunde():
    kunde = Kontakt.objects.create(
        firmenname="Muster Bäckerei GmbH",
        vorname="Lea",
        nachname="Sommer",
        anrede="Frau",
        strasse="Lindenweg 4",
        plz="55116",
        ort="Mainz",
        email="buchhaltung@baeckerei.test",
    )
    Anschrift.objects.create(
        kontakt=kunde,
        art="lieferung",
        zusatz="Lager Nord",
        strasse="Hafenstraße 9",
        plz="55120",
        ort="Mainz",
    )
    Anschrift.objects.create(
        kontakt=kunde,
        art="rechnung",
        zusatz="Buchhaltung",
        strasse="Postfach 12 34",
        plz="55001",
        ort="Mainz",
    )
    return kunde


def rechnungsanschrift(kunde):
    return kunde.anschriften.get(art="rechnung")


def lieferanschrift(kunde):
    return kunde.anschriften.get(art="lieferung")


def rechnung_formular(kunde, aktion="festschreiben", **mehr):
    return {
        "kontakt": kunde.pk,
        "anschrift": rechnungsanschrift(kunde).pk,
        "lieferanschrift": lieferanschrift(kunde).pk,
        "datum": "2026-10-29",
        "leistung_von": "2026-10-01",
        "zahlungsziel": "14",
        "steuerfall": "kleinunternehmer",
        "kopftext": "Sehr geehrte Frau Sommer,",
        "fusstext": "Mit freundlichen Grüßen",
        "bezeichnung": ["Webdesign"],
        "beschreibung": [""],
        "menge": ["10"],
        "einheit": ["Std."],
        "preis": ["80,00"],
        "aktion": aktion,
        **mehr,
    }


def gewaehlt(seite, name):
    """Werte der vorgewählten Einträge in der Auswahl `name`."""
    auswahl = seite.split(f'<select id="{name}" name="{name}"')[1].split("</select>")[0]
    return re.findall(r'<option value="(\d+)"[^>]* selected>', auswahl)


def seitentext(pfad):
    return " ".join(
        PdfReader(BytesIO(pfad.read_bytes())).pages[0].extract_text().split()
    )


def test_zeilen_mit_weiterer_anschrift(kunde):
    lager = lieferanschrift(kunde)

    assert kunde.anschrift_zeilen() == [
        "Muster Bäckerei GmbH",
        "Frau Lea Sommer",
        "Lindenweg 4",
        "55116 Mainz",
    ]
    # Die Zusatzzeile steht anstelle des Ansprechpartners.
    assert kunde.anschrift_zeilen(lager) == [
        "Muster Bäckerei GmbH",
        "Lager Nord",
        "Hafenstraße 9",
        "55120 Mainz",
    ]
    lager.zusatz, lager.land = "", "Österreich"
    assert kunde.anschrift_zeilen(lager)[1:] == [
        "Frau Lea Sommer",
        "Hafenstraße 9",
        "55120 Mainz",
        "Österreich",
    ]
    assert str(lager) == "Lieferung: Hafenstraße 9, 55120 Mainz, Österreich"
    assert lager.bezeichnung == "Lieferanschrift"
    assert kunde.anschrift_fuer("rechnung").zusatz == "Buchhaltung"
    assert kunde.anschrift_fuer("sonstige") is None


def test_anlegen_aendern_entfernen_und_protokoll(client):
    antwort = client.post(
        reverse("contacts:neu"),
        {
            **FIRMA,
            **anschriften(
                (
                    "",
                    "rechnung",
                    " Buchhaltung ",
                    "Postfach 12 34",
                    "55001",
                    "Mainz",
                    "",
                ),
                ("", "lieferung", "", "", "", "", "Deutschland"),
                ("", "quatsch", "", "Hafenstraße 9", "55120", "Mainz", "Deutschland"),
            ),
        },
    )

    assert antwort.status_code == 302
    kunde = Kontakt.objects.get()
    rechnung, sonstige = kunde.anschriften.all()
    assert (rechnung.art, rechnung.zusatz, rechnung.land) == (
        "rechnung",
        "Buchhaltung",
        "",
    )
    assert sonstige.art == "sonstige"  # unbekannte Art
    assert eintraege(kunde) == [
        (
            "",
            "Rechnung: Buchhaltung, Postfach 12 34, 55001 Mainz\n"
            "Sonstige: Hafenstraße 9, 55120 Mainz",
        )
    ]
    formular = client.get(reverse("contacts:bearbeiten", args=[kunde.pk])).text
    assert f'name="anschrift_id" value="{rechnung.pk}"' in formular
    assert 'id="anschrift-vorlage"' in formular

    # Ändern behält die ID, damit Belege weiter auf die Anschrift zeigen.
    client.post(
        reverse("contacts:bearbeiten", args=[kunde.pk]),
        {
            **FIRMA,
            **anschriften(
                (
                    str(rechnung.pk),
                    "rechnung",
                    "Rechnungsstelle",
                    "Postfach 12 34",
                    "55001",
                    "Mainz",
                    "",
                ),
                (
                    "",
                    "lieferung",
                    "Lager Nord",
                    "Hafenstraße 9",
                    "55120",
                    "Mainz",
                    "Deutschland",
                ),
            ),
        },
    )

    rechnung.refresh_from_db()
    assert rechnung.zusatz == "Rechnungsstelle"
    assert not Anschrift.objects.filter(pk=sonstige.pk).exists()
    assert [a.art for a in kunde.anschriften.all()] == ["rechnung", "lieferung"]
    assert eintraege(kunde)[1] == (
        "Rechnung: Buchhaltung, Postfach 12 34, 55001 Mainz\n"
        "Sonstige: Hafenstraße 9, 55120 Mainz",
        "Rechnung: Rechnungsstelle, Postfach 12 34, 55001 Mainz\n"
        "Lieferung: Lager Nord, Hafenstraße 9, 55120 Mainz",
    )

    # Unverändert gespeichert: kein weiterer Eintrag.
    client.post(
        reverse("contacts:bearbeiten", args=[kunde.pk]),
        {
            **FIRMA,
            **anschriften(
                *(
                    (str(a.pk), a.art, a.zusatz, a.strasse, a.plz, a.ort, a.land)
                    for a in kunde.anschriften.all()
                )
            ),
        },
    )
    assert len(eintraege(kunde)) == 2


def test_unvollstaendige_anschrift_bleibt_zum_verbessern_stehen(client):
    antwort = client.post(
        reverse("contacts:neu"),
        {**FIRMA, **anschriften(("", "lieferung", "Lager Nord", "", "", "Mainz", ""))},
    )

    assert antwort.status_code == 200
    assert not Kontakt.objects.exists()
    seite = antwort.text
    assert "Bitte Straße, PLZ und Ort angeben." in seite
    assert 'value="Lager Nord"' in seite


def test_fremde_id_legt_neue_an(client, kunde):
    andere = Kontakt.objects.create(firmenname="Hof Ahorn")

    client.post(
        reverse("contacts:bearbeiten", args=[andere.pk]),
        {
            **FIRMA,
            "firmenname": "Hof Ahorn",
            **anschriften(
                (
                    str(lieferanschrift(kunde).pk),
                    "lieferung",
                    "",
                    "Weg 1",
                    "55116",
                    "Mainz",
                    "",
                )
            ),
        },
    )

    assert lieferanschrift(kunde).strasse == "Hafenstraße 9"
    assert andere.anschriften.get().strasse == "Weg 1"


def test_neue_rechnung_nimmt_rechnungs_und_lieferanschrift(client, firma, kunde):
    seite = client.get(reverse("invoicing:neu"), {"empfaenger": kunde.pk}).text

    rechnung, lager = rechnungsanschrift(kunde), lieferanschrift(kunde)
    assert (
        f'value="{rechnung.pk}" data-kontakt="{kunde.pk}" data-art="rechnung"' in seite
    )
    assert (
        'data-anschrift="Muster Bäckerei GmbH|Buchhaltung|Postfach 12 34|55001 Mainz"'
        in seite
    )
    assert gewaehlt(seite, "anschrift") == [str(rechnung.pk)]
    assert gewaehlt(seite, "lieferanschrift") == [str(lager.pk)]
    assert 'data-vorgabe="rechnung"' in seite and 'data-vorgabe="lieferung"' in seite
    # Angebote gehen an die Standardanschrift, die Lieferanschrift gilt auch dort.
    angebot = client.get(reverse("angebote:neu"), {"empfaenger": kunde.pk}).text
    assert (
        f'value="{lager.pk}" data-kontakt="{kunde.pk}" data-art="lieferung"' in angebot
    )
    assert gewaehlt(angebot, "anschrift") == []
    assert gewaehlt(angebot, "lieferanschrift") == [str(lager.pk)]


def test_festschreiben_mit_rechnungs_und_lieferanschrift(
    client, firma, kunde, settings
):
    client.post(reverse("invoicing:neu"), rechnung_formular(kunde))

    rechnung = Rechnung.objects.get()
    assert rechnung.status == Rechnung.Status.FESTGESCHRIEBEN
    e, lieferung = rechnung.beleg["empfaenger"], rechnung.beleg["lieferanschrift"]
    assert e["zeilen"] == [
        "Muster Bäckerei GmbH",
        "Buchhaltung",
        "Postfach 12 34",
        "55001 Mainz",
    ]
    assert (e["strasse"], e["plz"]) == ("Postfach 12 34", "55001")
    assert lieferung["zusatz"] == "Lager Nord"
    pfad = settings.DATA_DIR / rechnung.datei
    text = seitentext(pfad)
    assert "Buchhaltung Postfach 12 34 55001 Mainz" in text
    assert (
        "Lieferanschrift: Muster Bäckerei GmbH, Lager Nord, Hafenstraße 9, 55120 Mainz"
        in text
    )
    xml = PdfReader(pfad).attachments["factur-x.xml"][0].decode()
    kaeufer = xml.split("<ram:BuyerTradeParty>")[1].split("</ram:BuyerTradeParty>")[0]
    assert "<ram:PostcodeCode>55001</ram:PostcodeCode>" in kaeufer
    an = xml.split("<ram:ShipToTradeParty>")[1].split("</ram:ShipToTradeParty>")[0]
    assert "<ram:Name>Muster Bäckerei GmbH</ram:Name>" in an
    assert "<ram:LineOne>Hafenstraße 9</ram:LineOne>" in an
    assert "<ram:LineTwo>Lager Nord</ram:LineTwo>" in an
    assert "<ram:CountryID>DE</ram:CountryID>" in an

    # Die Korrektur übernimmt beide und sperrt sie wie den Empfänger.
    client.post(reverse("invoicing:korrigieren", args=[rechnung.pk]))
    korrektur = Rechnung.objects.get(korrektur_zu=rechnung)
    assert korrektur.anschrift == rechnungsanschrift(kunde)
    assert korrektur.lieferanschrift == lieferanschrift(kunde)
    editor = client.get(reverse("invoicing:bearbeiten", args=[korrektur.pk])).text
    assert '<select id="anschrift" name="anschrift" disabled>' in editor
    assert '<select id="lieferanschrift" name="lieferanschrift" disabled>' in editor
    korrektur.delete()

    # Die Stornorechnung geht an dieselbe Anschrift, auch eine Mahnung.
    client.post(reverse("invoicing:stornieren", args=[rechnung.pk]))
    storno = Rechnung.objects.get(storno_zu=rechnung)
    assert storno.beleg["empfaenger"]["zeilen"] == e["zeilen"]
    assert storno.beleg["lieferanschrift"] == lieferung
    aufstellung = {"zeilen": [], "gesamt": 0}
    heute = date.today()
    mahnung = mahnen.beleg_daten(
        rechnung, firma, 1, heute, heute, "Bitte zahlen.", aufstellung
    )
    assert mahnung["empfaenger"]["zeilen"] == e["zeilen"]


def test_ohne_weitere_anschrift_wie_bisher(client, firma, kunde, settings):
    client.post(
        reverse("invoicing:neu"),
        rechnung_formular(kunde, anschrift="", lieferanschrift=""),
    )

    rechnung = Rechnung.objects.get()
    assert rechnung.beleg["empfaenger"]["zeilen"][1:] == [
        "Frau Lea Sommer",
        "Lindenweg 4",
        "55116 Mainz",
    ]
    assert rechnung.beleg["lieferanschrift"] is None
    pfad = settings.DATA_DIR / rechnung.datei
    assert "Lieferanschrift" not in seitentext(pfad)
    assert (
        "ShipToTradeParty"
        not in PdfReader(pfad).attachments["factur-x.xml"][0].decode()
    )


def test_unbekanntes_land_der_lieferanschrift_ohne_xml(client, firma, kunde, settings):
    Anschrift.objects.filter(art="lieferung").update(land="Japan")

    client.post(reverse("invoicing:neu"), rechnung_formular(kunde))

    rechnung = Rechnung.objects.get()
    assert not rechnung.ist_entwurf
    assert not PdfReader(settings.DATA_DIR / rechnung.datei).attachments


def test_anschrift_einer_anderen_adresse_abgelehnt(client, firma, kunde):
    andere = Kontakt.objects.create(
        firmenname="Hof Ahorn", strasse="Weg 1", plz="55116", ort="Mainz"
    )

    antwort = client.post(
        reverse("invoicing:neu"),
        rechnung_formular(kunde, kontakt=andere.pk, lieferanschrift=""),
    )

    assert antwort.status_code == 200
    assert not Rechnung.objects.exists()
    assert "Diese Anschrift gehört zu einer anderen Adresse." in antwort.text


def test_anschrift_auf_beleg_bleibt_entwurf_faellt_zurueck(client, firma, kunde):
    client.post(reverse("invoicing:neu"), rechnung_formular(kunde))
    client.post(
        reverse("invoicing:neu"),
        rechnung_formular(kunde, aktion="speichern", anschrift=""),
    )
    entwurf = Rechnung.objects.get(status=Rechnung.Status.ENTWURF)
    rechnung, lager = rechnungsanschrift(kunde), lieferanschrift(kunde)

    # Beide entfernt: Die der festgeschriebenen Rechnung kommen mit Meldung zurück.
    antwort = client.post(
        reverse("contacts:bearbeiten", args=[kunde.pk]),
        {**FIRMA, "nachname": "Sommer"},
    )

    assert antwort.status_code == 200
    assert "Steht auf Rechnung 260001 und bleibt deshalb." in antwort.text
    assert kunde.anschriften.count() == 2

    # Nur der Entwurf nutzt die neue: Sie lässt sich entfernen, er nimmt keine mehr.
    neu = Anschrift.objects.create(
        kontakt=kunde, art="lieferung", strasse="Am Markt 2", plz="55116", ort="Mainz"
    )
    entwurf.lieferanschrift = neu
    entwurf.save()
    behalten = anschriften(
        *(
            (str(a.pk), a.art, a.zusatz, a.strasse, a.plz, a.ort, a.land)
            for a in (rechnung, lager)
        )
    )
    antwort = client.post(
        reverse("contacts:bearbeiten", args=[kunde.pk]),
        {**FIRMA, "nachname": "Sommer", **behalten},
    )

    assert antwort.status_code == 302
    entwurf.refresh_from_db()
    assert entwurf.lieferanschrift is None
    assert kunde.anschriften.count() == 2


def test_angebot_auftrag_und_rechnung_uebernehmen(firma, kunde):
    sonstige = Anschrift.objects.create(
        kontakt=kunde, art="sonstige", strasse="Filiale 1", plz="55116", ort="Mainz"
    )
    angebot = Angebot.objects.create(
        kontakt=kunde, anschrift=sonstige, lieferanschrift=lieferanschrift(kunde)
    )

    auftrag = auftragsbeleg.aus_angebot(angebot, firma)
    assert (auftrag.anschrift, auftrag.lieferanschrift) == (
        sonstige,
        lieferanschrift(kunde),
    )
    rechnung = auftragsbeleg.rechnung_erstellen(auftrag, firma)
    # Rechnungen gehen an die Rechnungsanschrift.
    assert rechnung.anschrift == rechnungsanschrift(kunde)
    assert rechnung.lieferanschrift == lieferanschrift(kunde)
    kopie = angebot.kopieren()
    assert kopie.lieferanschrift == lieferanschrift(kunde)

    # Ohne Rechnungsanschrift die des Auftrags.
    rechnungsanschrift(kunde).delete()
    rechnung = auftragsbeleg.rechnung_erstellen(auftrag, firma)
    assert rechnung.anschrift == sonstige


def test_anzeige_export_auskunft_und_gesamtexport(client, kunde):
    verlauf = client.get(reverse("historie:verlauf", args=[kunde.pk])).text
    assert "Lieferanschrift" in verlauf and "Lager Nord" in verlauf
    assert "Rechnungsanschrift" in client.get(reverse("contacts:liste")).text

    antwort = client.get(reverse("contacts:liste"), {"format": "csv"})
    zeile = next(
        csv.DictReader(StringIO(antwort.content.decode("utf-8-sig")), delimiter=";")
    )
    assert zeile[WEITERE] == (
        "Lieferung: Lager Nord, Hafenstraße 9, 55120 Mainz\n"
        "Rechnung: Buchhaltung, Postfach 12 34, 55001 Mainz"
    )
    assert datenschutz.stammdaten(kunde)[WEITERE] == zeile[WEITERE]

    _, _, abfrage, vorne, hinten = next(
        t for t in gesamtexport.TABELLEN if t[0] == "anschriften.csv"
    )
    titel, zeilen = gesamtexport.tabelle_daten(Anschrift, abfrage, vorne, hinten)
    assert titel == [
        "Kundennummer",
        "Adresse",
        "Art",
        "Zusatz",
        "Straße und Hausnummer",
        "PLZ",
        "Ort",
        "Land",
    ]
    assert zeilen[0][:4] == [
        "K-0001",
        "Muster Bäckerei GmbH",
        "Lieferung",
        "Lager Nord",
    ]

    kunde.delete()
    assert not Anschrift.objects.exists()
