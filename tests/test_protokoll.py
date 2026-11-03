"""Änderungsprotokoll (Spezifikation K-6) – mit erfundenen Daten."""

import pytest
from django.urls import reverse

from artikel.models import Artikel
from contacts.models import Kontakt
from core.models import Firmendaten
from core.templatetags.kf import euro
from konten.models import Benutzer
from protokoll.models import Eintrag, Unveraenderbar

pytestmark = pytest.mark.django_db

KENNWORT = "Tannenbaum Fahrrad Wolke"


def adresse(client, **mehr):
    return {
        "art": "firma",
        "firmenname": "Bäckerei Krume",
        "strasse": "Lindenweg 4",
        "plz": "55116",
        "ort": "Mainz",
        "land": "Deutschland",
        **mehr,
    }


def test_geaenderte_anschrift_mit_altem_und_neuem_wert(client, inhaber):
    client.post(reverse("contacts:neu"), adresse(client))
    kontakt = Kontakt.objects.get()
    client.post(
        reverse("contacts:bearbeiten", args=[kontakt.pk]),
        adresse(client, plz="65183", ort="Wiesbaden"),
    )

    angelegt, geaendert = Eintrag.objects.filter(art="Adresse").order_by("pk")
    assert angelegt.aktion == Eintrag.Aktion.ANGELEGT
    assert ["Ort", "", "Mainz"] in angelegt.aenderungen
    assert geaendert.aktion == Eintrag.Aktion.GEAENDERT
    assert geaendert.wer == "Max Muster" and geaendert.benutzer_id == inhaber.pk
    assert geaendert.beschreibung == "Bäckerei Krume"
    assert geaendert.aenderungen == [
        ["PLZ", "55116", "65183"],
        ["Ort", "Mainz", "Wiesbaden"],
    ]

    seite = client.get(reverse("protokoll:liste")).content.decode()
    assert "<del>Mainz</del>" in seite and "<ins>Wiesbaden</ins>" in seite


def test_loeschen_und_positionen(client):
    kunde = Kontakt.objects.create(
        firmenname="Muster GmbH", strasse="A 1", plz="1", ort="B"
    )
    formular = {
        "kontakt": kunde.pk,
        "datum": "2026-10-29",
        "leistung_von": "2026-10-01",
        "zahlungsziel": "14",
        "steuerfall": "kleinunternehmer",
        "bezeichnung": ["Webdesign"],
        "beschreibung": [""],
        "menge": ["2"],
        "einheit": ["Std."],
        "preis": ["80,00"],
        "aktion": "speichern",
    }
    client.post(reverse("invoicing:neu"), formular)
    rechnung = kunde.rechnungen.get()
    client.post(
        reverse("invoicing:bearbeiten", args=[rechnung.pk]),
        {**formular, "menge": ["3"]},
    )
    client.post(reverse("invoicing:loeschen", args=[rechnung.pk]))

    eintraege = list(Eintrag.objects.filter(art="Rechnung").order_by("pk"))
    positionen = [
        e.aenderungen[0]
        for e in eintraege
        if e.aenderungen[:1] and e.aenderungen[0][0] == "Positionen"
    ]
    assert positionen == [
        ["Positionen", "", f"1. 2 Std. Webdesign à {euro(80)}"],
        [
            "Positionen",
            f"1. 2 Std. Webdesign à {euro(80)}",
            f"1. 3 Std. Webdesign à {euro(80)}",
        ],
    ]
    assert eintraege[-1].aktion == Eintrag.Aktion.GELOESCHT


def test_kennwoerter_nie_im_klartext(client):
    firma = Firmendaten.laden()
    firma.mail_passwort = "streng geheim"
    firma.save()
    Benutzer.objects.create_user("anna@muster.test", KENNWORT, name="Anna Beispiel")

    text = str(list(Eintrag.objects.values_list("aenderungen", flat=True)))
    assert "streng geheim" not in text and "argon2" not in text
    assert ["Passwort", "", "•••"] in Eintrag.objects.filter(art="Firmendaten").latest(
        "pk"
    ).aenderungen


def test_anmeldungen_und_fehlversuche(anonym):
    anna = Benutzer.objects.create_user(
        "anna@muster.test", KENNWORT, name="Anna Beispiel"
    )
    anmelden = reverse("konten:anmelden")
    anonym.post(
        anmelden, {"email": "anna@muster.test", "kennwort": "falsch falsch falsch"}
    )
    anonym.post(anmelden, {"email": "niemand@muster.test", "kennwort": KENNWORT})
    anonym.post(anmelden, {"email": "anna@muster.test", "kennwort": KENNWORT})

    eintraege = [
        (e.aktion, e.wer, e.beschreibung, e.benutzer_id)
        for e in Eintrag.objects.filter(art="").order_by("pk")
    ]
    assert eintraege == [
        ("fehlversuch", "anna@muster.test", "Kennwort falsch", anna.pk),
        ("fehlversuch", "niemand@muster.test", "Unbekannte E-Mail-Adresse", None),
        ("anmeldung", "Anna Beispiel", "anna@muster.test", anna.pk),
    ]
    # Fehlversuche zählen und Anmeldezeit sind keine Änderungen an Annas Konto.
    assert not Eintrag.objects.filter(aktion=Eintrag.Aktion.GEAENDERT).exists()


def test_protokoll_ist_unveraenderbar(client):
    Artikel.objects.create(bezeichnung="Stundensatz", einheit="Std.", preis=80)
    eintrag = Eintrag.objects.get(art="Artikel")

    eintrag.beschreibung = "anders"
    with pytest.raises(Unveraenderbar):
        eintrag.save()
    with pytest.raises(Unveraenderbar):
        eintrag.delete()
    # Auch nicht über Abfragen für viele Einträge auf einmal.
    with pytest.raises(Unveraenderbar):
        Eintrag.objects.update(beschreibung="anders")
    with pytest.raises(Unveraenderbar):
        Eintrag.objects.all().delete()
    assert Eintrag.objects.get(pk=eintrag.pk).beschreibung == "Stundensatz"


def test_nur_inhaber_sehen_das_protokoll(client):
    anna = Benutzer.objects.create_user(
        "anna@muster.test", KENNWORT, name="Anna Beispiel"
    )
    assert "Protokoll" in client.get(reverse("core:start")).content.decode()
    assert client.get(reverse("protokoll:liste")).status_code == 200

    client.force_login(anna)
    assert client.get(reverse("protokoll:liste")).status_code == 403
    assert (
        reverse("protokoll:liste")
        not in client.get(reverse("core:start")).content.decode()
    )
