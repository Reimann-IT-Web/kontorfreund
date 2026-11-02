"""Verfahrensdokumentation und Verzeichnis von Verarbeitungstätigkeiten (Spezifikation D-5)."""

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader

from archive import pruefung
from core.models import Firmendaten
from dokumentation import fassungen, inhalt
from dokumentation.models import Abgelegt, Fassung
from konten.models import Benutzer

pytestmark = pytest.mark.django_db

VERFAHREN = Fassung.Art.VERFAHREN
DATENSCHUTZ = Fassung.Art.DATENSCHUTZ


@pytest.fixture(autouse=True)
def firma():
    firma = Firmendaten.laden()
    firma.name = "Muster IT & Web"
    firma.inhaber = "Max Muster"
    firma.strasse = "Gartenweg 1"
    firma.plz = "55116"
    firma.ort = "Mainz"
    firma.steuernummer = "12/345/67890"
    firma.save()
    return firma


def herunterladen(client, art):
    antwort = client.post(reverse("dokumentation:herunterladen", args=[art]))
    assert antwort.status_code == 200
    return b"".join(antwort.streaming_content)


def text(pdf):
    return " ".join(s.extract_text() for s in PdfReader(BytesIO(pdf)).pages)


def test_fassungen_entstehen_nur_bei_aenderungen(client):
    pdf = herunterladen(client, VERFAHREN)
    (erste,) = Fassung.objects.all()
    assert erste.nummer == 1 and erste.version == settings.VERSION
    assert erste.erstellt_von.name == "Max Muster"
    datei = Path(settings.DATA_DIR) / erste.datei
    assert datei.read_bytes() == pdf
    assert hashlib.sha256(pdf).hexdigest() == erste.sha256
    inhalt_pdf = text(pdf)
    assert "Verfahrensdokumentation" in inhalt_pdf and "Muster IT & Web" in inhalt_pdf
    assert "Noch offen" in inhalt_pdf

    # Nichts geändert: dieselbe Fassung, keine neue Datei.
    assert herunterladen(client, VERFAHREN) == pdf
    assert Fassung.objects.count() == 1

    client.post(
        reverse("dokumentation:seite"),
        {"taetigkeit": "IT-Service und Webdesign, seit 2013."},
    )
    neu = herunterladen(client, VERFAHREN)
    zweite = Fassung.objects.get(nummer=2)
    assert zweite.aenderungen == ["1.1 Unternehmen"]
    assert "IT-Service und Webdesign" in text(neu)
    assert "1.1 Unternehmen" in text(neu)
    # Die erste Fassung bleibt, wie sie war, und lässt sich weiter herunterladen.
    assert datei.read_bytes() == pdf
    alt = client.get(reverse("dokumentation:fassung", args=[erste.pk]))
    assert b"".join(alt.streaming_content) == pdf
    assert "Verfahrensdokumentation Fassung 1.pdf" in alt["Content-Disposition"]


def test_offene_angaben(client):
    # Sechs Fragen zum Betrieb und die noch nicht eingerichtete Datensicherung.
    assert fassungen.offen(fassungen.entwurf(VERFAHREN)) == 7
    assert fassungen.offen(fassungen.entwurf(DATENSCHUTZ)) == 2
    seite = client.get(reverse("dokumentation:seite")).content.decode()
    assert "7 Angaben offen" in seite and "2 Angaben offen" in seite

    antwort = client.post(
        reverse("dokumentation:seite"),
        {
            "taetigkeit": "IT-Service",
            "gewinnermittlung": "Einnahmenüberschussrechnung über ELSTER",
            "zahlungsverkehr": "Geschäftskonto, Auszüge als PDF",
            "belege": "Ordner je Jahr",
            "email": "Postfach, nichts wird gelöscht",
            "rechner": "PC im Büro",
            "weitere_verarbeitungen": "Website mit Kontaktformular",
            "tom_bildschirmsperre": "on",
        },
    )
    assert antwort.status_code == 302
    assert fassungen.offen(fassungen.entwurf(VERFAHREN)) == 1
    assert fassungen.offen(fassungen.entwurf(DATENSCHUTZ)) == 0
    seite = client.get(reverse("dokumentation:seite")).content.decode()
    assert "1 Angabe offen" in seite and "vollständig" in seite

    pdf = text(herunterladen(client, DATENSCHUTZ))
    assert "Verzeichnis von Verarbeitungstätigkeiten" in pdf
    assert "Website mit Kontaktformular" in pdf
    assert "sperrt sich nach kurzer Zeit" in pdf
    assert "Festplatte" not in pdf


def test_inhalt_folgt_den_einstellungen(firma):
    def texte(art):
        return str(fassungen.entwurf(art))

    assert "§ 19 UStG" in texte(VERFAHREN)
    assert "Versand von Belegen per E-Mail" not in texte(DATENSCHUTZ)
    assert "Belege aus dem bisherigen Programm" not in texte(VERFAHREN)
    firma.kleinunternehmer = False
    firma.email = "post@muster.test"
    firma.mail_server = "smtp.muster.test"
    firma.save()
    assert "Regelbesteuerung" in texte(VERFAHREN)
    assert "Steuerbefreiung" not in texte(VERFAHREN)
    assert "Postausgang smtp.muster.test" in texte(DATENSCHUTZ)


def test_neuer_teil_meldet_nur_sich_selbst():
    alt = [
        inhalt.abschnitt("A", inhalt.teil("eins", inhalt.absatz("x"))),
        inhalt.abschnitt("B", inhalt.teil("zwei", inhalt.absatz("y"))),
    ]
    neu = [
        inhalt.abschnitt(
            "A",
            inhalt.teil("neu", inhalt.absatz("n")),
            inhalt.teil("eins", inhalt.absatz("x")),
        ),
        inhalt.abschnitt("B"),
    ]
    assert fassungen.aenderungen(alt, neu) == ["1.1 neu", "zwei (entfallen)"]


def test_druck_trennt_nicht_zwischen_zahl_und_einheit():
    assert fassungen._binden(["Art. 18 DSGVO", {"a": "25.000 € und 8 Jahre"}, 3]) == [
        "Art. 18 DSGVO",
        {"a": "25.000 € und 8 Jahre"},
        3,
    ]


def test_fassungen_bleiben_unveraendert(client):
    herunterladen(client, DATENSCHUTZ)
    fassung = Fassung.objects.get()
    fassung.version = "anders"
    with pytest.raises(Abgelegt):
        fassung.save()
    with pytest.raises(Abgelegt):
        fassung.delete()
    # Die tägliche Prüfung der Ablage kennt die Datei.
    assert any(d == fassung.datei for _, _, _, d, _ in pruefung._dateien())


def test_nur_fuer_den_inhaber(client):
    assert (
        client.post(
            reverse("dokumentation:herunterladen", args=["unbekannt"])
        ).status_code
        == 404
    )
    c = Client()
    c.force_login(
        Benutzer.objects.create_user(
            "mia@muster.test", name="Mia", rolle=Benutzer.Rolle.MITARBEITER
        )
    )
    assert c.get(reverse("dokumentation:seite")).status_code == 403
    assert (
        c.post(reverse("dokumentation:herunterladen", args=[VERFAHREN])).status_code
        == 403
    )
    assert not Fassung.objects.exists()
