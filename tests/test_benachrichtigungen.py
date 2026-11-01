"""Benachrichtigungen über Telegram (App benachrichtigungen) – mit erfundenen Daten,
ohne echte Nachrichten."""

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

from benachrichtigungen import autostart, nachrichten, telegram
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
SCHLUESSEL = "123456789:AAHmusterSchluesselFuerTests_0123456789"


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
    e.bot_schluessel = SCHLUESSEL
    e.bot_name = "muster_buero_bot"
    e.chat = "4711"
    e.empfaenger = inhaber
    e.save()
    return e


@pytest.fixture
def gesendet(monkeypatch):
    """Statt Telegram: Texte mitschreiben."""
    texte = []
    monkeypatch.setattr(
        telegram, "senden", lambda schluessel, chat, text: texte.append(text)
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
        "Heute: 14:30 Angebot nachfassen\n"
        "Überfällig: 1 Wiedervorlage\n"
        f"Nicht bezahlt: Rechnung {rechnung.nummer} 160,00 €\n"
        f"Zu zahlen: Nr. E-1 49,90 € bis {bald:%d.%m.}"
    ]
    # Keine Namen von Kunden oder Lieferanten an Telegram.
    assert "Korn" not in gesendet[0] and "Strom" not in gesendet[0]
    einstellung.refresh_from_db()
    assert einstellung.gesendet_am and not einstellung.fehler

    nachrichten.erinnern(um(8, 5))
    assert len(gesendet) == 1


def test_rechnungen_nur_einmal_gemeldet(client, einstellung, kunde, gesendet):
    ueberfaellige_rechnung(client, kunde)
    nachrichten.erinnern(um(8))
    assert "Nicht bezahlt" in gesendet[0]
    # Am nächsten Tag steht die Rechnung nicht noch einmal drin, also keine Nachricht.
    Gemeldet.objects.filter(anlass="tag").delete()
    nachrichten.erinnern(um(9))
    assert len(gesendet) == 1


def test_viele_eintraege_werden_gekuerzt(einstellung, gesendet):
    for nr in range(5):
        Wiedervorlage.objects.create(titel=f"Aufgabe {nr}", faellig=HEUTE)
    nachrichten.erinnern(um(8))
    assert "Aufgabe 0; Aufgabe 1; Aufgabe 2 und 2 weitere" in gesendet[0]


def test_ruhiger_tag_ohne_nachricht(einstellung, gesendet):
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
    assert gesendet == ["Muster IT: 14:30 Angebot nachfassen"]
    # Verschoben: wieder eine Erinnerung zur neuen Zeit.
    w.uhrzeit = time(15, 0)
    w.save()
    nachrichten.erinnern(um(14, 40))
    assert gesendet[-1] == "Muster IT: 15:00 Angebot nachfassen"
    nachrichten.erinnern(um(15, 10))
    assert len(gesendet) == 2


def test_ohne_vorlauf_keine_terminerinnerung(einstellung, gesendet):
    einstellung.uhrzeit = time(23, 59)
    einstellung.vorlauf = 0
    einstellung.save()
    Wiedervorlage.objects.create(titel="Termin", faellig=HEUTE, uhrzeit=time(14, 30))
    nachrichten.erinnern(um(14, 15))
    assert gesendet == []


@pytest.mark.parametrize("feld", ["aktiv", "chat"])
def test_ausgeschaltet_oder_nicht_verbunden(einstellung, gesendet, feld):
    setattr(einstellung, feld, Einstellung._meta.get_field(feld).get_default())
    einstellung.save()
    Wiedervorlage.objects.create(titel="Rückruf", faellig=HEUTE)
    nachrichten.erinnern(um(8))
    assert gesendet == [] and not Gemeldet.objects.exists()


def test_fehler_wird_wiederholt(einstellung, monkeypatch, gesendet):
    Wiedervorlage.objects.create(titel="Rückruf", faellig=HEUTE)

    def gestoppt(schluessel, chat, text):
        raise telegram.Fehler(telegram._meldung(403, "Forbidden"))

    with monkeypatch.context() as m:
        m.setattr(telegram, "senden", gestoppt)
        nachrichten.erinnern(um(8))
    einstellung.refresh_from_db()
    assert "gestoppt" in einstellung.fehler and not Gemeldet.objects.exists()
    nachrichten.erinnern(um(8, 5))
    einstellung.refresh_from_db()
    assert len(gesendet) == 1 and not einstellung.fehler
    # Der Stand der Nachrichten steht nicht im Änderungsprotokoll.
    assert not Eintrag.objects.filter(aenderungen__icontains="gestoppt").exists()


# ---------- Bot-API ----------


@pytest.fixture
def api(monkeypatch):
    """Antworten der Bot-API je Methode; schreibt die Anfragen mit."""
    antworten, anfragen = {}, []

    def urlopen(anfrage, timeout):
        anfragen.append(anfrage)
        antwort = antworten[anfrage.full_url.rsplit("/", 1)[1]]
        if isinstance(antwort, Exception):
            raise antwort
        return io.BytesIO(json.dumps(antwort).encode())

    monkeypatch.setattr(telegram.urllib.request, "urlopen", urlopen)
    return antworten, anfragen


def test_senden_an_telegram(api):
    antworten, anfragen = api
    antworten["sendMessage"] = {"ok": True, "result": {}}
    telegram.senden(SCHLUESSEL, "4711", "Hallo")
    assert (
        anfragen[0].full_url == f"https://api.telegram.org/bot{SCHLUESSEL}/sendMessage"
    )
    assert anfragen[0].data == b"chat_id=4711&text=Hallo"


def test_chat_nur_mit_dem_code(api):
    antworten, _ = api
    antworten["getUpdates"] = {
        "ok": True,
        "result": [
            {
                "message": {
                    "text": "/start abc123",
                    "chat": {"id": 11, "type": "private"},
                }
            },
            {"message": {"text": "/start", "chat": {"id": 22, "type": "private"}}},
            {"message": {"text": "/start abc123", "chat": {"id": 33, "type": "group"}}},
        ],
    }
    assert telegram.chat_finden(SCHLUESSEL, "abc123") == "11"
    assert telegram.chat_finden(SCHLUESSEL, "anders") is None


@pytest.mark.parametrize(
    ("fehler", "meldung"),
    [
        (
            urllib.error.HTTPError(
                "https://api.telegram.org/", 401, "", {}, io.BytesIO(b"{}")
            ),
            "kennt diesen Bot-Schlüssel nicht",
        ),
        (
            urllib.error.HTTPError(
                "https://api.telegram.org/",
                400,
                "",
                {},
                io.BytesIO(b'{"description": "Bad Request: chat not found"}'),
            ),
            "neu verbinden",
        ),
        (urllib.error.URLError("offline"), "Keine Verbindung"),
    ],
)
def test_fehler_von_telegram(api, fehler, meldung):
    antworten, _ = api
    antworten["sendMessage"] = fehler
    with pytest.raises(telegram.Fehler, match=meldung):
        telegram.senden(SCHLUESSEL, "4711", "Hallo")


# ---------- Seite ----------


def test_einrichten_und_verbinden(client, inhaber, monkeypatch):
    monkeypatch.setattr(telegram, "bot", lambda schluessel: "muster_buero_bot")
    url = reverse("benachrichtigungen:einstellungen")
    seite = client.get(url).content.decode()
    assert "@BotFather" in seite and "Erscheint, sobald der Schlüssel" in seite

    daten = {"bot_schluessel": SCHLUESSEL, "uhrzeit": "07:30", "vorlauf": "30"}
    assert client.post(url, daten).url == url
    e = Einstellung.laden()
    assert (e.bot_schluessel, e.bot_name, e.chat) == (
        SCHLUESSEL,
        "muster_buero_bot",
        "",
    )
    seite = client.get(url).content.decode()
    assert SCHLUESSEL not in seite and "Leer lassen" in seite
    assert f"https://t.me/muster_buero_bot?start={e.code}" in seite

    # Noch nicht auf „Starten“ getippt.
    monkeypatch.setattr(telegram, "chat_finden", lambda schluessel, code: None)
    antwort = client.post(reverse("benachrichtigungen:verbinden"), follow=True)
    assert "Noch nicht gefunden" in antwort.content.decode()

    gesendet = []
    monkeypatch.setattr(
        telegram,
        "chat_finden",
        lambda schluessel, code: "4711" if code == e.code else None,
    )
    monkeypatch.setattr(
        telegram, "senden", lambda schluessel, chat, text: gesendet.append((chat, text))
    )
    antwort = client.post(reverse("benachrichtigungen:verbinden"), follow=True)
    e.refresh_from_db()
    assert (e.chat, e.aktiv, e.empfaenger) == ("4711", True, inhaber)
    assert gesendet == [("4711", benachrichtigungen_views.VERBUNDEN)]
    assert "Verbunden mit @muster_buero_bot" in antwort.content.decode()
    assert not Eintrag.objects.filter(aenderungen__icontains="AAHmuster").exists()


def test_falscher_schluessel(client, monkeypatch):
    url = reverse("benachrichtigungen:einstellungen")
    seite = client.post(
        url, {"bot_schluessel": "hallo", "uhrzeit": "07:30", "vorlauf": "30"}
    ).content.decode()
    assert "Das ist kein Bot-Schlüssel" in seite

    def unbekannt(schluessel):
        raise telegram.Fehler(telegram._meldung(401, "Unauthorized"))

    monkeypatch.setattr(telegram, "bot", unbekannt)
    seite = client.post(
        url, {"bot_schluessel": SCHLUESSEL, "uhrzeit": "07:30", "vorlauf": "30"}
    ).content.decode()
    assert "kennt diesen Bot-Schlüssel nicht" in seite
    assert not Einstellung.laden().bot_schluessel


def test_testen_und_trennen(client, einstellung, gesendet):
    client.post(reverse("benachrichtigungen:testen"))
    assert gesendet == [benachrichtigungen_views.TEST]
    code = einstellung.code
    client.post(reverse("benachrichtigungen:trennen"))
    einstellung.refresh_from_db()
    assert not einstellung.chat and not einstellung.aktiv and einstellung.code != code
    # Der Bot bleibt; nur neu verbinden.
    assert einstellung.bot_schluessel == SCHLUESSEL


def test_nur_fuer_inhaber(anonym):
    anonym.force_login(
        Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    )
    assert anonym.get(reverse("benachrichtigungen:einstellungen")).status_code == 403
    assert anonym.post(reverse("benachrichtigungen:verbinden")).status_code == 403


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
