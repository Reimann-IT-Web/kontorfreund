"""Kategorien frei anlegen, mehrere je Adresse (Spezifikation K-1) – mit erfundenen Daten."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from backups import gesamtexport
from contacts import datenschutz
from contacts.models import Kategorie, Kontakt
from importe.models import Import
from konten.models import Benutzer
from protokoll.models import Eintrag

pytestmark = pytest.mark.django_db

FIRMA = {"art": "firma", "firmenname": "Bäckerei Korn", "land": "Deutschland"}
KUNDE = Kategorie.Kennung.KUNDE
LIEFERANT = Kategorie.Kennung.LIEFERANT


def eintraege(kontakt):
    """Protokolleinträge zu den Kategorien einer Adresse."""
    return [
        e.aenderungen[0][1:]
        for e in Eintrag.objects.filter(
            aktion=Eintrag.Aktion.GEAENDERT, objekt_id=str(kontakt.pk)
        ).order_by("pk")
        if e.aenderungen[0][0] == "Kategorien"
    ]


@pytest.mark.django_db(transaction=True)
def test_umstellung_behaelt_die_bisherige_kategorie():
    alt = [("contacts", "0006_kontaktwege_position"), ("importe", "0001_initial")]
    executor = MigrationExecutor(connection)
    executor.migrate(alt)
    apps = executor.loader.project_state(alt).apps
    for nummer, kategorie in enumerate(["kunde", "lieferant", "interessent"], 1):
        apps.get_model("contacts", "Kontakt").objects.create(
            nummer=nummer,
            firmenname=f"Firma {nummer}",
            anzeigename=f"Firma {nummer}",
            kategorie=kategorie,
        )
    benutzer = Benutzer.objects.create_user("inhaber@muster.test", name="Max")
    apps.get_model("importe", "Import").objects.create(
        ziel="kontakte",
        dateiname="liste.csv",
        spalten=[],
        zeilen=[],
        kategorie="lieferant",
        benutzer_id=benutzer.pk,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())

    assert [(k.firmenname, k.kategorien_text) for k in Kontakt.objects.all()] == [
        ("Firma 1", "Kunde"),
        ("Firma 2", "Lieferant"),
        ("Firma 3", "Interessent"),
    ]
    assert [(k.name, k.kennung) for k in Kategorie.objects.all()] == [
        ("Interessent", "interessent"),
        ("Kunde", "kunde"),
        ("Lieferant", "lieferant"),
    ]
    assert Import.objects.get().kategorie == Kategorie.vorgabe(LIEFERANT)


def test_adresse_mit_mehreren_und_neuer_kategorie(client):
    kunde, lieferant = Kategorie.vorgabe(KUNDE), Kategorie.vorgabe(LIEFERANT)
    neu = client.get(reverse("contacts:neu")).context["form"]
    assert list(neu.initial["kategorien"]) == [kunde], "neue Adressen sind Kunden"

    client.post(
        reverse("contacts:neu"),
        {
            **FIRMA,
            "kategorien": [kunde.pk, lieferant.pk],
            "neue_kategorie": "  Wartungsvertrag ",
        },
    )
    korn = Kontakt.objects.get()
    assert korn.kategorien_text == "Kunde, Lieferant, Wartungsvertrag"
    assert eintraege(korn) == [["", "Kunde, Lieferant, Wartungsvertrag"]]

    # Dieselbe Kategorie, auch in anderer Schreibweise, gibt es nur einmal.
    client.post(
        reverse("contacts:bearbeiten", args=[korn.pk]),
        {**FIRMA, "kategorien": [lieferant.pk], "neue_kategorie": "wartungsvertrag"},
    )
    assert korn.kategorien_text == "Lieferant, Wartungsvertrag"
    assert Kategorie.objects.filter(name__iexact="wartungsvertrag").count() == 1
    assert eintraege(korn)[-1] == [
        "Kunde, Lieferant, Wartungsvertrag",
        "Lieferant, Wartungsvertrag",
    ]

    antwort = client.post(
        reverse("contacts:bearbeiten", args=[korn.pk]),
        {**FIRMA, "neue_kategorie": "Webdesign, Hosting"},
    )
    assert "ohne Komma" in antwort.context["form"].errors["neue_kategorie"][0]
    assert korn.kategorien_text == "Lieferant, Wartungsvertrag", "nichts gespeichert"


def test_kategorien_anlegen_umbenennen_und_loeschen(client):
    seite = reverse("contacts:kategorien")
    client.post(seite, {"name": " Webdesign "})
    web = Kategorie.objects.get(name="Webdesign")
    antwort = client.post(seite, {"name": "WEBDESIGN"})
    assert "Die Kategorie „Webdesign“ gibt es schon." in antwort.text
    assert Kategorie.objects.count() == 4

    korn = Kontakt.objects.create(firmenname="Bäckerei Korn")
    korn.kategorien.add(web)
    Kontakt.objects.create(firmenname="Alt GmbH", archiviert=True).kategorien.add(web)
    assert f'href="/adressen/?kategorie={web.pk}">1 Adresse</a>' in (
        client.get(seite).text
    ), "nur aktive Adressen"

    # Auch die vorgegebenen lassen sich umbenennen; das Programm findet sie weiter.
    lieferant = Kategorie.vorgabe(LIEFERANT)
    client.post(
        reverse("contacts:kategorie", args=[lieferant.pk]), {"name": "Zulieferer"}
    )
    assert Kategorie.vorgabe(LIEFERANT).name == "Zulieferer"
    antwort = client.post(
        reverse("contacts:kategorie", args=[web.pk]), {"name": "zulieferer"}
    )
    assert antwort.context["bearbeitet"] == web
    assert f'id="kategorie-{web.pk}-fehler"' in antwort.text

    loeschen = reverse("contacts:kategorie_loeschen", args=[lieferant.pk])
    assert client.post(loeschen).status_code == 404
    client.post(reverse("contacts:kategorie_loeschen", args=[web.pk]))
    assert not Kategorie.objects.filter(pk=web.pk).exists()
    assert Kontakt.objects.get(pk=korn.pk).kategorien_text == ""
    assert Eintrag.objects.filter(
        aktion=Eintrag.Aktion.GELOESCHT, art="Kategorie", beschreibung="Webdesign"
    ).exists()


def test_hoechstens_100_kategorien(client):
    Kategorie.objects.bulk_create(
        Kategorie(name=f"Gruppe {n}") for n in range(100 - Kategorie.objects.count())
    )
    antwort = client.post(reverse("contacts:kategorien"), {"name": "Eine zu viel"})
    assert "Höchstens 100 Kategorien." in antwort.text
    antwort = client.post(
        reverse("contacts:neu"), {**FIRMA, "neue_kategorie": "Eine zu viel"}
    )
    assert antwort.context["form"].errors["neue_kategorie"] == [
        "Höchstens 100 Kategorien."
    ]
    assert not Kontakt.objects.exists()


def test_liste_nach_kategorie_filtern(client):
    web = Kategorie.objects.create(name="Webdesign")
    korn = Kontakt.objects.create(firmenname="Bäckerei Korn")
    korn.kategorien.add(web, Kategorie.vorgabe(KUNDE))
    Kontakt.objects.create(firmenname="Hof Ahorn")

    alle = client.get(reverse("contacts:liste"))
    assert len(alle.context["kontakte"]) == 2
    assert (
        '<span class="tags"><span class="tag">Kunde</span>'
        '<span class="tag">Webdesign</span></span>'
    ) in alle.text
    gefiltert = client.get(reverse("contacts:liste"), {"kategorie": web.pk})
    assert list(gefiltert.context["kontakte"]) == [korn]
    assert f'<option value="{web.pk}" selected>Webdesign</option>' in gefiltert.text
    export = client.get(
        reverse("contacts:liste"), {"kategorie": web.pk, "format": "csv"}
    )
    assert "Adressen Webdesign" in export["Content-Disposition"]
    archiv = client.get(reverse("contacts:liste"), {"kategorie": web.pk, "archiv": "1"})
    assert "Keine archivierte Adresse hat die Kategorie „Webdesign“." in archiv.text
    for unbekannt in ("999", "abc"):
        antwort = client.get(reverse("contacts:liste"), {"kategorie": unbekannt})
        assert len(antwort.context["kontakte"]) == 2


def test_import_mit_mehreren_kategorien(client):
    web = Kategorie.objects.create(name="Webdesign")
    korn = Kontakt.objects.create(firmenname="Bäckerei Korn", ort="Dresden")
    korn.kategorien.add(web, Kategorie.vorgabe(KUNDE))
    Kontakt.objects.create(firmenname="Hof Ahorn", ort="Bonn")
    datei = client.get(reverse("contacts:liste"), {"format": "xlsx"}).content
    Kontakt.objects.all().delete()
    web.delete()

    client.post(
        reverse("importe:adressen"),
        {"datei": SimpleUploadedFile("Adressen.xlsx", datei)},
    )
    imp = Import.objects.get()
    assert (imp.zuordnung["kategorie"], imp.kategorie) == (
        "Kategorien",
        Kategorie.vorgabe(KUNDE),
    )
    zuordnen = client.get(reverse("importe:zuordnen", args=[imp.pk])).text
    assert 'name="kategorie" value=""' in zuordnen and "keine" in zuordnen
    daten = {f"spalte_{feld}": spalte for feld, spalte in imp.zuordnung.items()}
    client.post(
        reverse("importe:zuordnen", args=[imp.pk]),
        {"kategorie": "", "dubletten_anlegen": "", **daten},
    )
    bericht = client.get(reverse("importe:bericht", args=[imp.pk])).text
    assert "Die Kategorie „Webdesign“ legt Kontorfreund neu an." in bericht
    assert "<td>Kunde, Webdesign</td>" in bericht
    client.post(reverse("importe:uebernehmen", args=[imp.pk]))

    korn, ahorn = Kontakt.objects.order_by("nummer")
    assert (korn.kategorien_text, ahorn.kategorien_text) == ("Kunde, Webdesign", "")
    assert eintraege(korn) == [["", "Kunde, Webdesign"]]


def test_auskunft_und_gesamtexport(inhaber):
    korn = Kontakt.objects.create(firmenname="Bäckerei Korn")
    korn.kategorien.add(Kategorie.vorgabe(KUNDE), Kategorie.objects.create(name="Web"))
    assert datenschutz.stammdaten(korn)["Kategorien"] == "Kunde, Web"

    _, _, abfrage, vorne, hinten = next(
        t for t in gesamtexport.TABELLEN if t[0] == "adressen.csv"
    )
    titel, zeilen = gesamtexport.tabelle_daten(Kontakt, abfrage, vorne, hinten)
    assert zeilen[0][titel.index("Kategorien")] == "Kunde, Web"
    _, _, abfrage, vorne, hinten = next(
        t for t in gesamtexport.TABELLEN if t[0] == "kategorien.csv"
    )
    titel, zeilen = gesamtexport.tabelle_daten(Kategorie, abfrage, vorne, hinten)
    assert titel == ["ID", "Name"]
    assert [z[1] for z in zeilen] == ["Kunde", "Interessent", "Lieferant", "Web"]
