"""Datenschutz für eine Adresse (Spezifikation D-1) – mit erfundenen Daten."""

import hashlib
import json
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from angebote.models import Angebot
from archive.models import Altbeleg
from contacts import datenschutz
from contacts.models import Kontakt
from core.models import Firmendaten
from eingang.models import Eingangsrechnung
from historie.models import Datei, Vorgang
from invoicing.models import Rechnung
from konten.models import Benutzer
from protokoll.models import GESCHWAERZT, Eintrag
from wiedervorlagen.models import Wiedervorlage
from zahlungen.models import Zahlung

pytestmark = pytest.mark.django_db

HEUTE = timezone.localdate()
JAHR = HEUTE.year


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster IT & Web"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.iban = "DE02120300000000202051"
    f.save()
    return f


@pytest.fixture
def kunde():
    k = Kontakt.objects.create(
        art=Kontakt.Art.PERSON,
        anrede="Frau",
        vorname="Lea",
        nachname="Sommer",
        strasse="Lindenweg 4",
        plz="55118",
        ort="Mainz",
        telefon="06131 4711",
        email="lea@sommer.test",
        notiz="Ruft am liebsten vormittags an",
    )
    # Eine frühere Angabe, die nur noch im Änderungsprotokoll steht
    k.telefon = "0170 4712"
    k.save()
    return k


@pytest.fixture
def mitarbeiter():
    benutzer = Benutzer.objects.create_user(
        "mia@muster.test", name="Mia Muster", rolle=Benutzer.Rolle.MITARBEITER
    )
    c = Client()
    c.force_login(benutzer)
    return c


def schreiben(client, kunde):
    """Festgeschriebene Rechnung über 1.000 € als Kleinunternehmer."""
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": HEUTE.isoformat(),
            "leistung_von": HEUTE.isoformat(),
            "zahlungsziel": "14",
            "steuerfall": "kleinunternehmer",
            "kopftext": "Sehr geehrte Frau Sommer,",
            "fusstext": "Mit freundlichen Grüßen",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["12,5"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    rechnung = Rechnung.objects.latest("pk")
    assert rechnung.status == Rechnung.Status.FESTGESCHRIEBEN
    return rechnung


def ablegen(pfad, inhalt):
    ziel = Path(settings.DATA_DIR) / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return hashlib.sha256(inhalt).hexdigest()


def drumherum(client, kunde):
    """Verlauf, Datei, Wiedervorlage und ein Rechnungsentwurf zur Adresse."""
    Vorgang.objects.create(
        kontakt=kunde,
        art=Vorgang.Art.ANRUF,
        betreff="Rückruf wegen der Website",
        text="Wünscht eine neue Startseite",
    )
    client.post(
        reverse("historie:hochladen", args=[kunde.pk]),
        {"dateien": [SimpleUploadedFile("Vertrag Sommer.pdf", b"%PDF-1.4 Vertrag")]},
    )
    Wiedervorlage.objects.create(kontakt=kunde, titel="Angebot nachfassen")
    entwurf = Rechnung.objects.create(kontakt=kunde, betreff="Wartung Sommer")
    entwurf.positionen.create(nr=1, bezeichnung="Wartung", preis=Decimal("70.00"))


def auskunft(client, kunde):
    antwort = client.post(reverse("contacts:auskunft", args=[kunde.pk]))
    assert antwort["Content-Type"] == "application/zip"
    assert f"Auskunft {kunde.kundennummer}" in antwort["Content-Disposition"]
    return zipfile.ZipFile(BytesIO(b"".join(antwort.streaming_content)))


def test_auskunft_enthaelt_alle_daten(client, firma, kunde):
    drumherum(client, kunde)
    rechnung = schreiben(client, kunde)
    Zahlung.objects.create(rechnung=rechnung, datum=HEUTE, betrag=Decimal("400.00"))
    datei = Datei.objects.get()

    paket = auskunft(client, kunde)
    namen = paket.namelist()
    assert {"Auskunft K-0001.pdf", "auskunft.json", rechnung.datei, datei.datei} <= set(
        namen
    )
    assert paket.read(datei.datei) == b"%PDF-1.4 Vertrag"

    daten = json.loads(paket.read("auskunft.json"))
    assert daten["Verantwortlicher"]["Name"] == "Muster IT & Web"
    adresse = daten["Adresse"]
    assert (adresse["Kundennummer"], adresse["Nachname"], adresse["Telefon"]) == (
        "K-0001",
        "Sommer",
        "0170 4712",
    )
    assert adresse["Notiz"] == "Ruft am liebsten vormittags an"
    (beleg,) = daten["Belege"]
    assert (beleg["Nummer"], beleg["Betrag"], beleg["Aufbewahren bis"]) == (
        rechnung.nummer,
        "1000.00",
        f"{JAHR + 8}-12-31",
    )
    assert beleg["Positionen"][0]["Bezeichnung"] == "Webdesign"
    assert daten["Entwürfe"][0]["Betreff"] == "Wartung Sommer"
    assert daten["Zahlungen"][0]["Betrag"] == "400.00"
    assert daten["Verlauf"][0]["Text"] == "Wünscht eine neue Startseite"
    assert daten["Dateien"][0]["Name"] == "Vertrag Sommer.pdf"
    assert daten["Wiedervorlagen"][0]["Was ist zu tun?"] == "Angebot nachfassen"
    aenderungen = [a for e in daten["Änderungsprotokoll"] for a in e["Änderungen"]]
    assert {"Feld": "Telefon", "Vorher": "06131 4711", "Nachher": "0170 4712"} in (
        aenderungen
    )

    text = "\n".join(
        s.extract_text()
        for s in PdfReader(BytesIO(paket.read("Auskunft K-0001.pdf"))).pages
    )
    for erwartet in (
        "Auskunft nach Art. 15 DSGVO",
        "Sehr geehrte Frau Sommer,",
        "lea@sommer.test",
        rechnung.nummer,
        f"31.12.{JAHR + 8}",
        "Rückruf wegen der Website",
        "Vertrag Sommer.pdf",
        "Angebot nachfassen",
        "06131 4711",
        "Art. 77 DSGVO",
        "Max Muster",
    ):
        assert erwartet in text, erwartet

    assert Eintrag.objects.filter(aktion=Eintrag.Aktion.AUSKUNFT).count() == 1
    seite = client.get(reverse("contacts:datenschutz", args=[kunde.pk]))
    assert f"Zuletzt erstellt am {HEUTE:%d.%m.%Y}" in seite.text


def test_loeschen_ohne_belege(
    client, kunde, settings, django_capture_on_commit_callbacks
):
    drumherum(client, kunde)
    pfad = settings.DATA_DIR / Datei.objects.get().datei
    assert pfad.is_file()

    seite = client.get(reverse("contacts:datenschutz", args=[kunde.pk]))
    assert "mit 1 Entwurf, 1 Eintrag im Verlauf, 1 Datei, 1 Wiedervorlage" in seite.text

    url = reverse("contacts:loeschen", args=[kunde.pk])
    antwort = client.post(url, follow=True)
    assert "Bitte bestätigen Sie" in antwort.text
    assert Kontakt.objects.exists()

    with django_capture_on_commit_callbacks(execute=True):
        antwort = client.post(url, {"bestaetigt": "1"}, follow=True)
    assert "K-0001 ist mit allem, was dazugehörte, gelöscht." in antwort.text
    assert not Kontakt.objects.exists()
    assert not Vorgang.objects.exists()
    assert not Datei.objects.exists()
    assert not Wiedervorlage.objects.exists()
    assert not Rechnung.objects.exists()
    assert not pfad.exists()
    assert not pfad.parent.exists()

    # Im Protokoll bleibt, wann wer etwas getan hat, aber nichts über die Person.
    inhalt = json.dumps(
        list(Eintrag.objects.values("beschreibung", "aenderungen")),
        ensure_ascii=False,
    )
    for spur in ("Sommer", "Lea", "4711", "Lindenweg", "Startseite", "nachfassen"):
        assert spur not in inhalt, spur
    assert Eintrag.objects.filter(
        art="Adresse", aktion=Eintrag.Aktion.ANGELEGT, beschreibung=GESCHWAERZT
    ).exists()
    loeschung = Eintrag.objects.get(aktion=Eintrag.Aktion.LOESCHUNG)
    assert loeschung.beschreibung.startswith("K-0001 mit 1 Entwurf")
    assert loeschung.wer == "Max Muster"


def test_abgelaufene_belege_werden_mitgeloescht(
    client, kunde, settings, django_capture_on_commit_callbacks
):
    pfad = "archiv/altbelege/2015-001.pdf"
    Altbeleg.objects.create(
        art=Altbeleg.Art.RECHNUNG,
        nummer="2015-001",
        datum=date(2015, 3, 1),
        kontakt=kunde,
        empfaenger="Lea Sommer\nLindenweg 4",
        betrag=Decimal("99.00"),
        datei=pfad,
        sha256=ablegen(pfad, b"%PDF 2015-001"),
        originalname="2015-001.pdf",
    )
    seite = client.get(reverse("contacts:datenschutz", args=[kunde.pk]))
    assert "Die Aufbewahrungsfrist aller Belege ist abgelaufen" in seite.text
    assert "31.12.2023" in seite.text

    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("contacts:loeschen", args=[kunde.pk]), {"bestaetigt": "1"})
    assert not Kontakt.objects.exists()
    assert not Altbeleg.objects.exists()
    assert not (settings.DATA_DIR / pfad).exists()


def test_sperren_solange_belege_aufbewahrt_werden(client, firma, kunde, mitarbeiter):
    rechnung = schreiben(client, kunde)
    Angebot.objects.create(kontakt=kunde, betreff="Entwurf für Sommer")
    vorlage = Wiedervorlage.objects.create(kontakt=kunde, titel="Sommer anrufen")
    Vorgang.objects.create(kontakt=kunde, betreff="Gespräch mit Sommer")

    seite = client.get(reverse("contacts:datenschutz", args=[kunde.pk]))
    assert f"Löschen geht deshalb erst ab dem 31.12.{JAHR + 8}." in seite.text
    assert "1 Entwurf wird dabei gelöscht" in seite.text
    antwort = client.post(
        reverse("contacts:loeschen", args=[kunde.pk]), {"bestaetigt": "1"}
    )
    assert antwort.status_code == 404

    client.post(reverse("contacts:sperren", args=[kunde.pk]))
    kunde.refresh_from_db()
    assert kunde.gesperrt_am and kunde.archiviert
    assert not Angebot.objects.exists()
    vorlage.refresh_from_db()
    assert vorlage.erledigt and vorlage.ergebnis == datenschutz.ERLEDIGT
    assert Rechnung.objects.get() == rechnung

    # Nirgends mehr zu sehen …
    liste = reverse("contacts:liste")
    assert "Lea Sommer" not in client.get(liste).text
    assert "Lea Sommer" not in client.get(liste, {"archiv": "1"}).text
    assert "Lea Sommer" not in client.get(liste, {"q": "Sommer"}).text
    assert "Lea Sommer" not in client.get(reverse("core:start")).text
    assert "Lea Sommer" not in client.get(reverse("invoicing:neu")).text
    erledigt = client.get(reverse("wiedervorlagen:liste"), {"zeigen": "erledigt"})
    assert "Sommer anrufen" not in erledigt.text
    neu = client.post(
        reverse("contacts:neu"),
        {"art": "person", "nachname": "Sommer", "vorname": "Lea"}
        | {"ort": "Mainz", "land": "Deutschland"},
    )
    assert neu.status_code == 302, "keine Dublettenwarnung mit der gesperrten Adresse"

    # … außer für den Inhaber, und auch für ihn nur zum Ansehen.
    assert "1 gesperrt" in client.get(liste).text
    assert "Lea Sommer" in client.get(liste, {"gesperrt": "1"}).text
    bearbeiten = reverse("contacts:bearbeiten", args=[kunde.pk])
    assert client.get(bearbeiten).url == reverse(
        "contacts:datenschutz", args=[kunde.pk]
    )
    verlauf = reverse("historie:verlauf", args=[kunde.pk])
    seite = client.get(verlauf)
    assert "Gespräch mit Sommer" in seite.text
    assert "Eintragen" not in seite.text
    assert client.post(verlauf, {"art": "notiz", "betreff": "x"}).status_code == 404
    archivieren = reverse("contacts:archivieren", args=[kunde.pk])
    assert client.post(archivieren).status_code == 404
    hochladen = reverse("historie:hochladen", args=[kunde.pk])
    assert client.post(hochladen).status_code == 404

    assert mitarbeiter.get(bearbeiten).status_code == 404
    assert mitarbeiter.get(verlauf).status_code == 404
    assert "K-0001" not in mitarbeiter.get(liste, {"gesperrt": "1"}).text

    client.post(reverse("contacts:entsperren", args=[kunde.pk]))
    kunde.refresh_from_db()
    assert kunde.gesperrt_am is None and kunde.archiviert
    assert "K-0001" in client.get(liste, {"archiv": "1"}).text
    geaendert = Eintrag.objects.filter(art="Adresse", aktion=Eintrag.Aktion.GEAENDERT)
    assert any(
        feld == "Gesperrt nach Art. 18 DSGVO"
        for e in geaendert
        for feld, _, _ in e.aenderungen
    )


def test_aufbewahrungsfristen(kunde):
    for art, nummer in [(Altbeleg.Art.RECHNUNG, "R-1"), (Altbeleg.Art.ANGEBOT, "A-1")]:
        Altbeleg.objects.create(
            art=art,
            nummer=nummer,
            datum=date(2020, 6, 1),
            kontakt=kunde,
            datei=f"archiv/altbelege/{nummer}.pdf",
            sha256=nummer,
            originalname=f"{nummer}.pdf",
        )
    Eingangsrechnung.objects.create(
        format=Eingangsrechnung.Format.XML,
        syntax="UBL",
        art="380",
        nummer="E-1",
        datum=date(2019, 12, 31),
        lieferant="Lea Sommer",
        kontakt=kunde,
        waehrung="EUR",
        brutto=Decimal("10.00"),
        zahlbetrag=Decimal("10.00"),
        datei="archiv/eingang/E-1.xml",
        sha256="E-1",
        originalname="E-1.xml",
    )
    alle = datenschutz.belege(kunde)
    assert [(b.nummer, b.aufbewahren_bis) for b in alle] == [
        ("E-1", date(2027, 12, 31)),
        ("A-1", date(2026, 12, 31)),
        ("R-1", date(2028, 12, 31)),
    ]
    assert datenschutz.frist(alle) == date(2028, 12, 31)


def test_nur_fuer_den_inhaber(kunde, mitarbeiter):
    assert (
        mitarbeiter.get(reverse("contacts:datenschutz", args=[kunde.pk])).status_code
        == 403
    )
    for name in ("auskunft", "sperren", "loeschen"):
        url = reverse(f"contacts:{name}", args=[kunde.pk])
        assert mitarbeiter.post(url, {"bestaetigt": "1"}).status_code == 403
    assert Kontakt.objects.filter(gesperrt_am__isnull=True).exists()
    assert (
        reverse("contacts:datenschutz", args=[kunde.pk])
        not in mitarbeiter.get(reverse("contacts:liste")).text
    )
