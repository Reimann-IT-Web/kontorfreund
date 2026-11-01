"""Wiedervorlagen (Spezifikation K-4) – mit erfundenen Daten."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from konten.models import Benutzer
from wiedervorlagen.models import Wiedervorlage, naechster_monat

pytestmark = pytest.mark.django_db

HEUTE = date.today()


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.save()
    return f


def vorlage(titel, tage=0, **mehr):
    return Wiedervorlage.objects.create(
        titel=titel, faellig=HEUTE + timedelta(days=tage), **mehr
    )


def test_anlegen(client, inhaber, firma, kunde):
    antwort = client.post(
        reverse("wiedervorlagen:neu"),
        {
            "titel": "Angebot nachfassen",
            "faellig": HEUTE.isoformat(),
            "uhrzeit": "14:30",
            "kontakt": kunde.pk,
            "zustaendig": inhaber.pk,
            "notiz": "",
        },
    )
    assert antwort.url == reverse("wiedervorlagen:liste")
    w = Wiedervorlage.objects.get()
    assert (w.titel, w.kontakt, w.zustaendig, w.uhrzeit.hour) == (
        "Angebot nachfassen",
        kunde,
        inhaber,
        14,
    )
    start = client.get(reverse("core:start"))
    assert list(start.context["wiedervorlagen"]) == [w]
    start = start.content.decode()
    assert "1 Wiedervorlage fällig" in start
    assert "heute 14:30" in start


def test_liste_nach_faelligkeit(client):
    for titel, tage in [("Später", 30), ("Bald", 3), ("Heute", 0), ("Alt", -2)]:
        vorlage(f"Aufgabe {titel}", tage)
    seite = client.get(reverse("wiedervorlagen:liste")).content.decode()
    reihenfolge = [
        seite.index(text)
        for text in [
            "Überfällig",
            "Aufgabe Alt",
            ">Heute <",
            "Aufgabe Heute",
            "Demnächst",
            "Aufgabe Bald",
            "Später <",
            "Aufgabe Später",
        ]
    ]
    assert reihenfolge == sorted(reihenfolge)


@pytest.mark.parametrize(
    ("tag", "erwartet"),
    [
        (date(2026, 1, 31), date(2026, 2, 28)),
        (date(2028, 1, 31), date(2028, 2, 29)),
        (date(2026, 12, 15), date(2027, 1, 15)),
    ],
)
def test_naechster_monat(tag, erwartet):
    assert naechster_monat(tag) == erwartet


@pytest.mark.parametrize(
    ("wohin", "erwartet"),
    [
        ("morgen", HEUTE + timedelta(days=1)),
        ("woche", HEUTE + timedelta(days=7)),
        ("monat", naechster_monat(HEUTE)),
    ],
)
def test_verschieben(client, wohin, erwartet):
    w = vorlage("Rückruf", -3)
    antwort = client.post(
        reverse("wiedervorlagen:aendern", args=[w.pk]),
        {"verschieben": wohin, "weiter": reverse("core:start")},
    )
    assert antwort.url == reverse("core:start")
    w.refresh_from_db()
    assert w.faellig == erwartet


def test_erledigen_und_wieder_oeffnen(client, inhaber, kunde):
    w = vorlage("Rückruf", kontakt=kunde)
    url = reverse("wiedervorlagen:aendern", args=[w.pk])
    client.post(url, {"verschieben": "", "aktion": "erledigen", "ergebnis": "Zugesagt"})
    w.refresh_from_db()
    assert w.erledigt and w.erledigt_von == inhaber and w.ergebnis == "Zugesagt"
    assert client.get(reverse("wiedervorlagen:liste")).context["gruppen"] == []
    erledigt = client.get(reverse("wiedervorlagen:liste"), {"zeigen": "erledigt"})
    assert "Rückruf" in erledigt.content.decode()
    verlauf = client.get(reverse("historie:verlauf", args=[kunde.pk])).content.decode()
    assert "Erledigt: Rückruf" in verlauf and "Zugesagt" in verlauf

    client.post(url, {"aktion": "oeffnen"})
    w.refresh_from_db()
    assert not w.erledigt


def test_aus_rechnung_vorbelegt(client, kunde):
    rechnung = Rechnung.objects.create(kontakt=kunde)
    url = reverse("wiedervorlagen:neu")
    seite = client.get(
        url, {"rechnung": rechnung.pk, "in": "14", "titel": "Zahlung prüfen"}
    ).content.decode()
    assert 'value="Zahlung prüfen"' in seite
    assert f'value="{HEUTE + timedelta(days=14):%Y-%m-%d}"' in seite
    client.post(
        f"{url}?rechnung={rechnung.pk}",
        {"titel": "Zahlung prüfen", "faellig": HEUTE.isoformat(), "kontakt": ""},
    )
    w = Wiedervorlage.objects.get()
    assert (w.rechnung, w.kontakt) == (rechnung, kunde)


def test_ruecksprung_nur_innerhalb(client):
    w = vorlage("Rückruf")
    antwort = client.post(
        reverse("wiedervorlagen:aendern", args=[w.pk]),
        {"aktion": "erledigen", "weiter": "https://example.com/"},
    )
    assert antwort.url == reverse("wiedervorlagen:liste")
    seite = client.get(
        reverse("wiedervorlagen:bearbeiten", args=[w.pk]),
        {"weiter": "javascript:alert(1)"},
    ).content.decode()
    assert "javascript:" not in seite


def test_meine_und_alle(client, inhaber):
    anna = Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    vorlage("Für Anna", zustaendig=anna)
    vorlage("Für mich", zustaendig=inhaber)
    vorlage("Für alle")
    meine = client.get(reverse("wiedervorlagen:liste")).content.decode()
    assert "Für mich" in meine and "Für alle" in meine and "Für Anna" not in meine
    assert "2 Wiedervorlagen fällig" in meine
    alle = client.get(reverse("wiedervorlagen:liste"), {"wer": "alle"}).content.decode()
    assert "Für Anna" in alle and "für Anna Beispiel" in alle


def test_loeschen(client):
    w = vorlage("Rückruf")
    client.post(reverse("wiedervorlagen:loeschen", args=[w.pk]))
    assert not Wiedervorlage.objects.exists()
