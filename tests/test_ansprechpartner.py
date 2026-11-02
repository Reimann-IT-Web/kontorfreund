"""Ansprechpartner einer Firma (Spezifikation K-1 und K-2) – mit erfundenen Daten."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from backups import gesamtexport
from contacts import datenschutz
from contacts.models import Kontakt
from historie.models import Vorgang

pytestmark = pytest.mark.django_db


@pytest.fixture
def firma():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn",
        strasse="Markt 3",
        plz="55116",
        ort="Mainz",
        kategorie="lieferant",
    )


@pytest.fixture
def person(firma):
    return Kontakt.objects.create(
        art="person",
        vorname="Lea",
        nachname="Sommer",
        telefon="06131 12345",
        firma=firma,
    )


def eintrag(kontakt, betreff, inhaber, stunde):
    return Vorgang.objects.create(
        kontakt=kontakt,
        art=Vorgang.Art.ANRUF,
        betreff=betreff,
        benutzer=inhaber,
        zeitpunkt=timezone.make_aware(timezone.datetime(2026, 11, 2, stunde)),
    )


def test_ansprechpartner_bei_der_firma_anlegen(client, firma):
    url = f"{reverse('contacts:neu')}?firma={firma.pk}"
    antwort = client.get(url)
    assert antwort.context["form"].initial == {
        "art": "person",
        "firma": firma.pk,
        "kategorie": "lieferant",
    }
    assert f'<option value="{firma.pk}" selected>Bäckerei Korn</option>' in antwort.text

    antwort = client.post(
        url,
        {
            "art": "person",
            "kategorie": "lieferant",
            "vorname": "Lea",
            "nachname": "Sommer",
            "firma": firma.pk,
            "land": "Deutschland",
        },
    )

    assert antwort.url == reverse("historie:verlauf", args=[firma.pk])
    lea = Kontakt.objects.get(nachname="Sommer")
    assert (lea.art, lea.firma, lea.kategorie) == ("person", firma, "lieferant")
    bei_firma = client.get(antwort.url).text
    assert (
        reverse("historie:verlauf", args=[lea.pk]) in bei_firma
        and "Lea Sommer" in bei_firma
    )
    bei_person = client.get(reverse("historie:verlauf", args=[lea.pk])).text
    assert "Ansprechpartner bei" in bei_person
    assert reverse("historie:verlauf", args=[firma.pk]) in bei_person
    liste = client.get(reverse("contacts:liste")).text
    assert "Ansprechpartner bei Bäckerei Korn" in liste
    assert liste.count("Anschrift unvollständig") == 0, (
        "Ansprechpartner brauchen keine eigene"
    )


def test_eintraege_der_ansprechpartner_im_verlauf_der_firma(
    client, inhaber, firma, person
):
    eintrag(firma, "Bestellung besprochen", inhaber, 9)
    eintrag(person, "Rückruf wegen Lieferung", inhaber, 10)
    url = reverse("historie:verlauf", args=[firma.pk])

    seite = client.get(url).text
    assert "Bestellung besprochen" in seite and "Rückruf wegen Lieferung" in seite
    assert seite.index("Rückruf wegen Lieferung") < seite.index("Bestellung besprochen")
    assert f"?kontakt={person.pk}&amp;in=7" in seite, "Nachfassen beim Ansprechpartner"
    assert "ohne Ansprechpartner" in seite

    ohne = client.get(url, {"personen": "0"}).text
    assert "Bestellung besprochen" in ohne and "Rückruf wegen Lieferung" not in ohne

    bei_person = client.get(reverse("historie:verlauf", args=[person.pk])).text
    assert (
        "Rückruf wegen Lieferung" in bei_person
        and "Bestellung besprochen" not in bei_person
    )


def test_gesperrte_erscheinen_nicht(client, inhaber, firma, person):
    eintrag(person, "Rückruf wegen Lieferung", inhaber, 10)
    datenschutz.sperren(person, inhaber)
    seite = client.get(reverse("historie:verlauf", args=[firma.pk])).text
    assert "Lea Sommer" not in seite and "Rückruf wegen Lieferung" not in seite

    tom = Kontakt.objects.create(art="person", nachname="Ahorn", firma=firma)
    datenschutz.sperren(firma, inhaber)
    assert (
        "Ansprechpartner bei"
        not in client.get(reverse("historie:verlauf", args=[tom.pk])).text
    )
    formular = client.get(reverse("contacts:bearbeiten", args=[tom.pk])).text
    assert "Bäckerei Korn" not in formular


def test_nur_personen_gehoeren_zu_einer_firma(firma, person):
    andere = Kontakt.objects.create(firmenname="Hof Ahorn", firma=firma)
    assert andere.firma is None, "eine Firma ist nie Ansprechpartner"

    firma.art = "person"
    firma.nachname = "Korn"
    with pytest.raises(ValidationError, match="hat Ansprechpartner"):
        firma.full_clean()


def test_firma_geloescht_person_bleibt(firma, person):
    firma.delete()
    person.refresh_from_db()
    assert person.firma is None


def test_auskunft_und_gesamtexport(firma, person):
    assert (
        datenschutz.stammdaten(person)["Ansprechpartner bei"] == "K-0001 Bäckerei Korn"
    )
    assert datenschutz.stammdaten(firma)["Ansprechpartner bei"] == ""

    name, _, abfrage, vorne, hinten = next(
        t for t in gesamtexport.TABELLEN if t[0] == "adressen.csv"
    )
    titel, zeilen = gesamtexport.tabelle_daten(Kontakt, abfrage, vorne, hinten)
    lea = dict(zip(titel, zeilen[1], strict=True))
    assert (lea["Ansprechpartner bei"], lea["Kundennummer der Firma"]) == (
        "Bäckerei Korn",
        "K-0001",
    )
