"""Tägliche Prüfung der abgelegten Dateien (Spezifikation B-9) – mit erfundenen Daten."""

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from archive import pruefung
from archive.models import Altbeleg, Pruefung
from backups import sicherung
from benachrichtigungen import nachrichten, telegram
from benachrichtigungen.models import Einstellung
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung
from konten.models import Benutzer
from protokoll.models import Eintrag

pytestmark = pytest.mark.django_db

HEUTE = date.today()


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
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )


@pytest.fixture
def belege(client, firma, kunde):
    """Eine festgeschriebene Rechnung und ein Altbeleg, beide mit abgelegter Datei."""
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
    inhalt = b"%PDF-1.4 Rechnung aus dem Altprogramm"
    datei = Path(settings.DATA_DIR) / "archiv" / "altbelege" / "RE-1001.pdf"
    datei.parent.mkdir(parents=True)
    datei.write_bytes(inhalt)
    altbeleg = Altbeleg.objects.create(
        art=Altbeleg.Art.RECHNUNG,
        nummer="1001",
        datum=HEUTE - timedelta(days=400),
        kontakt=kunde,
        betrag=Decimal("50.00"),
        datei="archiv/altbelege/RE-1001.pdf",
        sha256=hashlib.sha256(inhalt).hexdigest(),
        originalname="RE-1001.pdf",
    )
    return rechnung, altbeleg


def pfad(beleg):
    return Path(settings.DATA_DIR) / beleg.datei


def warnung(antwort):
    return "fehlen oder sind verändert" in antwort.content.decode()


def test_alles_unveraendert(client, belege):
    ergebnis = pruefung.pruefen()

    assert (ergebnis.anzahl, ergebnis.befunde) == (2, [])
    assert not Eintrag.objects.filter(aktion=Eintrag.Aktion.ABLAGE).exists()
    ablage = client.get(reverse("archive:liste"))
    assert "keine Abweichung in 2 Dateien" in ablage.content.decode()
    assert not warnung(ablage)
    assert not warnung(client.get(reverse("core:start")))


@pytest.mark.django_db(transaction=True)
def test_prueft_ohne_die_datenbank_zu_sperren(client, belege, monkeypatch):
    """Am 01.11.2026 scheiterte die Prüfung im echten Programm zweimal an „database is
    locked“: Sie rechnete die Prüfsummen in einer offenen Transaktion, während eine
    Anfrage schrieb. Gesperrt wird nur noch für das Speichern des Ergebnisses."""
    zustand = pruefung._zustand
    in_transaktion = []

    def zaehlen(datei, sha256):
        in_transaktion.append(connection.in_atomic_block)
        return zustand(datei, sha256)

    monkeypatch.setattr(pruefung, "_zustand", zaehlen)
    pfad(belege[1]).write_bytes(b"anders")
    ergebnis = pruefung.pruefen()

    assert in_transaktion == [False, False]
    assert [b["zustand"] for b in ergebnis.befunde] == [pruefung.VERAENDERT]
    assert Eintrag.objects.filter(aktion=Eintrag.Aktion.ABLAGE).count() == 1
    assert settings.DATABASES["default"]["OPTIONS"]["transaction_mode"] == "IMMEDIATE"


def test_abweichung_gemeldet_protokolliert_und_wieder_in_ordnung(client, belege):
    rechnung, altbeleg = belege
    original = pfad(rechnung).read_bytes()
    pfad(rechnung).write_bytes(original + b"angehaengt")
    pfad(altbeleg).unlink()

    ergebnis = pruefung.pruefen()

    assert [(b["beleg"], b["zustand"], b["neu"]) for b in ergebnis.befunde] == [
        (f"Rechnung {rechnung.nummer}", pruefung.VERAENDERT, True),
        ("Rechnung 1001 (Altprogramm)", pruefung.FEHLT, True),
    ]
    eintraege = Eintrag.objects.filter(aktion=Eintrag.Aktion.ABLAGE).order_by("pk")
    assert [(e.art, e.beschreibung, e.aenderungen) for e in eintraege] == [
        (
            "Rechnung",
            f"Rechnung {rechnung.nummer}",
            [[rechnung.datei, "", "außerhalb von Kontorfreund verändert"]],
        ),
        (
            "Altbeleg",
            "Rechnung 1001",
            [[altbeleg.datei, "", "fehlt oder lässt sich nicht lesen"]],
        ),
    ]
    start = client.get(reverse("core:start")).content.decode()
    assert "2 abgelegte Dateien fehlen oder sind verändert:" in start
    assert f"Rechnung {rechnung.nummer}, Rechnung 1001 (Altprogramm)." in start
    ablage = client.get(reverse("archive:liste")).content.decode()
    assert f"ist verändert, festgestellt am {HEUTE:%d.%m.%Y}" in ablage
    assert "Ohne Datensicherung lässt sich das Original nicht zurückholen" in ablage
    # Seitenleiste
    assert 'title="2 abgelegte Dateien fehlen oder sind verändert"' in ablage
    assert (
        "Abweichung in der Ablage"
        in client.get(reverse("protokoll:liste")).content.decode()
    )

    # Mitarbeiter sehen es auch und sagen dem Inhaber Bescheid.
    anna = Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    mitarbeiter = Client()
    mitarbeiter.force_login(anna)
    assert (
        "dem Inhaber Bescheid"
        in mitarbeiter.get(reverse("archive:liste")).content.decode()
    )

    # Am nächsten Tag noch dasselbe: kein zweiter Eintrag, das Datum bleibt.
    Pruefung.objects.update(zeit=timezone.now() - timedelta(days=1))
    assert pruefung.faellig()
    zweite = pruefung.pruefen()
    assert [(b["neu"], b["seit"]) for b in zweite.befunde] == [
        (False, timezone.localdate().isoformat())
    ] * 2
    assert eintraege.count() == 2

    # Originale zurück: keine Warnung mehr.
    pfad(rechnung).write_bytes(original)
    pfad(altbeleg).write_bytes(b"%PDF-1.4 Rechnung aus dem Altprogramm")
    assert pruefung.pruefen().befunde == []
    assert not warnung(client.get(reverse("core:start")))


def test_jetzt_pruefen(client, belege, inhaber):
    rechnung, _ = belege
    antwort = client.post(reverse("archive:pruefen"), follow=True)
    assert "Geprüft: keine Abweichung in 2 Dateien." in antwort.content.decode()

    pfad(rechnung).unlink()
    antwort = client.post(reverse("archive:pruefen"), follow=True)
    assert "1 abgelegte Datei fehlt oder ist verändert." in antwort.content.decode()
    assert Eintrag.objects.get(aktion=Eintrag.Aktion.ABLAGE).wer == str(inhaber)
    assert client.get(reverse("archive:pruefen")).status_code == 405


def test_nach_anfrage_angestossen(client, anonym, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(pruefung, "bei_bedarf", lambda: aufrufe.append(1))
    # Der Selbsttest ruft nur die Anmeldeseite auf und soll nichts hinterlassen.
    anonym.get(reverse("konten:anmelden"))
    assert aufrufe == []
    client.get(reverse("core:start"))
    assert aufrufe == [1]


def test_befehl_erinnern_prueft_einmal_am_tag(belege):
    assert pruefung.faellig()
    call_command("erinnern")
    assert Pruefung.objects.count() == 1
    assert not pruefung.faellig()
    call_command("erinnern")
    assert Pruefung.objects.count() == 1


def test_telegram_meldet_neue_abweichung_einmal(belege, inhaber, monkeypatch):
    texte = []
    monkeypatch.setattr(
        telegram, "senden", lambda schluessel, chat, text: texte.append(text)
    )
    e = Einstellung.laden()
    e.aktiv = True
    e.bot_schluessel = "123456789:AAHmusterSchluesselFuerTests_0123456789"
    e.bot_name = "muster_buero_bot"
    e.chat = "4711"
    e.empfaenger = inhaber
    e.save()
    rechnung, _ = belege
    pfad(rechnung).unlink()

    pruefung.pruefen()
    nachrichten.erinnern()
    nachrichten.erinnern()

    meldungen = [t for t in texte if "Abgelegte" in t]
    assert meldungen == [
        f"Muster IT: Abgelegte Belege fehlen oder sind verändert: Rechnung {rechnung.nummer}. "
        "Näheres in Kontorfreund unter Ablage."
    ]
    # Am nächsten Tag dieselbe Abweichung: keine neue Nachricht.
    Pruefung.objects.update(zeit=timezone.now() - timedelta(days=1))
    pruefung.pruefen()
    nachrichten.erinnern()
    assert [t for t in texte if "Abgelegte" in t] == meldungen


KENNWORT = "Pferd Batterie Heftklammer"


# Sicherungen brauchen echte Transaktionen der Datenbank.
@pytest.mark.django_db(transaction=True)
def test_originale_aus_der_sicherung_zurueckholen(client, belege):
    rechnung, altbeleg = belege
    sicherung.einrichten(KENNWORT)
    sicherung.sichern()
    original = pfad(rechnung).read_bytes()
    pfad(rechnung).write_bytes(b"gefaelscht")
    pfad(altbeleg).unlink()
    # Die neueste Sicherung enthält schon die Fälschung; das Original kommt aus der älteren.
    sicherung.sichern()
    pruefung.pruefen()
    ablage = client.get(reverse("archive:liste")).content.decode()
    assert "Originale zurückholen" in ablage

    antwort = client.post(reverse("archive:zurueckholen"), follow=True)

    assert pfad(rechnung).read_bytes() == original
    assert pfad(altbeleg).read_bytes() == b"%PDF-1.4 Rechnung aus dem Altprogramm"
    beiseite = list((Path(settings.DATA_DIR) / "abweichungen").rglob("*.pdf"))
    assert [p.read_bytes() for p in beiseite] == [b"gefaelscht"]
    assert Pruefung.letzte().befunde == []
    text = antwort.content.decode()
    assert "2 Dateien aus der Datensicherung zurückgeholt." in text
    assert "Was verändert war, liegt jetzt unter" in text
    eintraege = Eintrag.objects.filter(aktion=Eintrag.Aktion.ZURUECK).order_by("pk")
    assert [(e.beschreibung, e.aenderungen[0][0]) for e in eintraege] == [
        (f"Rechnung {rechnung.nummer}", rechnung.datei),
        ("Rechnung 1001", altbeleg.datei),
    ]
    assert eintraege[0].aenderungen[0][2].startswith("aus der Sicherung vom ")


@pytest.mark.django_db(transaction=True)
def test_kein_passendes_original(client, belege):
    rechnung, _ = belege
    sicherung.einrichten(KENNWORT)
    sicherung.sichern()  # mit dem Original, aber unter dem früheren Kennwort
    sicherung.einrichten("Neues Kennwort für die Sicherung")
    pfad(rechnung).write_bytes(b"gefaelscht")
    sicherung.sichern()  # nur die Fälschung
    pruefung.pruefen()

    antwort = client.post(reverse("archive:zurueckholen"), follow=True)

    assert pfad(rechnung).read_bytes() == b"gefaelscht"
    assert not (Path(settings.DATA_DIR) / "abweichungen").exists()
    assert len(Pruefung.letzte().befunde) == 1
    assert "Für 1 Datei fand sich in den Sicherungen kein unverändertes Original." in (
        antwort.content.decode()
    )
    assert not Eintrag.objects.filter(aktion=Eintrag.Aktion.ZURUECK).exists()


def test_zurueckholen_nur_fuer_den_inhaber(belege):
    anna = Benutzer.objects.create_user("anna@muster.test", name="Anna Beispiel")
    mitarbeiter = Client()
    mitarbeiter.force_login(anna)
    assert mitarbeiter.post(reverse("archive:zurueckholen")).status_code == 403
