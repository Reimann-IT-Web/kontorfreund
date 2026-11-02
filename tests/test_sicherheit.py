"""Maßnahmen aus der Prüfung nach OWASP ASVS (docs/sicherheit.md) – mit erfundenen Daten."""

import logging
import re
import time

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from benachrichtigungen import telegram
from config.fehlerprotokoll import MitZeitzone
from contacts.models import Kontakt
from core.models import Firmendaten
from historie.models import Datei
from konten import sitzungen, totp
from konten.kennwort import Kennwortregeln
from konten.models import Benutzer
from protokoll.models import Eintrag

pytestmark = pytest.mark.django_db

KENNWORT = "Tannenbaum Fahrrad Wolke"
FIREFOX = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
)
SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


@pytest.fixture
def anna():
    return Benutzer.objects.create_user("anna@muster.test", KENNWORT, name="Anna Korn")


def angemeldet(benutzer, kennwort=KENNWORT, geraet=FIREFOX):
    browser = Client(HTTP_USER_AGENT=geraet)
    antwort = browser.post(
        reverse("konten:anmelden"), {"email": benutzer.email, "kennwort": kennwort}
    )
    assert antwort.status_code == 302, antwort.content.decode()
    return browser


def letzter(aktion):
    return Eintrag.objects.filter(aktion=aktion).first()


# ---------- Kennwörter (ASVS 6.2) ----------


def test_kennwoerter_aus_datenlecks_und_aus_namen(anna):
    Firmendaten.objects.update_or_create(
        pk=1, defaults={"name": "Bäckerei Korn", "inhaber": "Max Muster"}
    )
    regeln = Kennwortregeln()
    for schwach, grund in [
        ("Sonnenschein1", "password_breached"),
        ("Korn-Bäckerei-2026!", "password_too_similar"),
        ("MusterKorn12345", "password_too_similar"),
        ("Kontorfreund 2026!", "password_too_similar"),
        ("adminadminadmin", "password_too_common"),
        ("Pass-wort-2026!", "password_too_common"),
    ]:
        with pytest.raises(ValidationError) as fehler:
            regeln.validate(schwach, anna)
        assert fehler.value.code == grund, schwach
    # Lang und beliebig zusammengesetzt, auch mit einem Namen darin.
    regeln.validate("Korn Laterne Heftklammer Wolke", anna)
    regeln.validate("x" * 40 + "Ü!" + "y" * 40, anna)


def test_neue_konten_pruefen_ihren_eigenen_namen(client):
    antwort = client.post(
        reverse("konten:benutzer"),
        {
            "name": "Lena Weidenbach",
            "email": "lena@muster.test",
            "rolle": "mitarbeiter",
            "kennwort": "Weidenbach-2026!",
            "wiederholung": "Weidenbach-2026!",
        },
    )
    assert "fast nur aus Ihrem Namen" in antwort.content.decode()
    assert not Benutzer.objects.filter(email="lena@muster.test").exists()


# ---------- Erstes Kennwort (ASVS 6.4.1) ----------


def test_erstes_kennwort_wird_bei_der_anmeldung_ersetzt(client):
    client.post(
        reverse("konten:benutzer"),
        {
            "name": "Anna Korn",
            "email": "anna@muster.test",
            "rolle": "mitarbeiter",
            "kennwort": KENNWORT,
            "wiederholung": KENNWORT,
        },
    )
    anna = Benutzer.objects.get(email="anna@muster.test")
    assert anna.kennwort_vorlaeufig

    browser = angemeldet(anna)
    assert browser.get(reverse("core:start")).url == reverse("konten:kennwort")
    assert browser.get(reverse("contacts:liste")).url == reverse("konten:kennwort")
    gleich = browser.post(
        reverse("konten:kennwort"),
        {"bisher": KENNWORT, "kennwort": KENNWORT, "wiederholung": KENNWORT},
    )
    assert "anderes als das bisherige" in gleich.content.decode()

    neu = "Laterne Wolke Fahrrad 7"
    antwort = browser.post(
        reverse("konten:kennwort"),
        {"bisher": KENNWORT, "kennwort": neu, "wiederholung": neu},
    )
    assert antwort.url == reverse("core:start")
    anna.refresh_from_db()
    assert not anna.kennwort_vorlaeufig and anna.check_password(neu)
    assert browser.get(reverse("core:start")).status_code == 200

    # Setzt der Inhaber es neu, wählt Anna danach wieder ein eigenes.
    client.post(
        reverse("konten:benutzer_bearbeiten", args=[anna.pk]),
        {"aktion": "kennwort", "kennwort": KENNWORT, "wiederholung": KENNWORT},
    )
    anna.refresh_from_db()
    assert anna.kennwort_vorlaeufig
    assert browser.get(reverse("core:start")).status_code == 302  # abgemeldet


def test_pruefer_waehlt_sein_kennwort_selbst(anna):
    anna.rolle = Benutzer.Rolle.PRUEFER
    anna.kennwort_vorlaeufig = True
    anna.zugang_bis = anna.erstellt.date()
    anna.pruefung_von = anna.pruefung_bis = 2025
    anna.save()

    browser = angemeldet(anna)
    assert browser.get(reverse("datenzugriff:start")).url == reverse("konten:kennwort")
    assert browser.get(reverse("konten:kennwort")).status_code == 200
    neu = "Laterne Wolke Fahrrad 7"
    browser.post(
        reverse("konten:kennwort"),
        {"bisher": KENNWORT, "kennwort": neu, "wiederholung": neu},
    )
    assert browser.get(reverse("core:start")).url == reverse("datenzugriff:start")
    assert browser.get(reverse("datenzugriff:start")).status_code == 200


# ---------- Sitzungen (ASVS 7.3 bis 7.5) ----------


def test_hoechstens_zwoelf_stunden_angemeldet(anna):
    browser = angemeldet(anna)
    sitzung = browser.session
    sitzung[sitzungen.SEIT] = time.time() - sitzungen.HOECHSTENS - 1
    sitzung.save()

    antwort = browser.get(reverse("contacts:liste"))
    assert antwort.url.startswith(reverse("konten:anmelden"))
    assert browser.get(reverse("core:start")).status_code == 302
    assert letzter(Eintrag.Aktion.ABMELDUNG).beschreibung == "nach 12 Stunden"


def test_geraete_ansehen_und_abmelden(anna):
    hier = angemeldet(anna)
    telefon = angemeldet(anna, geraet=SAFARI)

    seite = hier.get(reverse("konten:konto")).content.decode()
    assert "Firefox unter Windows" in seite and "Safari unter iPhone" in seite
    assert "dieses Gerät" in seite

    for _ in range(4):
        hier.post(reverse("konten:geraete_abmelden"), {"kennwort": "falsch"})
    assert telefon.get(reverse("core:start")).status_code == 200
    assert letzter(Eintrag.Aktion.FEHLVERSUCH).beschreibung.startswith("Kennwort zum")

    hier.post(reverse("konten:geraete_abmelden"), {"kennwort": KENNWORT})
    assert telefon.get(reverse("core:start")).status_code == 302
    assert hier.get(reverse("core:start")).status_code == 200
    assert letzter(Eintrag.Aktion.ABMELDUNG).beschreibung == "auf anderen Geräten (1)"


def test_falsches_kennwort_beim_bestaetigen_sperrt(anna):
    browser = angemeldet(anna)
    for _ in range(5):
        antwort = browser.post(
            reverse("konten:konto"),
            {"bisher": "falsch", "kennwort": "x" * 20, "wiederholung": "x" * 20},
        )
    assert antwort.url == reverse("konten:anmelden")
    anna.refresh_from_db()
    assert anna.gesperrt
    assert browser.get(reverse("core:start")).status_code == 302


def test_zwei_faktor_aendern_beendet_andere_sitzungen(anna):
    hier, dort = angemeldet(anna), angemeldet(anna, geraet=SAFARI)
    hier.get(reverse("konten:zwei_faktor"))
    geheimnis = hier.session["zwei_faktor_geheimnis"]
    code = totp.code(geheimnis, int(time.time() // totp.SCHRITT))

    ohne = hier.post(reverse("konten:zwei_faktor"), {"code": code})
    assert ohne.status_code == 200
    hier.post(reverse("konten:zwei_faktor"), {"kennwort": KENNWORT, "code": code})
    anna.refresh_from_db()
    assert anna.zwei_faktor
    assert hier.get(reverse("core:start")).status_code == 200
    assert dort.get(reverse("core:start")).status_code == 302
    eintrag = letzter(Eintrag.Aktion.GEAENDERT)
    assert eintrag.aenderungen == [["Zwei-Faktor-Anmeldung", "aus", "ein"]]


def test_inhaber_meldet_einen_benutzer_ab(client, anna):
    browser = angemeldet(anna)
    client.post(
        reverse("konten:benutzer_bearbeiten", args=[anna.pk]), {"aktion": "abmelden"}
    )
    assert browser.get(reverse("core:start")).status_code == 302
    assert client.get(reverse("core:start")).status_code == 200
    assert "vom Inhaber" in letzter(Eintrag.Aktion.ABMELDUNG).beschreibung


def test_abmelden_steht_im_protokoll(anna):
    browser = angemeldet(anna)
    browser.post(reverse("konten:abmelden"))
    eintrag = letzter(Eintrag.Aktion.ABMELDUNG)
    assert (eintrag.benutzer_id, eintrag.beschreibung) == (anna.pk, "")


# ---------- Antworten (ASVS 3.3, 3.4, 13.4, 14.3) ----------


def test_kopfzeilen_und_cookies(anna):
    browser = angemeldet(anna)
    assert browser.cookies["csrftoken"]["httponly"]
    assert browser.cookies["sessionid"]["httponly"]
    seite = browser.get(reverse("contacts:liste"))
    assert "no-store" in seite["Cache-Control"]
    assert "base-uri 'none'" in seite["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in seite["Content-Security-Policy"]
    assert seite["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("methode", ["TRACE", "PUT", "DELETE", "OPTIONS"])
def test_nur_get_und_post(client, methode):
    antwort = client.generic(methode, reverse("contacts:liste"))
    assert antwort.status_code == 405
    assert antwort["Allow"] == "GET, HEAD, POST"


# ---------- Verweigert und Fehler (ASVS 16) ----------


def test_verweigerter_zugriff_steht_im_protokoll(anna):
    browser = angemeldet(anna)
    assert browser.get(reverse("konten:benutzer")).status_code == 403
    eintrag = letzter(Eintrag.Aktion.VERWEIGERT)
    assert eintrag.benutzer_id == anna.pk
    assert eintrag.beschreibung.startswith("GET /konto/benutzer/")


def test_formular_ohne_schluessel(anna):
    browser = Client(enforce_csrf_checks=True)
    browser.force_login(anna)
    antwort = browser.post(reverse("konten:abmelden"))
    assert antwort.status_code == 403
    assert "Formular abgelehnt" in antwort.content.decode()
    assert "Formular abgelehnt" in letzter(Eintrag.Aktion.VERWEIGERT).beschreibung
    assert browser.get(reverse("core:start")).status_code == 200  # nicht abgemeldet


def test_fehlerprotokoll_mit_zeitzone():
    eintrag = logging.LogRecord("x", logging.ERROR, "", 0, "kaputt", None, None)
    zeile = MitZeitzone("%(asctime)s %(message)s").format(eintrag)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d kaputt", zeile)


# ---------- Dateien und Verbindungen (ASVS 5.2, 15.3) ----------


def test_vorschau_nur_wenn_der_inhalt_passt(client):
    kunde = Kontakt.objects.create(firmenname="Bäckerei Korn", plz="55116", ort="Mainz")
    for name, inhalt, typ in [
        ("Foto.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png"),
        ("Foto2.png", b"<svg onload=alert(1)>", "application/octet-stream"),
        ("Brief.pdf", b"<html>kein PDF</html>", "application/octet-stream"),
    ]:
        client.post(
            reverse("historie:hochladen", args=[kunde.pk]),
            {"dateien": [SimpleUploadedFile(name, inhalt)]},
        )
        antwort = client.get(
            reverse("historie:datei", args=[Datei.objects.latest("pk").pk])
        )
        assert antwort["Content-Type"] == typ, name


def test_telegram_folgt_keiner_umleitung():
    oeffner = telegram._oeffnen.__self__
    assert any(isinstance(h, telegram._OhneUmleitung) for h in oeffner.handlers)
    assert telegram._OhneUmleitung().redirect_request() is None
