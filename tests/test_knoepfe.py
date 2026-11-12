"""Knöpfe in Telegram: senden, mahnen, als bezahlt buchen – mit erfundenen Daten."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.mail.backends import locmem
from django.urls import reverse
from django.utils import timezone

from benachrichtigungen import knoepfe, nachrichten, telegram
from benachrichtigungen.models import Einstellung, Gemeldet
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import versand
from invoicing.models import Position, Rechnung
from protokoll.models import Eintrag
from vertraege import abrechnen
from vertraege.models import Vertrag
from zahlungen.models import Mahnung, Zahlung

pytestmark = pytest.mark.django_db

HEUTE = date.today()
CHAT = "4711"


def um(stunde, tag=HEUTE):
    return timezone.make_aware(datetime.combine(tag, time(stunde)))


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
    f.iban = "DE02120300000000202051"
    f.mail_server = "smtp.muster.test"
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn",
        strasse="Markt 3",
        plz="55116",
        ort="Mainz",
        email="buchhaltung@baeckerei.test",
    )


@pytest.fixture
def telegramm(monkeypatch, inhaber, firma):
    """Verbundener Bot; merkt sich gesendete und geänderte Nachrichten."""
    e = Einstellung.laden()
    e.aktiv, e.bot_schluessel, e.chat, e.empfaenger = True, "1:abc", CHAT, inhaber
    e.save()
    log = {"gesendet": [], "geaendert": [], "druecke": []}
    monkeypatch.setattr(
        telegram,
        "senden",
        lambda s, c, text, knoepfe=None: log["gesendet"].append((text, knoepfe)),
    )
    monkeypatch.setattr(
        telegram, "aendern", lambda s, c, n, text: log["geaendert"].append(text)
    )
    monkeypatch.setattr(telegram, "antworten", lambda s, frage, text="": None)
    monkeypatch.setattr(versand, "SmtpVersand", lambda **_: locmem.EmailBackend())

    def neuigkeiten(schluessel, ab):
        return [d for d in log["druecke"] if d["update_id"] >= ab]

    monkeypatch.setattr(telegram, "neuigkeiten", neuigkeiten)
    return log


def druecken(log, daten, chat=CHAT, tag=HEUTE):
    """Knopfdruck, ausgewertet in der nächsten Runde."""
    log["druecke"].append(
        {
            "update_id": 100 + len(log["druecke"]),
            "callback_query": {
                "id": "q",
                "from": {"id": int(chat)},
                "message": {"message_id": 7, "chat": {"id": int(chat)}, "text": "…"},
                "data": daten,
            },
        }
    )
    nachrichten.erinnern(um(6, tag))  # vor der Übersicht: nur die Knöpfe
    return log["geaendert"][-1] if log["geaendert"] else None


def ueberfaellig(client, kunde, tage=30):
    """Rechnung über 160 €, seit 16 Tagen fällig: Die Zahlungserinnerung ist dran."""
    datum = (HEUTE - timedelta(days=tage)).isoformat()
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": datum,
            "leistung_von": datum,
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
    return Rechnung.objects.get(kontakt=kunde)


def daten(knopfliste, titel):
    return dict(knopfliste)[titel]


def test_mahnen_mit_einem_tipp(client, kunde, telegramm):
    rechnung = ueberfaellig(client, kunde)
    nachrichten.erinnern(um(8))

    ((text, knopfliste),) = telegramm["gesendet"]
    assert text == (
        f"Muster IT: Zu mahnen: Rechnung {rechnung.nummer} 160,00\xa0€ "
        "(Zahlungserinnerung)"
    )
    assert [t for t, _ in knopfliste] == ["Senden", "Ist bezahlt", "Später"]
    assert all(len(d.encode()) <= 64 for _, d in knopfliste)

    antwort = druecken(telegramm, daten(knopfliste, "Senden"))

    mahnung = Mahnung.objects.get()
    assert mahnung.stufe == 1 and mahnung.datum == HEUTE
    (nachricht,) = mail.outbox
    assert nachricht.to == ["buchhaltung@baeckerei.test"]
    assert nachricht.attachments[0].filename.startswith("Zahlungserinnerung")
    assert antwort.endswith(
        f"✓ Zahlungserinnerung zu Rechnung {rechnung.nummer} über 160,00\xa0€ gesendet."
    )
    # Keine Namen und Adressen an Telegram.
    assert "Korn" not in antwort and "baeckerei" not in antwort
    assert Einstellung.laden().gelesen_bis == 101

    # Ein zweiter Druck auf denselben Knopf verschickt nichts noch einmal.
    assert druecken(telegramm, daten(knopfliste, "Senden")).endswith(
        "Schon erledigt: Diese Stufe ist nicht mehr fällig."
    )
    assert Mahnung.objects.count() == 1 and len(mail.outbox) == 1


def test_ist_bezahlt_bucht_den_offenen_betrag(client, kunde, telegramm):
    rechnung = ueberfaellig(client, kunde)
    nachrichten.erinnern(um(8))
    ((_, knopfliste),) = telegramm["gesendet"]

    antwort = druecken(telegramm, daten(knopfliste, "Ist bezahlt"))

    zahlung = Zahlung.objects.get()
    assert (zahlung.rechnung, zahlung.betrag, zahlung.datum) == (
        rechnung,
        Decimal("160.00"),
        HEUTE,
    )
    assert "✓ Zahlung über 160,00\xa0€" in antwort and "mit Datum von heute" in antwort
    rechnung.refresh_from_db()
    assert rechnung.offen == 0


def test_spaeter_kommt_morgen_wieder(client, kunde, telegramm):
    ueberfaellig(client, kunde)
    nachrichten.erinnern(um(8))
    ((_, knopfliste),) = telegramm["gesendet"]

    assert druecken(telegramm, daten(knopfliste, "Später")).endswith(
        "Kommt morgen wieder in der Übersicht."
    )
    assert not Mahnung.objects.exists()
    nachrichten.erinnern(um(9))  # heute nicht noch einmal
    assert len(telegramm["gesendet"]) == 1

    nachrichten.erinnern(um(8, HEUTE + timedelta(days=1)))
    assert len(telegramm["gesendet"]) == 2
    assert "Zu mahnen" in telegramm["gesendet"][-1][0]


def test_entwurf_aus_vertrag_festschreiben_und_senden(kunde, telegramm, inhaber):
    vertrag = Vertrag.objects.create(
        bezeichnung="Wartung Server",
        kontakt=kunde,
        beginn=HEUTE,
        rabatt_prozent=Decimal("8"),
        zahlungsziel=0,
    )
    vertrag.positionen.create(nr=1, bezeichnung="Wartung", menge=12, preis=52)
    (entwurf,) = abrechnen.faellige(HEUTE)
    Rechnung.objects.filter(pk=entwurf.pk).update(datum=HEUTE - timedelta(days=3))

    nachrichten.erinnern(um(8))
    ((text, knopfliste),) = telegramm["gesendet"]
    assert (
        text == "Muster IT: Neuer Entwurf aus dem Vertrag „Wartung Server“: 574,08\xa0€"
    )
    assert [t for t, _ in knopfliste] == ["Festschreiben und senden", "Später"]

    antwort = druecken(telegramm, daten(knopfliste, "Festschreiben und senden"))

    entwurf.refresh_from_db()
    assert not entwurf.ist_entwurf
    assert entwurf.datum == HEUTE  # wie beim Öffnen im Editor
    assert antwort.endswith(f"✓ Rechnung {entwurf.nummer} über 574,08\xa0€ gesendet.")
    (nachricht,) = mail.outbox
    assert nachricht.attachments[0].filename == f"Rechnung-{entwurf.nummer}.pdf"
    eintrag = Eintrag.objects.filter(objekt_id=str(entwurf.pk)).latest("pk")
    assert eintrag.benutzer_id == inhaber.pk


def test_fehlende_angaben_werden_genannt(kunde, telegramm):
    kunde.strasse = ""
    kunde.save()
    rechnung = Rechnung.objects.create(kontakt=kunde, leistung_von=HEUTE)
    Position.objects.create(rechnung=rechnung, nr=1, bezeichnung="Wartung", preis=10)

    antwort = knoepfe.ausfuehren(["e", str(rechnung.pk)])

    assert antwort.startswith(
        "Nicht festgeschrieben, es fehlt: Empfänger mit Anschrift"
    )
    rechnung.refresh_from_db()
    assert rechnung.ist_entwurf


@pytest.mark.parametrize("fremd", ["chat", "signatur"])
def test_fremder_oder_veraenderter_knopf_bewirkt_nichts(
    client, kunde, telegramm, fremd
):
    rechnung = ueberfaellig(client, kunde)
    nachrichten.erinnern(um(8))
    ((_, knopfliste),) = telegramm["gesendet"]
    gueltig = daten(knopfliste, "Ist bezahlt")

    if fremd == "chat":
        druecken(telegramm, gueltig, chat="999")
    else:
        anders = gueltig.replace(f"b:{rechnung.pk}:", f"b:{rechnung.pk + 1}:")
        druecken(telegramm, anders)

    assert not Zahlung.objects.exists()
    assert telegramm["geaendert"] == []


def test_ohne_adresse_beim_kunden_kein_senden(client, kunde, telegramm):
    kunde.email = ""
    kunde.save()
    ueberfaellig(client, kunde)

    nachrichten.erinnern(um(8))

    ((text, knopfliste),) = telegramm["gesendet"]
    assert "fehlt die E-Mail-Adresse" in text
    assert [t for t, _ in knopfliste] == ["Ist bezahlt", "Später"]


def test_alte_nachricht_bekommt_die_antwort_neu(client, kunde, telegramm, monkeypatch):
    ueberfaellig(client, kunde)
    nachrichten.erinnern(um(8))
    ((_, knopfliste),) = telegramm["gesendet"]

    def zu_alt(*args):
        raise telegram.Fehler("message can't be edited")

    monkeypatch.setattr(telegram, "aendern", zu_alt)
    druecken(telegramm, daten(knopfliste, "Später"))

    assert telegramm["gesendet"][-1][0].endswith(
        "Kommt morgen wieder in der Übersicht."
    )


def test_gemeldet_bleibt_fuer_die_uebersicht(client, kunde, telegramm):
    rechnung = ueberfaellig(client, kunde)
    nachrichten.erinnern(um(8))
    assert Gemeldet.objects.filter(
        anlass="mahnstufe", schluessel=f"{rechnung.pk}:1"
    ).exists()
