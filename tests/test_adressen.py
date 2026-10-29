import pytest
from django.urls import reverse

from contacts.models import Kontakt

pytestmark = pytest.mark.django_db


def test_adresse_nur_mit_namen(client):
    response = client.post(
        reverse("contacts:neu"),
        {
            "art": "firma",
            "kategorie": "kunde",
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
        {"art": "firma", "kategorie": "kunde", "nachname": "Krume"},
    )

    assert "Bitte geben Sie den Firmennamen an." in response.text
    assert not Kontakt.objects.exists()


def test_person_braucht_nachnamen(client):
    response = client.post(
        reverse("contacts:neu"),
        {"art": "person", "kategorie": "kunde", "vorname": "Anna"},
    )

    assert "Bitte geben Sie den Nachnamen an." in response.text
    assert not Kontakt.objects.exists()


def test_dublettenwarnung_bei_gleicher_email(client):
    Kontakt.objects.create(
        art="person", vorname="Anna", nachname="Lindner", email="anna@post.example"
    )
    daten = {
        "art": "person",
        "kategorie": "kunde",
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
            "kategorie": "kunde",
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
