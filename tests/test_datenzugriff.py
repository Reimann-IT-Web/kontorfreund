"""Rolle Prüfer: unmittelbarer Datenzugriff für die Betriebsprüfung (Spezifikation D-6)."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from konten.models import Benutzer
from protokoll.models import Eintrag
from wiedervorlagen.forms import WiedervorlageForm

pytestmark = pytest.mark.django_db

HEUTE = date.today()
JAHR = HEUTE.year
KENNWORT = "Laterne Wolke Fahrrad 7"


@pytest.fixture
def rechnungen(client):
    firma = Firmendaten.laden()
    firma.name = "Muster IT & Web"
    firma.strasse = "Gartenweg 1"
    firma.plz = "55116"
    firma.ort = "Mainz"
    firma.steuernummer = "12/345/67890"
    firma.save()
    kunde = Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )
    erstellt = []
    for datum in (f"{JAHR - 1}-06-30", f"{JAHR}-01-02"):
        client.post(
            reverse("invoicing:neu"),
            {
                "kontakt": kunde.pk,
                "datum": datum,
                "leistung_von": datum,
                "zahlungsziel": "14",
                "steuerfall": "kleinunternehmer",
                "bezeichnung": ["Webdesign"],
                "beschreibung": [""],
                "menge": ["1"],
                "einheit": ["Std."],
                "preis": ["80,00"],
                "aktion": "festschreiben",
            },
        )
        erstellt.append(Rechnung.objects.latest("pk"))
    return erstellt


def pruefer(zugang_bis=HEUTE + timedelta(days=10)):
    return Benutzer.objects.create_user(
        "pruefung@finanzamt.test",
        KENNWORT,
        name="Frau Beispiel",
        rolle=Benutzer.Rolle.PRUEFER,
        pruefung_von=JAHR - 1,
        pruefung_bis=JAHR - 1,
        zugang_bis=zugang_bis,
    )


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def test_pruefer_anlegen(client):
    felder = {
        "aktion": "pruefer",
        "p-name": "Frau Beispiel",
        "p-email": "Pruefung@Finanzamt.test",
        "p-pruefung_von": str(JAHR),
        "p-pruefung_bis": str(JAHR),
        "p-zugang_bis": (HEUTE + timedelta(days=400)).isoformat(),
        "p-kennwort": KENNWORT,
        "p-wiederholung": KENNWORT,
    }
    seite = client.post(reverse("konten:benutzer"), felder)
    assert seite.status_code == 200
    assert "Bitte ein Datum zwischen heute" in seite.content.decode()
    assert not Benutzer.objects.filter(rolle=Benutzer.Rolle.PRUEFER).exists()

    felder["p-zugang_bis"] = (HEUTE + timedelta(days=30)).isoformat()
    antwort = client.post(reverse("konten:benutzer"), felder)
    assert antwort.status_code == 302
    konto = Benutzer.objects.get(rolle=Benutzer.Rolle.PRUEFER)
    assert konto.email == "pruefung@finanzamt.test"
    assert (konto.pruefung_von, konto.pruefung_bis) == (JAHR, JAHR)
    assert konto.zugang_bis == HEUTE + timedelta(days=30)
    assert konto.check_password(KENNWORT)

    # Verlängern; die Rolle lässt sich nicht wechseln.
    adresse = reverse("konten:benutzer_bearbeiten", args=[konto.pk])
    client.post(
        adresse,
        {
            "aktion": "pruefung",
            "pruefung_von": str(JAHR),
            "pruefung_bis": str(JAHR),
            "zugang_bis": (HEUTE + timedelta(days=60)).isoformat(),
        },
    )
    client.post(adresse, {"aktion": "rolle", "rolle": "inhaber"})
    konto.refresh_from_db()
    assert konto.zugang_bis == HEUTE + timedelta(days=60)
    assert konto.ist_pruefer


def test_keine_rolle_wird_zum_pruefer(client):
    mia = Benutzer.objects.create_user(
        "mia@muster.test", name="Mia", rolle=Benutzer.Rolle.MITARBEITER
    )
    client.post(
        reverse("konten:benutzer_bearbeiten", args=[mia.pk]),
        {"aktion": "rolle", "rolle": "pruefer"},
    )
    mia.refresh_from_db()
    assert mia.rolle == Benutzer.Rolle.MITARBEITER
    assert (
        "pruefer"
        not in client.get(reverse("konten:benutzer"))
        .content.decode()
        .split('name="rolle"')[1]
        .split("</select>")[0]
    )


def test_pruefer_sieht_nur_seinen_zeitraum(rechnungen):
    alt, neu = rechnungen
    c = angemeldet(pruefer())

    start = c.get(reverse("datenzugriff:start"))
    assert start.status_code == 200
    inhalt = start.content.decode()
    assert f"Daten des Jahres {JAHR - 1}" in inhalt
    assert "Rechnungsausgangsbuch" in inhalt and "Änderungsprotokoll" in inhalt
    # Kein Suchindex mit Adressen, keine Seitenleiste.
    assert "Bäckerei Korn" not in inhalt and "Neue Rechnung" not in inhalt

    tabelle = c.get(reverse("datenzugriff:tabelle", args=["rechnungen"])).content
    assert alt.nummer.encode() in tabelle and neu.nummer.encode() not in tabelle

    beleg = reverse("datenzugriff:beleg")
    offen = c.get(beleg, {"pfad": alt.datei})
    assert offen.status_code == 200 and offen["Content-Type"] == "application/pdf"
    assert c.get(beleg, {"pfad": neu.datei}).status_code == 404
    assert c.get(beleg, {"pfad": "db.sqlite3"}).status_code == 404


def test_suchen_und_sortieren(client, rechnungen):
    alt, neu = rechnungen
    adresse = reverse("datenzugriff:tabelle", args=["ausgangsbuch"])

    def tabelle(**abfrage):
        seite = client.get(adresse, abfrage).content.decode()
        return seite[seite.index("<tbody>") :]

    # Der Inhaber sieht zur Vorschau alle Jahre.
    beide = tabelle(sortiert=1, ab=1)
    assert beide.index(neu.nummer) < beide.index(alt.nummer)
    beide = tabelle(sortiert=1)
    assert beide.index(alt.nummer) < beide.index(neu.nummer)
    gefiltert = tabelle(q=neu.nummer)
    assert neu.nummer in gefiltert and alt.nummer not in gefiltert
    assert "1 von 2 Zeilen" in gefiltert


def test_pruefer_aendert_nichts(rechnungen):
    c = angemeldet(pruefer())
    assert c.get("/").url == reverse("datenzugriff:start")
    assert c.get(reverse("contacts:liste")).url == reverse("datenzugriff:start")
    assert c.get(reverse("konten:benutzer")).url == reverse("datenzugriff:start")
    vorher = Kontakt.objects.count()
    assert c.post(reverse("contacts:neu"), {"firmenname": "X"}).status_code == 403
    assert Kontakt.objects.count() == vorher
    assert c.post(reverse("datenzugriff:start")).status_code == 403
    assert (
        c.post(reverse("invoicing:stornieren", args=[rechnungen[0].pk])).status_code
        == 403
    )
    assert not Rechnung.objects.filter(storno_zu=rechnungen[0]).exists()
    assert c.post(reverse("konten:abmelden")).status_code == 302
    assert c.get(reverse("datenzugriff:start")).status_code == 302


def test_zugang_endet(anonym):
    konto = pruefer(zugang_bis=HEUTE - timedelta(days=1))
    seite = anonym.post(
        reverse("konten:anmelden"),
        {"email": konto.email, "kennwort": KENNWORT},
    )
    assert "abgelaufen" in seite.content.decode()
    assert "_auth_user_id" not in anonym.session
    assert Eintrag.objects.filter(
        aktion=Eintrag.Aktion.FEHLVERSUCH, beschreibung__contains="abgelaufen"
    ).exists()

    # Eine Sitzung von gestern endet bei der nächsten Anfrage.
    c = angemeldet(konto)
    antwort = c.get(reverse("datenzugriff:start"))
    assert antwort.url == reverse("konten:anmelden")
    assert "_auth_user_id" not in c.session


def test_mitarbeiter_sehen_den_datenzugriff_nicht():
    mia = Benutzer.objects.create_user(
        "mia@muster.test", name="Mia", rolle=Benutzer.Rolle.MITARBEITER
    )
    assert angemeldet(mia).get(reverse("datenzugriff:start")).status_code == 403


def test_pruefer_bekommt_keine_wiedervorlagen():
    konto = pruefer()
    assert konto not in WiedervorlageForm().fields["zustaendig"].queryset
