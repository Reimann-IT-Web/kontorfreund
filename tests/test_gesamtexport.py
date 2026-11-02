"""Gesamtexport (Spezifikation D-1, D-6) – mit erfundenen Daten."""

import csv
import hashlib
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from archive.models import Altbeleg
from artikel.models import Artikel
from backups import gesamtexport
from contacts.models import Kontakt
from core.models import Firmendaten
from historie.models import Datei, Vorgang
from invoicing.models import Rechnung
from konten.models import Benutzer
from protokoll.erfassen import ERFASST
from wiedervorlagen.models import Wiedervorlage
from zahlungen.models import Zahlung

pytestmark = pytest.mark.django_db

HEUTE = date.today()


@pytest.fixture
def daten(client):
    firma = Firmendaten.laden()
    firma.name = "Muster IT & Web"
    firma.strasse = "Gartenweg 1"
    firma.plz = "55116"
    firma.ort = "Mainz"
    firma.steuernummer = "12/345/67890"
    firma.mail_passwort = "geheim-123"
    firma.save()
    kunde = Kontakt.objects.create(
        firmenname="Bäckerei Korn",
        strasse="Markt 3",
        plz="55116",
        ort="Mainz",
        telefon="=1+1",
        notiz="Zeile eins\nZeile zwei",
    )
    Artikel.objects.create(bezeichnung="Webdesign", einheit="Std.", preis=80)
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
            "menge": ["12,5"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    rechnung = Rechnung.objects.get()
    Zahlung.objects.create(rechnung=rechnung, datum=HEUTE, betrag=Decimal("400.00"))
    Vorgang.objects.create(kontakt=kunde, betreff="Anruf wegen Website")
    client.post(
        reverse("historie:hochladen", args=[kunde.pk]),
        {"dateien": [SimpleUploadedFile("Vertrag.pdf", b"%PDF-1.4 Vertrag")]},
    )
    Wiedervorlage.objects.create(kontakt=kunde, titel="Nachfassen")
    pfad = "archiv/altbelege/2015/150001.pdf"
    ziel = Path(settings.DATA_DIR) / pfad
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(b"%PDF alt")
    Altbeleg.objects.create(
        art=Altbeleg.Art.RECHNUNG,
        nummer="150001",
        datum=date(2015, 3, 1),
        kontakt=kunde,
        betrag=Decimal("99.00"),
        datei=pfad,
        sha256=hashlib.sha256(b"%PDF alt").hexdigest(),
        originalname="150001.pdf",
    )
    return kunde, rechnung


def herunterladen(client):
    antwort = client.get(reverse("backups:gesamtexport"))
    assert antwort["Content-Type"] == "application/zip"
    assert "Kontorfreund Gesamtexport" in antwort["Content-Disposition"]
    return zipfile.ZipFile(BytesIO(b"".join(antwort.streaming_content)))


def tabelle(paket, name):
    """Zeilen als Wörterbücher; CSV wie die Listen-Exporte (BOM, Semikolon)."""
    roh = paket.read(f"tabellen/{name}")
    assert roh.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(StringIO(roh.decode("utf-8-sig")), delimiter=";"))


def test_alle_daten_und_belege(client, daten):
    kunde, rechnung = daten
    paket = herunterladen(client)
    namen = set(paket.namelist())

    erwartet = {f"tabellen/{name}" for name, *_ in gesamtexport.TABELLEN}
    assert erwartet | {"tabellen/protokoll.csv", "LIESMICH.txt"} <= namen
    for pfad in gesamtexport.dateien():
        assert pfad in namen, pfad
    assert paket.read(rechnung.datei).startswith(b"%PDF")
    assert paket.read("archiv/altbelege/2015/150001.pdf") == b"%PDF alt"
    assert paket.read(Datei.objects.get().datei) == b"%PDF-1.4 Vertrag"

    (adresse,) = tabelle(paket, "adressen.csv")
    assert (adresse["Kundennummer"], adresse["Firmenname"]) == (
        "K-0001",
        "Bäckerei Korn",
    )
    assert adresse["Notiz"] == "Zeile eins\nZeile zwei"
    assert adresse["Telefon"] == "'=1+1", "keine Formel in Excel"

    (r,) = tabelle(paket, "rechnungen.csv")
    assert (r["Rechnungsnummer"], r["Kundennummer"], r["Brutto"]) == (
        rechnung.nummer,
        "K-0001",
        "1000,00",
    )
    assert (r["PDF"], r["SHA-256"]) == (rechnung.datei, rechnung.sha256)
    (p,) = tabelle(paket, "rechnungspositionen.csv")
    assert (p["Rechnung-ID"], p["Bezeichnung"], p["Gesamt"]) == (
        r["ID"],
        "Webdesign",
        "1000,00",
    )
    assert tabelle(paket, "zahlungen.csv")[0]["Rechnung-ID"] == r["ID"]
    assert tabelle(paket, "verlauf.csv")[0]["Betreff"] == "Anruf wegen Website"
    assert tabelle(paket, "dateien.csv")[0]["Dateiname"] == "Vertrag.pdf"
    assert tabelle(paket, "wiedervorlagen.csv")[0]["Was ist zu tun?"] == "Nachfassen"
    assert tabelle(paket, "altbelege.csv")[0]["Nummer"] == "150001"
    assert tabelle(paket, "artikel.csv")[0]["Artikelnummer"] == "A-0001"
    assert any(
        z["Aktion"] == "Angelegt" and z["Art"] == "Adresse"
        for z in tabelle(paket, "protokoll.csv")
    )

    (firma,) = tabelle(paket, "firma.csv")
    assert firma["Firmenname"] == "Muster IT & Web"
    assert "geheim-123" not in paket.read("tabellen/firma.csv").decode("utf-8-sig")

    liesmich = paket.read("LIESMICH.txt").decode("utf-8-sig")
    assert "für Muster IT & Web" in liesmich
    assert "adressen.csv" in liesmich and "(1 Zeile)" in liesmich
    assert "3 Belege und Dateien im Original" in liesmich


def test_alle_geschaeftsdaten_kommen_mit():
    """Neue Modelle mit Geschäftsdaten gehören auch in den Gesamtexport."""
    exportiert = {
        abfrage.model._meta.label for _, _, abfrage, *_ in gesamtexport.TABELLEN
    }
    einstellungen = {
        "zahlungen.Mahnstufe",
        "zahlungen.Basiszins",
        "konten.Benutzer",
        "auswertungen.Datev",
        "benachrichtigungen.Einstellung",
    }
    assert set(ERFASST) - einstellungen <= exportiert


def test_nur_fuer_den_inhaber():
    c = Client()
    c.force_login(
        Benutzer.objects.create_user(
            "mia@muster.test", name="Mia", rolle=Benutzer.Rolle.MITARBEITER
        )
    )
    assert c.get(reverse("backups:gesamtexport")).status_code == 403
