"""Datensicherung: verschlüsseln, aufbewahren, wiederherstellen – mit erfundenen Daten."""

import os
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.sql import emit_pre_migrate_signal
from django.db.migrations.recorder import MigrationRecorder
from django.urls import reverse
from django.utils import timezone

from backups import sicherung
from contacts.models import Kontakt

KENNWORT = "Pferd Batterie Heftklammer"

# Sicherung und Wiederherstellung brauchen echte Transaktionen der Datenbank.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def beleg(settings):
    """Eine Adresse und ein abgelegter Beleg."""
    Kontakt.objects.create(firmenname="Muster Bäckerei GmbH", ort="Mainz")
    pfad = settings.DATA_DIR / "archiv" / "rechnungen" / "2026" / "Rechnung-260001.pdf"
    pfad.parent.mkdir(parents=True)
    pfad.write_bytes(b"%PDF-1.7 Muster Baeckerei")
    return pfad


@pytest.fixture
def eingerichtet():
    sicherung.einrichten(KENNWORT)


def gesichert(settings):
    return sorted((settings.DATA_DIR / "sicherung").glob("*.sicherung"))


def test_sichern_und_wiederherstellen(beleg, eingerichtet, settings):
    datei, hinweis = sicherung.sichern()

    assert hinweis == ""
    roh = datei.read_bytes()
    assert b"Muster" not in roh and b"%PDF" not in roh
    # Datum und Umfang sind ohne Kennwort lesbar, für die Vorschau.
    kopf = sicherung.kopf_lesen(datei)
    assert kopf["anlass"] == "manuell"
    assert kopf["umfang"] == {
        "adressen": 1,
        "rechnungen": 0,
        "entwuerfe": 0,
        "altbelege": 0,
        "dateien": 1,
    }
    assert sicherung.zustand()["zuletzt"] is not None

    Kontakt.objects.all().delete()
    beleg.write_bytes(b"geaendert")
    (beleg.parent / "neu.pdf").write_bytes(b"neu")

    _, vorher = sicherung.wiederherstellen(datei, KENNWORT)

    assert Kontakt.objects.get().firmenname == "Muster Bäckerei GmbH"
    assert beleg.read_bytes() == b"%PDF-1.7 Muster Baeckerei"
    assert not (beleg.parent / "neu.pdf").exists()
    assert sicherung.kopf_lesen(vorher)["anlass"] == "wiederherstellung"
    assert sicherung.kopf_lesen(vorher)["umfang"]["adressen"] == 0
    assert not (settings.DATA_DIR / "archiv.neu").exists()
    assert not (settings.DATA_DIR / "archiv.alt").exists()


def test_falsches_kennwort_und_beschaedigte_datei(beleg, eingerichtet, settings):
    # Größer als ein Block, damit auch spätere Blöcke geprüft werden.
    (beleg.parent / "gross.pdf").write_bytes(os.urandom(3 << 19))
    datei, _ = sicherung.sichern()

    with pytest.raises(sicherung.FalschesKennwort):
        sicherung.wiederherstellen(datei, "ein ganz anderes Kennwort")
    assert gesichert(settings) == [datei]

    roh = bytearray(datei.read_bytes())
    roh[-100] ^= 1
    datei.write_bytes(roh)
    with pytest.raises(sicherung.SicherungFehler, match="beschädigt"):
        sicherung.wiederherstellen(datei, KENNWORT)

    datei.write_bytes(roh[:-1000])
    with pytest.raises(sicherung.SicherungFehler, match="beschädigt"):
        sicherung.wiederherstellen(datei, KENNWORT)
    assert Kontakt.objects.count() == 1
    assert beleg.read_bytes() == b"%PDF-1.7 Muster Baeckerei"


def test_sicherung_aus_neuerer_version(beleg, eingerichtet, monkeypatch):
    echt = MigrationRecorder.applied_migrations
    monkeypatch.setattr(
        MigrationRecorder,
        "applied_migrations",
        lambda self: {**echt(self), ("invoicing", "9999_zukunft"): None},
    )
    datei, _ = sicherung.sichern()
    monkeypatch.undo()

    with pytest.raises(sicherung.SicherungFehler, match="neueren Version"):
        sicherung.wiederherstellen(datei, KENNWORT)
    assert Kontakt.objects.count() == 1


def test_aufbewahren_und_zweiter_speicherort(beleg, eingerichtet, settings, tmp_path):
    usb = tmp_path / "usb"
    usb.mkdir()
    sicherung.einstellen(str(usb), 3)

    for _ in range(4):
        sicherung.sichern()

    hier = [p.name for p in gesichert(settings)]
    assert len(hier) == 3
    assert sorted(p.name for p in usb.glob("*.sicherung")) == hier
    assert sicherung.liste()[0]["orte"] == ["Dieser Rechner", "Zweiter Speicherort"]
    assert sicherung.zustand()["warnung"] == ""

    usb.rename(tmp_path / "abgezogen")
    _, hinweis = sicherung.sichern()
    assert hinweis == sicherung.ZIEL_FEHLT
    assert sicherung.liste()[0]["orte"] == ["Dieser Rechner"]
    # Ein Tag ohne Platte ist noch kein Grund zur Warnung, eine Woche schon.
    assert sicherung.zustand()["warnung"] == ""
    vor_acht_tagen = timezone.now() - timedelta(days=8)
    sicherung._aendern(ziel_zuletzt=vor_acht_tagen.isoformat())
    assert sicherung.zustand()["warnung"] == "Zweiter Speicherort nicht erreicht"


def test_taeglich_nach_einer_anfrage(
    beleg, eingerichtet, client, settings, monkeypatch
):
    class SofortThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(sicherung, "threading", SimpleNamespace(Thread=SofortThread))
    monkeypatch.setattr(sicherung, "_naechste_pruefung", 0.0)
    assert sicherung.faellig()

    client.get(reverse("core:start"))

    assert [sicherung.kopf_lesen(p)["anlass"] for p in gesichert(settings)] == [
        "taeglich"
    ]
    assert not sicherung.faellig()
    monkeypatch.setattr(sicherung, "_naechste_pruefung", 0.0)
    client.get(reverse("core:start"))
    assert len(gesichert(settings)) == 1


def test_vor_update_nur_fuer_die_datenbankdatei(
    beleg, eingerichtet, settings, tmp_path, monkeypatch
):
    migration = SimpleNamespace(app_label="core", name="9999_neu", operations=[])
    plan = [(migration, False)]
    # Die Testdatenbank liegt im Arbeitsspeicher: keine Sicherung.
    emit_pre_migrate_signal(0, False, "default", plan=plan, apps=apps)
    assert gesichert(settings) == []

    datei = tmp_path / "db.sqlite3"
    datei.write_bytes(b"")
    monkeypatch.setattr(
        sicherung,
        "connections",
        {"default": SimpleNamespace(settings_dict={"NAME": str(datei)})},
    )
    emit_pre_migrate_signal(0, False, "default", plan=[], apps=apps)
    assert gesichert(settings) == []

    emit_pre_migrate_signal(0, False, "default", plan=plan, apps=apps)
    assert [sicherung.kopf_lesen(p)["anlass"] for p in gesichert(settings)] == [
        "update"
    ]


def test_wiederherstellen_auf_neuem_rechner(beleg, eingerichtet, settings):
    datei, _ = sicherung.sichern()
    (settings.DATA_DIR / "datensicherung.json").unlink()
    assert not sicherung.eingerichtet()

    sicherung.wiederherstellen(datei, KENNWORT)

    # Die tägliche Sicherung läuft mit demselben Kennwort weiter.
    assert sicherung.eingerichtet()
    neu, _ = sicherung.sichern()
    sicherung.wiederherstellen(neu, KENNWORT)
    assert Kontakt.objects.count() == 1


def test_einrichten_ueber_die_seite(beleg, client):
    url = reverse("backups:uebersicht")
    seite = client.get(url).content.decode()
    assert "Kennwort festlegen" in seite
    assert "Ohne das Kennwort lässt sich keine Sicherung wiederherstellen" in seite
    assert "Noch nicht eingerichtet" in seite

    falsch = client.post(
        url,
        {
            "aktion": "einrichten",
            "kennwort": KENNWORT,
            "wiederholung": "anders",
            "aufbewahren": "14",
        },
    ).content.decode()
    assert "stimmen nicht überein" in falsch
    assert "Bitte bestätigen Sie" in falsch
    assert not sicherung.eingerichtet()

    seite = client.post(
        url,
        {
            "aktion": "einrichten",
            "kennwort": KENNWORT,
            "wiederholung": KENNWORT,
            "notiert": "on",
            "ziel": "",
            "aufbewahren": "14",
        },
        follow=True,
    ).content.decode()
    assert "die erste Sicherung liegt bereit" in seite
    assert "Ihre Sicherungen liegen nur auf diesem Rechner" in seite
    assert "1 Adresse · 0 Rechnungen · 0 Altbelege" in seite
    assert "Noch nicht eingerichtet" not in seite


def test_zweiter_speicherort_wird_geprueft(
    beleg, eingerichtet, client, settings, tmp_path
):
    url = reverse("backups:uebersicht")
    daten = {"aktion": "ort", "aufbewahren": "14"}

    fehlt = client.post(url, {**daten, "ziel": str(tmp_path / "gibt-es-nicht")})
    assert "Diesen Ordner gibt es nicht" in fehlt.content.decode()
    drinnen = client.post(url, {**daten, "ziel": str(settings.DATA_DIR / "archiv")})
    assert "bei den Daten von Kontorfreund" in drinnen.content.decode()

    usb = tmp_path.parent / f"{tmp_path.name}-usb"
    usb.mkdir()
    seite = client.post(
        url, {**daten, "ziel": f'"{usb}"'}, follow=True
    ).content.decode()
    assert "Die neueste Sicherung liegt jetzt auch dort" in seite
    assert len(list(usb.glob("*.sicherung"))) == 1
    assert "Ihre Sicherungen liegen nur auf diesem Rechner" not in seite


def test_einlesen_und_wiederherstellen_ueber_die_seite(
    beleg, eingerichtet, client, settings
):
    datei, _ = sicherung.sichern()
    inhalt = datei.read_bytes()
    datei.unlink()
    Kontakt.objects.create(firmenname="Später angelegt")

    antwort = client.post(
        reverse("backups:einlesen"),
        {"datei": SimpleUploadedFile("von-usb.sicherung", inhalt)},
    )
    assert antwort.status_code == 302
    seite = client.get(antwort.url).content.decode()
    assert "In der Sicherung" in seite

    falsch = client.post(antwort.url, {"kennwort": "ein falsches Kennwort"})
    assert "Das Kennwort passt nicht zu dieser Sicherung" in falsch.content.decode()
    assert Kontakt.objects.count() == 2

    fertig = client.post(antwort.url, {"kennwort": KENNWORT}, follow=True)
    assert "ist wiederhergestellt" in fertig.content.decode()
    assert list(Kontakt.objects.values_list("firmenname", flat=True)) == [
        "Muster Bäckerei GmbH"
    ]


def test_fremde_dateien_werden_abgewiesen(client, settings):
    antwort = client.post(
        reverse("backups:einlesen"),
        {"datei": SimpleUploadedFile("x.sicherung", b"keine Sicherung")},
        follow=True,
    )
    assert "keine Sicherung von Kontorfreund" in antwort.content.decode()
    assert gesichert(settings) == []

    ordner = settings.DATA_DIR / "sicherung"
    ordner.mkdir()
    (ordner / "db.sqlite3").write_bytes(b"")
    for ort, name in [
        ("hier", "db.sqlite3"),
        ("anders", "kontorfreund-2026-01-01-000000.sicherung"),
    ]:
        assert (
            client.get(
                reverse("backups:wiederherstellen", args=[ort, name])
            ).status_code
            == 404
        )
