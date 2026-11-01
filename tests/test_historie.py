"""Kontakthistorie (Spezifikation K-2) – mit erfundenen Daten."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from archive.models import Altbeleg
from contacts.models import Kontakt
from core.models import Firmendaten
from historie import zeitleiste
from historie.models import Vorgang
from invoicing.models import Rechnung
from protokoll.models import Eintrag
from wiedervorlagen.models import Wiedervorlage
from zahlungen.models import Zahlung

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
    f.iban = "DE02120300000000202051"
    f.save()
    return f


def test_schnellerfassung(client, inhaber, kunde):
    url = reverse("historie:verlauf", args=[kunde.pk])
    antwort = client.post(
        url,
        {
            "art": "anruf",
            "zeitpunkt": "2026-11-02T09:15",
            "betreff": "Rückfrage zum Angebot",
            "text": "Möchte zwei Stunden mehr.",
        },
    )
    assert antwort.url == url
    v = Vorgang.objects.get()
    assert (v.art, v.benutzer, v.kontakt) == ("anruf", inhaber, kunde)
    assert (
        timezone.localtime(v.zeitpunkt).strftime("%d.%m.%Y %H:%M") == "02.11.2026 09:15"
    )
    assert Eintrag.objects.filter(art="Vorgang").exists()
    seite = client.get(url).content.decode()
    assert "Rückfrage zum Angebot" in seite and "02.11.2026 09:15" in seite


def test_betreff_oder_text_noetig(client, kunde):
    url = reverse("historie:verlauf", args=[kunde.pk])
    seite = client.post(url, {"art": "notiz", "zeitpunkt": "2026-11-02T09:15"})
    assert "Bitte einen Betreff oder einen Text eingeben." in seite.content.decode()
    assert not Vorgang.objects.exists()


def test_zeitleiste_sammelt_alles(client, firma, kunde, inhaber):
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": HEUTE.isoformat(),
            "leistung_von": HEUTE.isoformat(),
            "zahlungsziel": "14",
            "steuerfall": "kleinunternehmer",
            "kopftext": "",
            "fusstext": "",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["2"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    rechnung = Rechnung.objects.get()
    Zahlung.objects.create(rechnung=rechnung, datum=HEUTE, betrag=Decimal("160.00"))
    Vorgang.objects.create(
        kontakt=kunde,
        art="email",
        betreff="Rechnung geschickt",
        zeitpunkt=timezone.make_aware(datetime.combine(HEUTE, datetime.min.time())),
    )
    w = Wiedervorlage.objects.create(
        titel="Zahlung prüfen", faellig=HEUTE, kontakt=kunde
    )
    w.erledigen(inhaber, "Ist da.")
    Altbeleg.objects.create(
        art="rechnung",
        nummer="2024-007",
        datum=date(2024, 3, 1),
        kontakt=kunde,
        betrag=Decimal("99.00"),
        datei="archiv/altbelege/2024-007.pdf",
        sha256="0" * 64,
        originalname="alt.pdf",
    )

    punkte = zeitleiste.punkte(kunde)
    assert [(p.art, p.titel) for p in punkte] == [
        ("wiedervorlage", "Erledigt: Zahlung prüfen"),
        ("email", "Rechnung geschickt"),
        ("beleg", f"Rechnung {rechnung.nummer}"),
        ("zahlung", f"Überweisung zu Rechnung {rechnung.nummer}"),
        ("beleg", "Rechnung 2024-007"),
    ]
    assert punkte[2].betrag == Decimal("160.00")
    assert "rechnung=" in punkte[2].nachfassen

    url = reverse("historie:verlauf", args=[kunde.pk])
    nur_zahlungen = client.get(url, {"art": "zahlung"}).content.decode()
    assert "Überweisung zu Rechnung" in nur_zahlungen
    assert "Rechnung geschickt" not in nur_zahlungen
    seite = client.get(url).content.decode()
    assert reverse("archive:datei", args=[Altbeleg.objects.get().pk]) in seite
    assert "Nachfassen" in seite


def test_bearbeiten_und_loeschen(client, kunde):
    v = Vorgang.objects.create(kontakt=kunde, betreff="Termin vereinbart")
    url = reverse("historie:bearbeiten", args=[v.pk])
    client.post(
        url,
        {
            "art": "termin",
            "zeitpunkt": "2026-11-05T10:00",
            "betreff": "Termin am Freitag",
            "text": "",
        },
    )
    v.refresh_from_db()
    assert (v.art, v.betreff) == ("termin", "Termin am Freitag")
    client.post(reverse("historie:loeschen", args=[v.pk]))
    assert not Vorgang.objects.exists()


def test_verlauf_aus_der_adressliste(client, kunde):
    seite = client.get(reverse("contacts:liste")).content.decode()
    assert reverse("historie:verlauf", args=[kunde.pk]) in seite
    leer = client.get(reverse("historie:verlauf", args=[kunde.pk])).content.decode()
    assert "Noch nichts passiert" in leer
