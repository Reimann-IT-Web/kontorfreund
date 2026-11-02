"""Weitere Telefonnummern und E-Mail-Adressen, Position (Spezifikation K-1) – mit erfundenen Daten."""

import csv
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from backups import gesamtexport
from contacts import datenschutz
from contacts.models import Kontakt, Kontaktweg
from importe import lesen, uebernahme, vorlagen
from importe.models import Import
from protokoll.models import Eintrag

pytestmark = pytest.mark.django_db

PERSON = {
    "art": "person",
    "kategorie": "kunde",
    "vorname": "Lea",
    "nachname": "Sommer",
    "land": "Deutschland",
}
WEITERE = "Weitere Telefonnummern und E-Mail-Adressen"


def wege(*zeilen):
    """Formularfelder für Zeilen (Art, Bezeichnung, Nummer oder Adresse)."""
    arten, bezeichnungen, werte = zip(*zeilen, strict=True)
    return {"weg_art": arten, "weg_bezeichnung": bezeichnungen, "weg_wert": werte}


def eintraege(kontakt):
    """Protokolleinträge zu den weiteren Nummern und Adressen."""
    return [
        e.aenderungen[0][1:]
        for e in Eintrag.objects.filter(
            aktion=Eintrag.Aktion.GEAENDERT, objekt_id=str(kontakt.pk)
        ).order_by("pk")
        if e.aenderungen[0][0] == WEITERE
    ]


@pytest.fixture
def korn():
    korn = Kontakt.objects.create(
        firmenname="Bäckerei Korn",
        vorname="Lea",
        nachname="Sommer",
        position="Inhaberin",
        ort="Dresden",
        email="info@korn.test",
    )
    Kontaktweg.objects.create(
        kontakt=korn, art="telefon", bezeichnung="Mobil", wert="0171 2345678"
    )
    Kontaktweg.objects.create(
        kontakt=korn, art="email", bezeichnung="Buchhaltung", wert="rechnung@korn.test"
    )
    return korn


def test_anlegen_aendern_und_protokoll(client):
    antwort = client.post(
        reverse("contacts:neu"),
        {
            **PERSON,
            "position": "Geschäftsführerin",
            **wege(
                ("telefon", "Mobil", " 0171 2345678 "),
                ("email", "Buchhaltung", "rechnung@korn.test"),
                ("telefon", "Fax", ""),
                ("fax", "Fax", "06131 99"),
            ),
        },
    )

    assert antwort.status_code == 302
    lea = Kontakt.objects.get()
    assert lea.position == "Geschäftsführerin"
    assert [str(w) for w in lea.kontaktwege.all()] == [
        "Mobil: 0171 2345678",
        "Buchhaltung: rechnung@korn.test",
    ], "leere Zeilen und unbekannte Arten fallen weg"
    assert eintraege(lea) == [
        ["", "Mobil: 0171 2345678\nBuchhaltung: rechnung@korn.test"]
    ]
    formular = client.get(reverse("contacts:bearbeiten", args=[lea.pk])).text
    assert 'value="0171 2345678"' in formular and 'value="Buchhaltung"' in formular

    url = reverse("contacts:bearbeiten", args=[lea.pk])
    client.post(url, {**PERSON, **wege(("telefon", "Mobil", "0171 2345678"))})
    client.post(url, {**PERSON, **wege(("telefon", "Mobil", "0171 2345678"))})

    assert [str(w) for w in lea.kontaktwege.all()] == ["Mobil: 0171 2345678"]
    assert eintraege(lea)[1:] == [
        ["Mobil: 0171 2345678\nBuchhaltung: rechnung@korn.test", "Mobil: 0171 2345678"]
    ], "unverändert gespeichert gibt keinen Eintrag"


def test_fehler_bleiben_zum_verbessern_stehen(client):
    antwort = client.post(
        reverse("contacts:neu"),
        {**PERSON, **wege(("email", "Privat", "lea@"), ("telefon", "", "0" * 51))},
    )

    assert antwort.status_code == 200 and not Kontakt.objects.exists()
    assert "„lea@“ ist keine gültige E-Mail-Adresse." in antwort.text
    assert "höchstens 50 Zeichen" in antwort.text
    assert 'value="lea@"' in antwort.text and 'value="Privat"' in antwort.text

    antwort = client.post(
        reverse("contacts:neu"),
        {**PERSON, **wege(*[("telefon", "", f"0171 {i}") for i in range(21)])},
    )
    assert "Höchstens 20 weitere" in antwort.text and not Kontakt.objects.exists()


def test_dublette_auch_ueber_weitere_email(client, korn):
    neu = {"art": "firma", "kategorie": "kunde", "firmenname": "Hof Ahorn"}

    antwort = client.post(
        reverse("contacts:neu"), {**neu, "email": "Rechnung@korn.test"}
    )
    assert antwort.context["dubletten"] == [korn]

    antwort = client.post(
        reverse("contacts:neu"), {**neu, **wege(("email", "", "info@korn.test"))}
    )
    assert antwort.context["dubletten"] == [korn]
    assert not Kontakt.objects.filter(firmenname="Hof Ahorn").exists()


def test_liste_suche_und_export(client, korn):
    Kontakt.objects.create(
        art="person", nachname="Lind", position="Einkauf", firma=korn
    )
    seite = client.get(reverse("contacts:liste")).text

    assert "Lea Sommer, Inhaberin" in seite and "Einkauf bei Bäckerei Korn" in seite
    assert (
        'href="tel:01712345678"' in seite
        and 'href="mailto:rechnung@korn.test"' in seite
    )
    assert '<td class="col-kontakt">0171 2345678</td>' in seite, "statt „–“"
    treffer = client.get(reverse("contacts:liste"), {"q": "rechnung@"})
    assert list(treffer.context["kontakte"]) == [korn]

    antwort = client.get(reverse("contacts:liste"), {"format": "csv"})
    zeilen = csv.DictReader(
        StringIO(antwort.content.decode("utf-8-sig")), delimiter=";"
    )
    zeile = next(z for z in zeilen if z["Name"] == "Bäckerei Korn")
    assert zeile["Position"] == "Inhaberin"
    assert zeile[WEITERE] == "Mobil: 0171 2345678\nBuchhaltung: rechnung@korn.test"


def test_verlauf_zeigt_position_und_weitere(client, korn):
    lind = Kontakt.objects.create(
        art="person", nachname="Lind", position="Einkauf", firma=korn
    )

    bei_firma = client.get(reverse("historie:verlauf", args=[korn.pk])).text
    assert 'href="tel:01712345678"' in bei_firma and "Buchhaltung" in bei_firma
    assert '<span class="small">Einkauf</span>' in bei_firma
    bei_person = client.get(reverse("historie:verlauf", args=[lind.pk])).text
    assert "Einkauf bei <a" in bei_person


def test_auskunft_gesamtexport_und_loeschen(korn):
    daten = datenschutz.stammdaten(korn)
    assert daten["Position"] == "Inhaberin"
    assert daten[WEITERE] == "Mobil: 0171 2345678\nBuchhaltung: rechnung@korn.test"

    _, _, abfrage, vorne, hinten = next(
        t for t in gesamtexport.TABELLEN if t[0] == "telefon-email.csv"
    )
    titel, zeilen = gesamtexport.tabelle_daten(Kontaktweg, abfrage, vorne, hinten)
    assert titel == [
        "Kundennummer",
        "Adresse",
        "Art",
        "Bezeichnung",
        "Nummer oder Adresse",
    ]
    assert zeilen[0] == ["K-0001", "Bäckerei Korn", "Telefon", "Mobil", "0171 2345678"]

    korn.delete()
    assert not Kontaktweg.objects.exists()


def test_import_mit_mobil_fax_und_position(inhaber, korn):
    inhalt = (
        "Firma;Nachname;Position;E-Mail;Mobil (Rufnummer);Telefax\n"
        ";Lind;Einkauf;;0171 7654321;06131 99\n"
        "Hof Ahorn;;;RECHNUNG@korn.test;;\n"
        "Hof Birke;;;;;\n"
        "Kiosk Eck;;;;;" + "9" * 51 + "\n"
    ).encode()
    spalten, zeilen = lesen.lesen(inhalt)
    # Eine Spalte wie im Export der Adressliste, zugeordnet von Hand.
    spalten.append("Weiteres")
    zeilen[2][1].append("Buchhaltung: info@birke.test\nrechnung@korn.test")
    for _, werte in zeilen[:2] + zeilen[3:]:
        werte.append("")
    _, zuordnung = vorlagen.vorschlagen("kontakte", spalten, [])
    zuordnung["weitere"] = "Weiteres"
    assert (zuordnung["position"], zuordnung["mobil"], zuordnung["fax"]) == (
        "Position",
        "Mobil (Rufnummer)",
        "Telefax",
    )
    imp = Import.objects.create(
        ziel="kontakte",
        dateiname="liste.csv",
        spalten=spalten,
        zeilen=zeilen,
        zuordnung=zuordnung,
        benutzer=inhaber,
        bestaetigt=True,
    )

    bericht = uebernahme.uebernehmen(imp)

    assert bericht.dubletten == [
        (3, "Hof Ahorn", "K-0001 Bäckerei Korn"),
        (4, "Hof Birke", "K-0001 Bäckerei Korn"),
    ], "auch über die weiteren E-Mail-Adressen der Zeile"
    assert (
        bericht.fehler[0][0] == 5 and "höchstens 50 Zeichen" in bericht.fehler[0][1][0]
    )
    lind = Kontakt.objects.get(nachname="Lind")
    assert lind.position == "Einkauf"
    assert [str(w) for w in lind.kontaktwege.all()] == [
        "Mobil: 0171 7654321",
        "Fax: 06131 99",
    ]
    assert eintraege(lind) == [["", "Mobil: 0171 7654321\nFax: 06131 99"]]


def test_rundreise_mit_der_adressliste(client, korn):
    datei = client.get(reverse("contacts:liste"), {"format": "xlsx"}).content
    Kontakt.objects.all().delete()

    client.post(
        reverse("importe:adressen"),
        {"datei": SimpleUploadedFile("Adressen.xlsx", datei)},
    )
    imp = Import.objects.get()
    assert imp.vorlage == "Kontorfreund"
    daten = {f"spalte_{feld}": spalte for feld, spalte in imp.zuordnung.items()}
    client.post(
        reverse("importe:zuordnen", args=[imp.pk]),
        {"kategorie": "kunde", "dubletten_anlegen": "", **daten},
    )
    client.post(reverse("importe:uebernehmen", args=[imp.pk]))

    neu = Kontakt.objects.get()
    assert neu.position == "Inhaberin"
    assert [(w.art, str(w)) for w in neu.kontaktwege.all()] == [
        ("telefon", "Mobil: 0171 2345678"),
        ("email", "Buchhaltung: rechnung@korn.test"),
    ]
