import zipfile
from io import BytesIO

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from contacts.models import Kategorie, Kontakt

pytestmark = pytest.mark.django_db


def test_adresse_nur_mit_namen(client):
    response = client.post(
        reverse("contacts:neu"),
        {
            "art": "firma",
            "firmenname": "Bäckerei Krume",
            "land": "Deutschland",
        },
    )

    kontakt = Kontakt.objects.get()
    assert response.status_code == 302
    assert kontakt.kundennummer == "K-0001"
    assert kontakt.anzeigename == "Bäckerei Krume"


def test_nummern_fortlaufend():
    erste = Kontakt.objects.create(art="firma", firmenname="A")
    zweite = Kontakt.objects.create(art="person", nachname="B")

    assert (erste.kundennummer, zweite.kundennummer) == ("K-0001", "K-0002")


def test_firma_braucht_firmennamen(client):
    response = client.post(
        reverse("contacts:neu"),
        {"art": "firma", "nachname": "Krume"},
    )

    assert "Bitte geben Sie den Firmennamen an." in response.text
    assert not Kontakt.objects.exists()


def test_person_braucht_nachnamen(client):
    response = client.post(
        reverse("contacts:neu"),
        {"art": "person", "vorname": "Anna"},
    )

    assert "Bitte geben Sie den Nachnamen an." in response.text
    assert not Kontakt.objects.exists()


def test_dublettenwarnung_bei_gleicher_email(client):
    Kontakt.objects.create(
        art="person", vorname="Anna", nachname="Lindner", email="anna@post.example"
    )
    daten = {
        "art": "person",
        "nachname": "Lindner-Berg",
        "email": "ANNA@post.example",
    }

    response = client.post(reverse("contacts:neu"), daten)
    assert "gibt es vielleicht schon" in response.text
    assert Kontakt.objects.count() == 1

    client.post(reverse("contacts:neu"), {**daten, "trotzdem": "1"})
    assert Kontakt.objects.count() == 2


def test_ust_id_format(client):
    response = client.post(
        reverse("contacts:neu"),
        {
            "art": "firma",
            "firmenname": "X GmbH",
            "ust_id": "DE12345",
        },
    )

    assert "9 Ziffern" in response.text
    assert not Kontakt.objects.exists()


def test_suche_nach_name_und_nummer(client):
    Kontakt.objects.create(art="firma", firmenname="Fahrschule Kaya", ort="Bingen")
    Kontakt.objects.create(art="firma", firmenname="Weingut Hofmann", ort="Nierstein")

    nach_name = client.get("/adressen/", {"q": "kaya"}).context["kontakte"]
    nach_nummer = client.get("/adressen/", {"q": "K-0002"}).context["kontakte"]

    assert [k.anzeigename for k in nach_name] == ["Fahrschule Kaya"]
    assert [k.anzeigename for k in nach_nummer] == ["Weingut Hofmann"]


def test_archivieren_und_wiederherstellen(client):
    kontakt = Kontakt.objects.create(art="firma", firmenname="Alt GmbH")

    client.post(reverse("contacts:archivieren", args=[kontakt.pk]))
    assert list(client.get("/adressen/").context["kontakte"]) == []
    assert list(client.get("/adressen/", {"archiv": "1"}).context["kontakte"]) == [
        kontakt
    ]

    client.post(reverse("contacts:archivieren", args=[kontakt.pk]))
    assert list(client.get("/adressen/").context["kontakte"]) == [kontakt]


def test_export_der_liste(client):
    """Spezifikation M-5: die angezeigte Liste als XLSX, ODS und CSV."""
    lieferant = Kategorie.vorgabe(Kategorie.Kennung.LIEFERANT)
    Kontakt.objects.create(
        firmenname="Bäckerei Krume",
        vorname="Lea",
        nachname="Sommer",
        plz="01067",
        ort="Dresden",
        telefon="+49 351 123456",
        xrechnung=False,
    ).kategorien.add(Kategorie.vorgabe(Kategorie.Kennung.KUNDE), lieferant)
    Kontakt.objects.create(
        art="person", vorname="Erika", nachname="Beispiel"
    ).kategorien.add(lieferant)
    Kontakt.objects.create(firmenname="Alt GmbH", archiviert=True)

    seite = client.get(reverse("contacts:liste")).text
    assert 'href="?format=xlsx">Excel</a>, ' in seite
    assert (
        '<a href="?format=ods">LibreOffice</a> oder <a href="?format=csv">CSV</a>'
        in seite
    )

    antwort = client.get(reverse("contacts:liste"), {"format": "xlsx"})
    assert "Adressen" in antwort["Content-Disposition"]
    blatt = load_workbook(BytesIO(antwort.content)).active
    zeilen = list(blatt.values)
    assert zeilen[0][:4] == ("Kundennummer", "Art", "Kategorien", "Name")
    assert [z[3] for z in zeilen[1:]] == ["Bäckerei Krume", "Erika Beispiel"]
    krume = dict(zip(zeilen[0], zeilen[1], strict=True))
    assert krume["Kundennummer"] == "K-0001"
    assert krume["Kategorien"] == "Kunde, Lieferant"
    assert (krume["Vorname"], krume["Nachname"]) == ("Lea", "Sommer")
    # Als Text, sonst fiele die führende Null weg
    assert krume["PLZ"] == "01067"
    assert krume["Telefon"] == "+49 351 123456"
    assert krume["XRechnung"] is None

    lieferanten = client.get(
        reverse("contacts:liste"), {"kategorie": lieferant.pk, "format": "csv"}
    )
    assert "Adressen Lieferant" in lieferanten["Content-Disposition"]
    zeilen = lieferanten.content.decode("utf-8-sig").splitlines()
    assert len(zeilen) == 3
    assert zeilen[2].startswith("K-0002;Person;Lieferant;Erika Beispiel;")

    archiv = client.get(reverse("contacts:liste"), {"archiv": "1", "format": "ods"})
    assert "Archiv Adressen" in archiv["Content-Disposition"]
    with zipfile.ZipFile(BytesIO(archiv.content)) as ods:
        assert "Alt GmbH" in ods.read("content.xml").decode()
