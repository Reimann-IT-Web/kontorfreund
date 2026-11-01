"""Benachrichtigungen per SMS (App benachrichtigungen) – mit erfundenen Daten, ohne echte SMS."""

import io
import json
import sqlite3
import urllib.error
from contextlib import closing
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from benachrichtigungen import autostart, nachrichten, sms
from benachrichtigungen import views as benachrichtigungen_views
from benachrichtigungen.models import Einstellung, Gemeldet
from contacts.models import Kontakt
from core import firmen
from core.models import Firmendaten
from eingang.models import Eingangsrechnung
from invoicing.models import Rechnung
from konten.models import Benutzer
from protokoll.models import Eintrag
from wiedervorlagen.models import Wiedervorlage

pytestmark = pytest.mark.django_db

HEUTE = date.today()


def um(stunde, minute=0):
    return timezone.make_aware(datetime.combine(HEUTE, time(stunde, minute)))


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


@pytest.fixture
def einstellung(inhaber, firma):
    e = Einstellung.laden()
    e.aktiv = True
    e.handy = "+491711234567"
    e.api_schluessel = "geheimer-schluessel"
    e.empfaenger = inhaber
    e.save()
    return e


@pytest.fixture
def gesendet(monkeypatch):
    """Statt seven.io: Texte mitschreiben."""
    texte = []
    monkeypatch.setattr(
        sms, "senden", lambda schluessel, nummer, text: texte.append(text)
    )
    return texte


def ueberfaellige_rechnung(client, kunde):
    vor_einem_monat = HEUTE - timedelta(days=30)
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": vor_einem_monat.isoformat(),
            "leistung_von": vor_einem_monat.isoformat(),
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
    assert rechnung.ueberfaellig
    return rechnung


def eingangsrechnung(nummer, faellig, lieferant="Strom AG"):
    return Eingangsrechnung.objects.create(
        format="xml",
        syntax="UBL",
        art="380",
        nummer=nummer,
        datum=HEUTE,
        faellig=faellig,
        lieferant=lieferant,
        waehrung="EUR",
        brutto=Decimal("49.90"),
        zahlbetrag=Decimal("49.90"),
        datei=f"archiv/eingang/{nummer}.xml",
        sha256=nummer.ljust(64, "0"),
        originalname=f"{nummer}.xml",
    )


def test_tagesuebersicht_einmal_am_tag(client, einstellung, kunde, gesendet):
    rechnung = ueberfaellige_rechnung(client, kunde)
    Wiedervorlage.objects.create(
        titel="Angebot nachfassen", faellig=HEUTE, uhrzeit=time(14, 30), kontakt=kunde
    )
    Wiedervorlage.objects.create(titel="Rückruf", faellig=HEUTE - timedelta(days=2))
    anna = Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    Wiedervorlage.objects.create(titel="Für Anna", faellig=HEUTE, zustaendig=anna)
    bald = HEUTE + timedelta(days=2)
    eingangsrechnung("E-1", bald)
    eingangsrechnung("E-2", HEUTE + timedelta(days=10), lieferant="Später GmbH")

    nachrichten.erinnern(um(7))
    assert gesendet == []  # vor der eingestellten Uhrzeit

    nachrichten.erinnern(um(8))
    assert gesendet == [
        f"Muster IT, {HEUTE:%d.%m.}:\n"
        "Heute: 14:30 Angebot nachfassen (Bäckerei Korn)\n"
        "Überfällig: 1 Wiedervorlage\n"
        f"Nicht bezahlt: {rechnung.nummer} Bäckerei Korn 160,00 €\n"
        f"Zu zahlen: Strom AG 49,90 € bis {bald:%d.%m.}"
    ]
    einstellung.refresh_from_db()
    assert einstellung.gesendet_am and not einstellung.fehler

    nachrichten.erinnern(um(8, 5))
    assert len(gesendet) == 1


def test_rechnungen_nur_einmal_gemeldet(client, einstellung, kunde, gesendet):
    ueberfaellige_rechnung(client, kunde)
    Gemeldet.objects.create(
        anlass="tag", schluessel=(HEUTE - timedelta(days=1)).isoformat()
    )
    nachrichten.erinnern(um(8))
    assert "Nicht bezahlt" in gesendet[0]
    # Am nächsten Tag steht die Rechnung nicht noch einmal drin, also keine SMS.
    Gemeldet.objects.filter(anlass="tag").delete()
    nachrichten.erinnern(um(9))
    assert len(gesendet) == 1


def test_viele_eintraege_werden_gekuerzt(einstellung, gesendet):
    for nr in range(5):
        Wiedervorlage.objects.create(titel=f"Aufgabe {nr}", faellig=HEUTE)
    nachrichten.erinnern(um(8))
    assert "Aufgabe 0; Aufgabe 1; Aufgabe 2 und 2 weitere" in gesendet[0]


def test_ruhiger_tag_ohne_sms(einstellung, gesendet):
    nachrichten.erinnern(um(8))
    assert gesendet == []
    assert Gemeldet.objects.filter(anlass="tag", schluessel=HEUTE.isoformat()).exists()


def test_termin_vorher(einstellung, kunde, gesendet):
    einstellung.uhrzeit = time(23, 59)
    einstellung.save()
    w = Wiedervorlage.objects.create(
        titel="Angebot nachfassen", faellig=HEUTE, uhrzeit=time(14, 30), kontakt=kunde
    )
    nachrichten.erinnern(um(13, 50))
    assert gesendet == []
    nachrichten.erinnern(um(14, 5))
    nachrichten.erinnern(um(14, 10))
    assert gesendet == ["Muster IT: 14:30 Angebot nachfassen (Bäckerei Korn)"]
    # Verschoben: wieder eine Erinnerung zur neuen Zeit.
    w.uhrzeit = time(15, 0)
    w.save()
    nachrichten.erinnern(um(14, 40))
    assert gesendet[-1] == "Muster IT: 15:00 Angebot nachfassen (Bäckerei Korn)"
    nachrichten.erinnern(um(15, 10))
    assert len(gesendet) == 2


def test_ohne_vorlauf_keine_terminerinnerung(einstellung, gesendet):
    einstellung.uhrzeit = time(23, 59)
    einstellung.vorlauf = 0
    einstellung.save()
    Wiedervorlage.objects.create(titel="Termin", faellig=HEUTE, uhrzeit=time(14, 30))
    nachrichten.erinnern(um(14, 15))
    assert gesendet == []


def test_ausgeschaltet(einstellung, gesendet):
    einstellung.aktiv = False
    einstellung.save()
    Wiedervorlage.objects.create(titel="Rückruf", faellig=HEUTE)
    nachrichten.erinnern(um(8))
    assert gesendet == [] and not Gemeldet.objects.exists()


def test_fehler_wird_wiederholt(einstellung, monkeypatch, gesendet):
    Wiedervorlage.objects.create(titel="Rückruf", faellig=HEUTE)

    def guthaben_leer(schluessel, nummer, text):
        raise sms.Fehler(sms.MELDUNGEN["500"])

    with monkeypatch.context() as m:
        m.setattr(sms, "senden", guthaben_leer)
        nachrichten.erinnern(um(8))
    einstellung.refresh_from_db()
    assert "Guthaben" in einstellung.fehler and not Gemeldet.objects.exists()
    nachrichten.erinnern(um(8, 5))
    einstellung.refresh_from_db()
    assert len(gesendet) == 1 and not einstellung.fehler
    # Der Stand der SMS steht nicht im Änderungsprotokoll.
    assert not Eintrag.objects.filter(beschreibung__icontains="Guthaben").exists()


class Antwort(io.BytesIO):
    pass


@pytest.mark.parametrize(
    ("antwort", "meldung"),
    [
        ({"success": "100"}, None),
        ({"success": "900"}, "API-Schlüssel"),
        ({"success": "500"}, "Guthaben"),
        ({"success": "777"}, "Code 777"),
    ],
)
def test_sms_an_seven(monkeypatch, antwort, meldung):
    anfragen = []

    def urlopen(anfrage, timeout):
        anfragen.append(anfrage)
        return Antwort(json.dumps(antwort).encode())

    monkeypatch.setattr(sms.urllib.request, "urlopen", urlopen)
    if meldung:
        with pytest.raises(sms.Fehler, match=meldung):
            sms.senden("schluessel", "+491711234567", "Hallo")
    else:
        sms.senden("schluessel", "+491711234567", "Hallo")
    anfrage = anfragen[0]
    assert anfrage.full_url == "https://gateway.seven.io/api/sms"
    assert anfrage.get_header("X-api-key") == "schluessel"
    assert anfrage.data == b"to=%2B491711234567&text=Hallo"


@pytest.mark.parametrize(
    ("fehler", "meldung"),
    [
        (
            urllib.error.HTTPError(
                "https://gateway.seven.io/api/sms", 401, "", {}, None
            ),
            "API-Schlüssel",
        ),
        (urllib.error.URLError("offline"), "Keine Verbindung"),
    ],
)
def test_sms_ohne_verbindung(monkeypatch, fehler, meldung):
    def urlopen(anfrage, timeout):
        raise fehler

    monkeypatch.setattr(sms.urllib.request, "urlopen", urlopen)
    with pytest.raises(sms.Fehler, match=meldung):
        sms.senden("schluessel", "+491711234567", "Hallo")


def test_einstellungen_speichern(client, inhaber):
    url = reverse("benachrichtigungen:einstellungen")
    daten = {
        "aktiv": "on",
        "handy": "0171 / 123 45 67",
        "api_schluessel": "geheimer-schluessel",
        "uhrzeit": "07:30",
        "vorlauf": "30",
    }
    assert client.post(url, daten).url == url
    e = Einstellung.laden()
    assert (e.handy, e.api_schluessel, e.empfaenger) == (
        "+491711234567",
        "geheimer-schluessel",
        inhaber,
    )
    seite = client.get(url).content.decode()
    assert "geheimer-schluessel" not in seite and "Leer lassen" in seite
    # Leer gelassen bleibt der Schlüssel.
    client.post(url, {**daten, "api_schluessel": ""})
    assert Einstellung.laden().api_schluessel == "geheimer-schluessel"
    assert not Eintrag.objects.filter(aenderungen__icontains="geheimer").exists()


def test_eingeschaltet_braucht_nummer_und_schluessel(client):
    seite = client.post(
        reverse("benachrichtigungen:einstellungen"),
        {"aktiv": "on", "handy": "", "uhrzeit": "07:30", "vorlauf": "30"},
    ).content.decode()
    assert seite.count("Bitte ausfüllen, damit SMS ankommen.") == 2
    assert not Einstellung.laden().aktiv


def test_falsche_handynummer(client):
    seite = client.post(
        reverse("benachrichtigungen:einstellungen"),
        {"handy": "12", "uhrzeit": "07:30", "vorlauf": "30"},
    ).content.decode()
    assert "Bitte eine Handynummer eingeben" in seite


def test_testnachricht(client, monkeypatch):
    texte = []
    monkeypatch.setattr(
        sms, "senden", lambda schluessel, nummer, text: texte.append((nummer, text))
    )
    antwort = client.post(
        reverse("benachrichtigungen:einstellungen"),
        {
            "handy": "+49 171 1234567",
            "api_schluessel": "geheimer-schluessel",
            "uhrzeit": "07:30",
            "vorlauf": "30",
            "test": "1",
        },
        follow=True,
    )
    assert texte == [("+491711234567", benachrichtigungen_views.TEST)]
    assert "Testnachricht gesendet" in antwort.content.decode()


def test_nur_fuer_inhaber(anonym):
    anonym.force_login(
        Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    )
    assert anonym.get(reverse("benachrichtigungen:einstellungen")).status_code == 403


def test_beim_anmelden_starten(client, monkeypatch):
    gesetzt = []
    monkeypatch.setattr(autostart, "moeglich", lambda: True)
    monkeypatch.setattr(autostart, "an", lambda: False)
    monkeypatch.setattr(autostart, "setzen", gesetzt.append)
    seite = client.get(reverse("benachrichtigungen:einstellungen")).content.decode()
    assert "Beim Anmelden an Windows im Hintergrund starten" in seite
    client.post(reverse("benachrichtigungen:autostart"), {"ein": "1"})
    assert gesetzt == [True]


def test_befehl_erinnern(monkeypatch):
    aufgerufen = []
    monkeypatch.setattr(
        "benachrichtigungen.management.commands.erinnern.erinnern",
        lambda: aufgerufen.append(True),
    )
    call_command("erinnern")
    assert aufgerufen == [True]


def test_startprogramm_liest_den_schalter(tmp_path):
    assert not firmen.benachrichtigt(tmp_path)
    with closing(sqlite3.connect(tmp_path / "db.sqlite3")) as db:
        db.execute(
            "CREATE TABLE benachrichtigungen_einstellung (id INTEGER PRIMARY KEY, aktiv BOOL)"
        )
        db.execute("INSERT INTO benachrichtigungen_einstellung VALUES (1, 1)")
        db.commit()
    assert firmen.benachrichtigt(tmp_path)
