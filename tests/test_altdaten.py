"""Übernahme aus PDFs des Altprogramms – mit erfundenen Texten im selben Aufbau."""

from datetime import date
from decimal import Decimal

import pytest

from archive.importer import (
    NichtUebernommen,
    anschrift_zerlegen,
    auslesen,
    pruefen,
    uebernehmen,
)
from archive.models import Altbeleg
from contacts.models import Kontakt

KOPF = """Muster Bäckerei GmbH
Firma
Lindenweg 4
55116 Mainz
Muster IT - Gartenweg 1 - 55116 Mainz Muster IT
Gartenweg 1
"""

RECHNUNG = (
    KOPF
    + """Rechnung
Kunden-Nr.: 5009
Rechnung Nr.: 240012
12.03.2024
Gesamtsumme 1.175,50 €
"""
)

STORNO = (
    KOPF
    + """Stornorechnung
zu Rechnung Nr.: 240012 vom 12.03.2024
Kunden-Nr.: 5009
Storno Nr.: 3
20.03.2024
Gesamtsumme 1.175,50 €
"""
)

ENTWURF = (
    KOPF
    + "Rechnung\nRechnung Nr.: NEU\n12.08.2024\n-- ENTWURF --\nGesamtsumme 10,00 €\n"
)
MAHNUNG = KOPF + "1. Mahnung\nRechnung Nr.: 240012\n01.05.2024\nEndbetrag 10,00 €\n"


def test_rechnung_auslesen(tmp_path):
    beleg = auslesen(RECHNUNG, tmp_path / "r.pdf", "a" * 64)

    assert (beleg.art, beleg.nummer, beleg.datum) == (
        "rechnung",
        "240012",
        date(2024, 3, 12),
    )
    assert beleg.betrag == Decimal("1175.50")
    assert beleg.absender == "Muster IT"
    assert beleg.kundennummer == 5009
    assert beleg.anschrift["firmenname"] == "Muster Bäckerei GmbH"
    assert (beleg.anschrift["strasse"], beleg.anschrift["plz"]) == (
        "Lindenweg 4",
        "55116",
    )


def test_storno_negativ_mit_bezug(tmp_path):
    beleg = auslesen(STORNO, tmp_path / "s.pdf", "b" * 64)

    assert beleg.art == "storno"
    assert beleg.betrag == Decimal("-1175.50")
    assert beleg.bezug == "240012"


@pytest.mark.parametrize(
    ("text", "grund"), [(ENTWURF, "Entwurf"), (MAHNUNG, "Mahnung")]
)
def test_entwurf_und_mahnung_nicht_uebernommen(tmp_path, text, grund):
    with pytest.raises(NichtUebernommen, match=grund):
        auslesen(text, tmp_path / "x.pdf", "c" * 64)


def test_anschrift_mit_ansprechpartner():
    felder, sicher = anschrift_zerlegen(
        [
            "Onlinehandel Beispiel",
            "Herrn Dr. Max Muster",
            "Hauptstraße 6",
            "76185 Karlsruhe",
        ]
    )

    assert sicher
    assert felder["firmenname"] == "Onlinehandel Beispiel"
    assert (
        felder["anrede"],
        felder["titel"],
        felder["vorname"],
        felder["nachname"],
    ) == (
        "Herr",
        "Dr.",
        "Max",
        "Muster",
    )


@pytest.mark.parametrize(
    ("zeilen", "erwartet"),
    [
        (["Frau", "Anna Lindner"], ("Frau", "", "Anna", "Lindner")),
        (["Frau Prof. Dr.", "Anna Lindner"], ("Frau", "Prof. Dr.", "Anna", "Lindner")),
        (["Herrn", "Lindner"], ("Herr", "", "", "Lindner")),
    ],
)
def test_anschrift_anrede_in_eigener_zeile(zeilen, erwartet):
    felder, sicher = anschrift_zerlegen([*zeilen, "Weg 1", "55116 Mainz"])

    assert sicher
    assert felder["art"] == Kontakt.Art.PERSON
    assert (
        felder["anrede"],
        felder["titel"],
        felder["vorname"],
        felder["nachname"],
    ) == erwartet


def test_anschrift_nur_person():
    felder, _ = anschrift_zerlegen(["Frau Anna Lindner", "Weg 1", "55116 Mainz"])

    assert felder["art"] == Kontakt.Art.PERSON
    assert felder["nachname"] == "Lindner"


@pytest.mark.django_db
def test_uebernahme_legt_adresse_mit_alter_nummer_an(tmp_path, settings):
    settings.DATA_DIR = tmp_path / "daten"
    quelle = tmp_path / "alt"
    quelle.mkdir()
    texte = {"r.pdf": RECHNUNG, "s.pdf": STORNO, "e.pdf": ENTWURF, "m.pdf": MAHNUNG}
    for name in texte:
        (quelle / name).write_bytes(
            name.encode()
        )  # unterschiedlicher Inhalt → eigene Prüfsumme

    bericht = uebernehmen(pruefen(quelle, leser=lambda pfad: texte[pfad.name]))

    kontakt = Kontakt.objects.get()
    assert kontakt.kundennummer == "K-5009"
    assert Altbeleg.objects.count() == 2
    assert sum(b.betrag for b in Altbeleg.objects.all()) == 0
    assert bericht.uebersprungen == {"Entwurf": 1, "Mahnung": 1}
    assert (settings.DATA_DIR / Altbeleg.objects.first().datei).is_file()

    # Zweiter Lauf übernimmt nichts doppelt.
    zweiter = pruefen(quelle, leser=lambda pfad: texte[pfad.name])
    assert zweiter.belege == []
    assert zweiter.bereits_uebernommen == 2
