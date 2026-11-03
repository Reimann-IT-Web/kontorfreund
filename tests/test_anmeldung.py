"""Anmeldung, Rollen und Zwei-Faktor-Anmeldung (Spezifikation K-5) – mit erfundenen Daten."""

import base64
import time
from datetime import timedelta
from io import StringIO

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.urls import reverse
from django.utils import timezone

from konten import totp
from konten.kennwort import Kennwortregeln
from konten.models import Benutzer

pytestmark = pytest.mark.django_db

KENNWORT = "Tannenbaum Fahrrad Wolke"


@pytest.fixture
def mitarbeiterin():
    return Benutzer.objects.create_user(
        "anna@muster.test", KENNWORT, name="Anna Beispiel"
    )


def anmelden(client, email="anna@muster.test", kennwort=KENNWORT, **mehr):
    return client.post(
        reverse("konten:anmelden"), {"email": email, "kennwort": kennwort, **mehr}
    )


def test_ohne_anmeldung_geht_es_zur_anmeldung(anonym, inhaber):
    antwort = anonym.get(reverse("invoicing:liste"))

    assert antwort.status_code == 302
    assert antwort.url == f"{reverse('konten:anmelden')}?next=/rechnungen/"
    assert anonym.get(antwort.url).status_code == 200


def test_erster_start_legt_den_inhaber_an(anonym):
    assert anonym.get(reverse("konten:anmelden")).url == reverse("konten:einrichten")
    daten = {"name": "Max Muster", "email": "Max@Muster.test"}

    schwach = anonym.post(
        reverse("konten:einrichten"),
        {**daten, "kennwort": "passwort1234", "wiederholung": "passwort1234"},
    )
    assert "Datenleck" in schwach.content.decode()
    assert not Benutzer.objects.exists()

    anonym.post(
        reverse("konten:einrichten"),
        {**daten, "kennwort": KENNWORT, "wiederholung": KENNWORT},
    )

    benutzer = Benutzer.objects.get()
    assert benutzer.ist_inhaber and benutzer.email == "max@muster.test"
    # In der Datenbank steht nur der Argon2-Hash.
    assert benutzer.password.startswith("argon2$") and KENNWORT not in benutzer.password
    assert anonym.get(reverse("core:start")).status_code == 200
    # Die Einrichtung gibt es nur einmal.
    anonym.logout()
    assert anonym.get(reverse("konten:einrichten")).url == reverse("konten:anmelden")


@pytest.mark.parametrize(
    "kennwort",
    ["passwort1234", "Passwort!2026", "Kennwort12345", "123456789012", "kurz123"],
)
def test_schwache_kennwoerter_abgelehnt(kennwort):
    with pytest.raises(ValidationError):
        Kennwortregeln().validate(kennwort)


def test_anmelden_mit_weiterleitung(anonym, mitarbeiterin):
    antwort = anmelden(anonym, email="ANNA@muster.test", next="/rechnungen/")

    assert antwort.url == "/rechnungen/"
    assert anonym.get("/rechnungen/").status_code == 200
    # Fremde Ziele werden ignoriert.
    anonym.logout()
    assert anmelden(anonym, next="https://boese.test/").url == reverse("core:start")


def test_nach_fuenf_fehlversuchen_gesperrt(anonym, mitarbeiterin):
    for _ in range(4):
        antwort = anmelden(anonym, kennwort="falsch falsch falsch")
        assert "Kennwort stimmt nicht" in antwort.content.decode()

    antwort = anmelden(anonym, kennwort="falsch falsch falsch")
    assert "ist die Anmeldung für dieses Konto" in antwort.content.decode()
    # Auch das richtige Kennwort hilft während der Sperre nicht.
    gesperrt = anmelden(anonym)
    assert gesperrt.status_code == 200 and "gesperrt" in gesperrt.content.decode()

    Benutzer.objects.filter(pk=mitarbeiterin.pk).update(
        gesperrt_bis=timezone.now() - timedelta(seconds=1)
    )
    assert anmelden(anonym).status_code == 302


def test_mitarbeiter_sieht_keine_einstellungen(client, mitarbeiterin):
    client.force_login(mitarbeiterin)

    start = client.get(reverse("core:start")).content.decode()
    assert "Guten Tag, Anna Beispiel" in start
    assert f'href="{reverse("core:einstellungen")}"' not in start
    assert f'href="{reverse("backups:uebersicht")}"' not in start
    for adresse in (
        reverse("core:einstellungen"),
        reverse("backups:uebersicht"),
        reverse("konten:benutzer"),
    ):
        assert client.get(adresse).status_code == 403
    assert client.get(reverse("invoicing:liste")).status_code == 200


def test_inhaber_verwaltet_benutzer(client, inhaber):
    seite = client.get(reverse("konten:benutzer")).content.decode()
    assert '<option value="mitarbeiter" selected>' in seite
    client.post(
        reverse("konten:benutzer"),
        {
            "name": "Anna Beispiel",
            "email": "anna@muster.test",
            "rolle": "mitarbeiter",
            "kennwort": KENNWORT,
            "wiederholung": KENNWORT,
        },
    )
    anna = Benutzer.objects.get(email="anna@muster.test")
    assert anna.rolle == Benutzer.Rolle.MITARBEITER and anna.check_password(KENNWORT)
    seite = reverse("konten:benutzer_bearbeiten", args=[anna.pk])

    client.post(
        seite,
        {
            "aktion": "kennwort",
            "kennwort": "Neue Wolke Fahrrad",
            "wiederholung": "Neue Wolke Fahrrad",
        },
    )
    client.post(seite, {"aktion": "rolle", "rolle": "inhaber"})
    client.post(seite, {"aktion": "zugang"})

    anna.refresh_from_db()
    assert anna.check_password("Neue Wolke Fahrrad")
    assert anna.ist_inhaber and not anna.is_active
    # Sich selbst kann der Inhaber weder herabstufen noch aussperren.
    eigene = reverse("konten:benutzer_bearbeiten", args=[inhaber.pk])
    client.post(eigene, {"aktion": "rolle", "rolle": "mitarbeiter"})
    client.post(eigene, {"aktion": "zugang"})
    inhaber.refresh_from_db()
    assert inhaber.ist_inhaber and inhaber.is_active


def test_totp_nach_rfc_6238():
    geheimnis = base64.b32encode(b"12345678901234567890").decode()

    assert totp.code(geheimnis, 1) == "287082"
    assert totp.pruefen(geheimnis, "287 082", jetzt=59) == 1
    assert totp.pruefen(geheimnis, "287082", zuletzt=1, jetzt=59) is None


def test_zwei_faktor_einrichten_und_anmelden(client, anonym, mitarbeiterin):
    client.force_login(mitarbeiterin)
    client.get(reverse("konten:zwei_faktor"))
    geheimnis = client.session["zwei_faktor_geheimnis"]
    schritt = int(time.time() // totp.SCHRITT)
    client.post(
        reverse("konten:zwei_faktor"),
        {"kennwort": KENNWORT, "code": totp.code(geheimnis, schritt)},
    )
    mitarbeiterin.refresh_from_db()
    assert mitarbeiterin.totp_geheimnis == geheimnis

    assert anmelden(anonym).url == reverse("konten:code")
    assert anonym.get(reverse("core:start")).status_code == 302  # noch nicht angemeldet
    falsch = anonym.post(reverse("konten:code"), {"code": "000000"})
    assert "Der Code stimmt nicht" in falsch.content.decode()

    richtig = anonym.post(
        reverse("konten:code"), {"code": totp.code(geheimnis, schritt + 1)}
    )
    assert richtig.url == reverse("core:start")
    assert anonym.get(reverse("core:start")).status_code == 200


def test_zwei_faktor_pflicht_fuer_inhaber_im_netzwerk(client, mitarbeiterin, settings):
    settings.NETZWERK = True

    assert client.get(reverse("core:start")).url == reverse("konten:zwei_faktor")
    assert client.get(reverse("konten:zwei_faktor")).status_code == 200
    client.force_login(mitarbeiterin)
    assert client.get(reverse("core:start")).status_code == 200


def test_abmelden_und_automatisch_nach_acht_stunden(client):
    assert (
        settings.SESSION_COOKIE_AGE == 8 * 3600 and settings.SESSION_SAVE_EVERY_REQUEST
    )

    client.post(reverse("konten:abmelden"))

    assert client.get(reverse("core:start")).status_code == 302


def test_notfall_entsperren(mitarbeiterin):
    mitarbeiterin.totp_geheimnis = totp.neues_geheimnis()
    mitarbeiterin.save()
    for _ in range(5):
        mitarbeiterin.fehlversuch()
    assert mitarbeiterin.gesperrt

    ausgabe = StringIO()
    call_command("entsperren", "ANNA@muster.test", stdout=ausgabe)
    anna = Benutzer.objects.get(pk=mitarbeiterin.pk)
    assert not anna.gesperrt and anna.zwei_faktor
    assert "Sperre für anna@muster.test ist aufgehoben" in ausgabe.getvalue()

    call_command("entsperren", "anna@muster.test", "--ohne-zwei-faktor", stdout=ausgabe)
    assert not Benutzer.objects.get(pk=mitarbeiterin.pk).zwei_faktor
    with pytest.raises(CommandError, match="Kein Konto"):
        call_command("entsperren", "niemand@muster.test")
