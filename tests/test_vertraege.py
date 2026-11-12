"""Verträge für wiederkehrende Rechnungen (B-10) – mit erfundenen Daten."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from benachrichtigungen import nachrichten, telegram
from benachrichtigungen.models import Einstellung
from contacts import datenschutz
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from vertraege import abrechnen
from vertraege.models import Vertrag, monate_spaeter
from wiedervorlagen.models import Wiedervorlage

pytestmark = pytest.mark.django_db

HEUTE = date.today()


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.email = "post@muster.test"
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )


def formular(kunde, beginn, **mehr):
    """Halbjährlich 6 × 50 € abzüglich 8 % Rabatt = 276 €."""
    return {
        "vertrag-bezeichnung": "Wartung Server",
        "vertrag-kontakt": kunde.pk,
        "vertrag-betreff": "Wartungsvertrag",
        "vertrag-rhythmus": "6",
        "vertrag-beginn": beginn.isoformat(),
        "vertrag-ende": "",
        "vertrag-nachfragen": "30",
        "vertrag-zahlungsziel": "0",
        "vertrag-steuerfall": "kleinunternehmer",
        "vertrag-rabatt_prozent": "8",
        "vertrag-kopftext": "Sehr geehrte Damen und Herren,",
        "vertrag-fusstext": "Mit freundlichen Grüßen",
        "bezeichnung": ["Wartung Server und Netzwerk"],
        "beschreibung": ["Updates, Datensicherung prüfen"],
        "menge": ["6"],
        "einheit": ["Monat"],
        "preis": ["50,00"],
        **mehr,
    }


def anlegen(client, kunde, beginn, **mehr):
    antwort = client.post(reverse("vertraege:neu"), formular(kunde, beginn, **mehr))
    assert antwort.status_code == 302, antwort.text
    return Vertrag.objects.latest("pk")


@pytest.mark.parametrize(
    ("tag", "monate", "erwartet"),
    [
        (date(2027, 1, 1), 6, date(2027, 7, 1)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),
        (date(2027, 1, 31), 1, date(2027, 2, 28)),
        (date(2026, 11, 15), 3, date(2027, 2, 15)),
    ],
)
def test_monate_spaeter(tag, monate, erwartet):
    assert monate_spaeter(tag, monate) == erwartet


def test_vertrag_ab_heute_legt_gleich_den_entwurf_an(client, firma, kunde):
    antwort = client.post(reverse("vertraege:neu"), formular(kunde, HEUTE), follow=True)
    vertrag = Vertrag.objects.get()

    rechnung = Rechnung.objects.get()
    assert rechnung.ist_entwurf and rechnung.vertrag == vertrag
    assert rechnung.datum == HEUTE
    assert rechnung.leistung_von == HEUTE
    assert rechnung.leistung_bis == monate_spaeter(HEUTE, 6) - timedelta(days=1)
    assert rechnung.rabatt_prozent == Decimal("8")
    assert rechnung.zahlungsziel == 0
    assert rechnung.betreff == "Wartungsvertrag"
    assert [(p.bezeichnung, p.menge, p.preis) for p in rechnung.positionen.all()] == [
        ("Wartung Server und Netzwerk", Decimal("6"), Decimal("50.00"))
    ]
    assert rechnung.summen()[2] == Decimal("276.00")
    assert vertrag.naechster == monate_spaeter(HEUTE, 6)
    assert "Der Rechnungsentwurf liegt unter Rechnungen bereit (276,00" in antwort.text

    editor = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk])).text
    assert "Aus dem Vertrag" in editor and "Wartung Server" in editor
    liste = client.get(reverse("vertraege:liste")).text
    assert "Wartung Server" in liste and "276,00" in liste


def test_jeder_zeitraum_genau_einmal_auch_nachgeholt(client, firma, kunde):
    beginn = HEUTE + timedelta(days=10)
    vertrag = anlegen(client, kunde, beginn)
    assert not Rechnung.objects.exists()
    assert vertrag.naechster == beginn

    assert len(abrechnen.faellige(beginn)) == 1
    assert abrechnen.faellige(beginn) == []  # nicht doppelt

    # Ein Jahr lang nicht gelaufen: beide offenen Halbjahre einzeln, datiert auf heute.
    spaeter = monate_spaeter(beginn, 12) + timedelta(days=3)
    neu = abrechnen.faellige(spaeter)
    assert [r.leistung_von for r in neu] == [
        monate_spaeter(beginn, 6),
        monate_spaeter(beginn, 12),
    ]
    assert {r.datum for r in neu} == {spaeter}
    vertrag.refresh_from_db()
    assert vertrag.naechster == monate_spaeter(beginn, 18)


def test_nach_dem_ende_kein_entwurf(client, firma, kunde):
    beginn = HEUTE + timedelta(days=1)
    vertrag = anlegen(
        client,
        kunde,
        beginn,
        **{"vertrag-ende": monate_spaeter(beginn, 6).isoformat()},
    )
    assert len(abrechnen.faellige(monate_spaeter(beginn, 12))) == 2
    vertrag.refresh_from_db()
    assert not vertrag.laeuft
    assert "beendet" in client.get(reverse("vertraege:liste")).text


def test_aenderungen_gelten_fuer_die_naechsten_entwuerfe(client, firma, kunde):
    beginn = HEUTE + timedelta(days=1)
    vertrag = anlegen(client, kunde, beginn)
    (erster,) = abrechnen.faellige(beginn)

    client.post(
        reverse("vertraege:bearbeiten", args=[vertrag.pk]),
        formular(kunde, beginn, preis=["55,00"]),
    )
    (zweiter,) = abrechnen.faellige(monate_spaeter(beginn, 6))
    assert erster.positionen.get().preis == Decimal("50.00")
    assert zweiter.positionen.get().preis == Decimal("55.00")


def test_beginn_verschieben_nur_vor_dem_ersten_entwurf(client, firma, kunde):
    beginn = HEUTE + timedelta(days=5)
    vertrag = anlegen(client, kunde, beginn)
    spaeter = beginn + timedelta(days=30)
    client.post(
        reverse("vertraege:bearbeiten", args=[vertrag.pk]), formular(kunde, spaeter)
    )
    vertrag.refresh_from_db()
    assert vertrag.naechster == spaeter

    abrechnen.faellige(spaeter)
    client.post(
        reverse("vertraege:bearbeiten", args=[vertrag.pk]),
        formular(kunde, beginn),
    )
    vertrag.refresh_from_db()
    assert vertrag.naechster == monate_spaeter(spaeter, 6)


def test_ohne_position_wird_nichts_gespeichert(client, firma, kunde):
    antwort = client.post(
        reverse("vertraege:neu"),
        formular(kunde, HEUTE, bezeichnung=[""], beschreibung=[""], preis=[""]),
    )
    assert "braucht mindestens eine Position" in antwort.text
    assert not Vertrag.objects.exists()


def test_aus_einer_rechnung_wiederholen(client, firma, kunde):
    vertrag = anlegen(client, kunde, HEUTE)
    vorlage = Rechnung.objects.get()
    vorlage.vertrag = None
    vorlage.save()

    seite = client.get(reverse("vertraege:neu") + f"?aus_rechnung={vorlage.pk}").text
    assert "Wartung Server und Netzwerk" in seite
    assert 'name="vertrag-rabatt_prozent" value="8,00"' in seite
    assert vertrag.pk  # der erste bleibt unberührt


def test_middleware_legt_faellige_entwuerfe_an(client, firma, kunde):
    beginn = HEUTE + timedelta(days=1)
    vertrag = anlegen(client, kunde, beginn)
    Vertrag.objects.filter(pk=vertrag.pk).update(naechster=HEUTE)

    abrechnen._naechste_suche = 0.0
    client.get(reverse("core:start"))

    assert Rechnung.objects.filter(vertrag=vertrag, leistung_von=HEUTE).exists()


def test_loeschen_laesst_die_rechnungen_stehen(client, firma, kunde):
    vertrag = anlegen(client, kunde, HEUTE)
    rechnung = Rechnung.objects.get()

    client.post(reverse("vertraege:loeschen", args=[vertrag.pk]))

    assert not Vertrag.objects.exists()
    rechnung.refresh_from_db()
    assert rechnung.vertrag is None


def test_telegram_nennt_neue_entwuerfe_einmal(
    client, firma, kunde, inhaber, monkeypatch
):
    gesendet = []
    monkeypatch.setattr(telegram, "senden", lambda s, c, text: gesendet.append(text))
    e = Einstellung.laden()
    e.aktiv, e.bot_schluessel, e.chat, e.empfaenger = True, "1:abc", "4711", inhaber
    e.save()
    beginn = HEUTE + timedelta(days=1)
    vertrag = anlegen(client, kunde, beginn)
    Vertrag.objects.filter(pk=vertrag.pk).update(naechster=HEUTE)

    acht = timezone.make_aware(datetime.combine(HEUTE, time(23, 59)))
    nachrichten.erinnern(acht)

    assert len(gesendet) == 1
    assert "Neue Entwürfe: Wartung Server 276,00" in gesendet[0]
    assert "Korn" not in gesendet[0]


def test_sperren_beendet_und_loeschen_entfernt_vertraege(client, firma, kunde, inhaber):
    vertrag = anlegen(client, kunde, HEUTE + timedelta(days=3))

    datenschutz.sperren(kunde, inhaber)
    vertrag.refresh_from_db()
    assert not vertrag.laeuft
    assert abrechnen.faellige(HEUTE + timedelta(days=400)) == []

    daten = datenschutz.auskunft_daten(kunde, [], timezone.now())
    assert daten["Verträge"][0]["Bezeichnung"] == "Wartung Server"

    datenschutz.loeschen(kunde)
    assert not Vertrag.objects.exists()
    assert not Kontakt.objects.filter(pk=kunde.pk).exists()


def test_vor_jeder_verlaengerung_nachfragen(client, firma, kunde):
    beginn = HEUTE + timedelta(days=10)
    vertrag = anlegen(client, kunde, beginn)
    # Gerade angelegt: Für den ersten Zeitraum ist alles besprochen.
    abrechnen.faellige(beginn)
    assert not Wiedervorlage.objects.exists()

    zweiter = monate_spaeter(beginn, 6)
    abrechnen.faellige(zweiter - timedelta(days=31))
    assert not Wiedervorlage.objects.exists()
    abrechnen.faellige(zweiter - timedelta(days=30))
    abrechnen.faellige(zweiter - timedelta(days=29))  # nicht doppelt
    (w,) = Wiedervorlage.objects.all()
    assert w.titel == (
        f"Vertrag „Wartung Server“ ab {zweiter:%d.%m.%Y}: Fortsetzung und Preis klären"
    )
    assert w.kontakt == kunde
    assert w.faellig == zweiter - timedelta(days=30)
    vertrag.refresh_from_db()
    assert vertrag.nachgefragt_fuer == zweiter


def test_bestehender_vertrag_fragt_schon_vor_dem_ersten_zeitraum(client, firma, kunde):
    beginn = HEUTE + timedelta(days=60)
    anlegen(client, kunde, beginn)

    abrechnen.faellige(beginn - timedelta(days=30))

    assert Wiedervorlage.objects.get().faellig == beginn - timedelta(days=30)


def test_ohne_nachfragen_keine_wiedervorlage(client, firma, kunde):
    beginn = HEUTE + timedelta(days=60)
    anlegen(client, kunde, beginn, **{"vertrag-nachfragen": "0"})

    abrechnen.faellige(beginn)

    assert not Wiedervorlage.objects.exists()
