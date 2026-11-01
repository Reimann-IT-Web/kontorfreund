"""Dateien an Adressen und Vorgängen (Spezifikation K-3) – mit erfundenen Daten."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from contacts.models import Kontakt
from historie import zeitleiste
from historie.models import Datei, Vorgang
from protokoll.models import Eintrag

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n%Testdatei\n"
HTML = b"<html><script>alert('Hallo')</script></html>"


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )


def hochladen(client, kunde, *dateien):
    return client.post(
        reverse("historie:hochladen", args=[kunde.pk]),
        {"dateien": [SimpleUploadedFile(name, inhalt) for name, inhalt in dateien]},
        follow=True,
    )


def test_mehrere_auf_einmal_hochladen(client, kunde, settings):
    antwort = hochladen(
        client, kunde, ("Vertrag 2026.pdf", PDF), ("Notizen.docx", b"PK\x03\x04")
    )
    assert "2 Dateien sind abgelegt." in antwort.text

    vertrag, notizen = Datei.objects.order_by("pk")
    assert (vertrag.kontakt, vertrag.name, vertrag.groesse) == (
        kunde,
        "Vertrag 2026.pdf",
        len(PDF),
    )
    assert vertrag.benutzer.email == "inhaber@muster.test"
    # Im Archiv, damit jede Datensicherung sie mitnimmt; Name bereinigt, nie überschrieben
    assert vertrag.datei.startswith("archiv/dateien/K-0001/")
    assert vertrag.datei.endswith("-Vertrag_2026.pdf")
    assert (settings.DATA_DIR / vertrag.datei).read_bytes() == PDF
    assert vertrag.datei != notizen.datei

    seite = antwort.text
    assert "Vertrag 2026.pdf" in seite
    assert "PDF · " in seite
    assert "DOCX · " in seite
    assert Eintrag.objects.filter(art="Datei", aktion="angelegt").count() == 2


def test_vorschau_nur_fuer_pdf_und_bilder(client, kunde):
    hochladen(
        client,
        kunde,
        ("Rechnung.pdf", PDF),
        ("Foto.JPG", b"\xff\xd8\xff"),
        ("Tabelle.xlsx", b"PK"),
    )
    pdf, foto, tabelle = Datei.objects.order_by("pk")

    antwort = client.get(reverse("historie:datei", args=[pdf.pk]))
    assert antwort["Content-Type"] == "application/pdf"
    assert antwort["Content-Disposition"].startswith("inline")
    assert b"".join(antwort.streaming_content) == PDF
    # Der PDF-Betrachter des Browsers braucht die gelockerte Richtlinie
    assert "Content-Security-Policy" not in antwort

    antwort = client.get(reverse("historie:datei", args=[foto.pk]))
    assert antwort["Content-Type"] == "image/jpeg"
    assert antwort["Content-Disposition"].startswith("inline")
    assert antwort["Content-Security-Policy"] == "sandbox"

    antwort = client.get(reverse("historie:datei", args=[tabelle.pk]))
    assert antwort["Content-Disposition"].startswith("attachment")
    assert 'filename="Tabelle.xlsx"' in antwort["Content-Disposition"]

    herunter = client.get(reverse("historie:datei", args=[pdf.pk]) + "?herunterladen")
    assert herunter["Content-Disposition"].startswith("attachment")


def test_html_wird_nie_im_browser_ausgefuehrt(client, kunde):
    for name in ["Seite.html", "Bild.svg", "ohne Endung"]:
        hochladen(client, kunde, (name, HTML))
        datei = Datei.objects.latest("pk")
        antwort = client.get(reverse("historie:datei", args=[datei.pk]))
        assert antwort["Content-Type"] == "application/octet-stream", name
        assert antwort["Content-Disposition"].startswith("attachment"), name
        assert antwort["X-Content-Type-Options"] == "nosniff"
        assert antwort["Content-Security-Policy"] == "sandbox"


def test_dateinamen_werden_bereinigt(client, kunde):
    hochladen(
        client,
        kunde,
        ("C:\\Users\\Max\\..\\Angebot.pdf", PDF),
        ("../../config/settings.py", b"x"),
        (" . ", b"x"),
        ("€€€.€", b"x"),
    )
    angebot, settings_py, leer, euro = Datei.objects.order_by("pk")
    assert angebot.name == "Angebot.pdf"
    assert settings_py.name == "settings.py"
    assert settings_py.datei.startswith("archiv/dateien/K-0001/")
    assert leer.name == "Datei"
    assert euro.name == "€€€.€"
    assert euro.datei.endswith("-Datei")


def test_zu_grosse_datei_wird_abgelehnt(client, kunde, settings):
    settings.DATEI_MB = 1
    antwort = hochladen(
        client, kunde, ("Video.mp4", b"0" * (1024 * 1024 + 1)), ("Klein.pdf", PDF)
    )
    assert "Video.mp4: Die Datei ist größer als 1 MB" in antwort.text
    assert [d.name for d in Datei.objects.all()] == ["Klein.pdf"]


def test_ohne_datei(client, kunde):
    antwort = client.post(reverse("historie:hochladen", args=[kunde.pk]), follow=True)
    assert "Bitte wählen Sie eine Datei aus." in antwort.text


def test_loeschen_und_rueckgaengig(client, kunde, settings):
    hochladen(client, kunde, ("Vertrag.pdf", PDF))
    datei = Datei.objects.get()

    antwort = client.post(
        reverse("historie:datei_loeschen", args=[datei.pk]), follow=True
    )
    verlauf = reverse("historie:verlauf", args=[kunde.pk])
    assert antwort.redirect_chain[-1][0] == f"{verlauf}?geloescht={datei.pk}#dateien"
    assert "„Vertrag.pdf“ ist gelöscht." in antwort.text
    assert "Rückgängig" in antwort.text
    assert client.get(reverse("historie:datei", args=[datei.pk])).status_code == 404
    # Noch da, nur ausgeblendet
    assert (settings.DATA_DIR / datei.datei).exists()

    antwort = client.post(
        reverse("historie:datei_zurueckholen", args=[datei.pk]), follow=True
    )
    assert "„Vertrag.pdf“ ist wieder da." in antwort.text
    assert client.get(reverse("historie:datei", args=[datei.pk])).status_code == 200
    aenderungen = [
        e.aenderungen[0][0]
        for e in Eintrag.objects.filter(art="Datei", aktion="geaendert")
    ]
    assert aenderungen == ["Gelöscht am", "Gelöscht am"]


def test_nach_30_tagen_endgueltig_weg(client, kunde, settings):
    hochladen(client, kunde, ("Alt.pdf", PDF), ("Neu.pdf", PDF))
    alt, neu = Datei.objects.order_by("pk")
    alt.geloescht_am = timezone.now() - timedelta(days=31)
    alt.save()
    neu.geloescht_am = timezone.now() - timedelta(days=29)
    neu.save()

    Datei.aufraeumen()
    assert list(Datei.objects.all()) == [neu]
    assert not (settings.DATA_DIR / alt.datei).exists()
    assert (settings.DATA_DIR / neu.datei).exists()
    assert Eintrag.objects.filter(art="Datei", aktion="geloescht").count() == 1


def test_datei_an_einem_eintrag(client, kunde):
    antwort = client.post(
        reverse("historie:verlauf", args=[kunde.pk]),
        {
            "art": "anruf",
            "zeitpunkt": "2026-10-20T09:30",
            "betreff": "Angebot besprochen",
            "text": "",
            "dateien": [SimpleUploadedFile("Skizze.png", b"\x89PNG")],
        },
        follow=True,
    )
    assert "Anruf eingetragen, mit 1 Datei." in antwort.text
    vorgang = Vorgang.objects.get()
    datei = Datei.objects.get()
    assert datei.vorgang == vorgang

    punkt = next(p for p in zeitleiste.punkte(kunde) if p.vorgang)
    assert punkt.dateien == [datei]
    # Nur beim Eintrag, nicht noch einmal als eigener Punkt
    assert not [p for p in zeitleiste.punkte(kunde) if p.art == "dokument"]
    assert "zu Anruf „Angebot besprochen“" in antwort.text

    # Auf der Seite des Eintrags: weitere anhängen, löschen und zurückholen
    client.post(
        reverse("historie:bearbeiten", args=[vorgang.pk]),
        {
            "art": "anruf",
            "zeitpunkt": "2026-10-20T09:30",
            "betreff": "Angebot besprochen",
            "text": "",
            "dateien": [SimpleUploadedFile("Notiz.txt", b"Text")],
        },
    )
    assert vorgang.dateien.count() == 2
    antwort = client.post(
        reverse("historie:datei_loeschen", args=[datei.pk]),
        {"von": "vorgang"},
        follow=True,
    )
    seite = reverse("historie:bearbeiten", args=[vorgang.pk])
    assert antwort.redirect_chain[-1][0] == f"{seite}?geloescht={datei.pk}#dateien"
    assert "„Skizze.png“ ist gelöscht." in antwort.text

    # Wird der Eintrag gelöscht, bleiben seine Dateien bei der Adresse
    antwort = client.post(reverse("historie:loeschen", args=[vorgang.pk]), follow=True)
    assert "Die angehängten Dateien bleiben bei der Adresse." in antwort.text
    assert [p.titel for p in zeitleiste.punkte(kunde)] == ["Notiz.txt"]


def test_eigener_punkt_im_verlauf(client, kunde):
    hochladen(client, kunde, ("Vertrag.pdf", PDF))
    datei = Datei.objects.get()
    (punkt,) = zeitleiste.punkte(kunde)
    assert (punkt.art, punkt.titel, punkt.icon) == (
        "dokument",
        "Vertrag.pdf",
        "paperclip",
    )
    assert punkt.url == reverse("historie:datei", args=[datei.pk])
    assert punkt.neues_fenster
    seite = client.get(
        reverse("historie:verlauf", args=[kunde.pk]), {"art": "dokument"}
    ).text
    assert "Vertrag.pdf" in seite


def test_mitarbeiter_darf_dateien_ablegen(anonym, kunde):
    from konten.models import Benutzer

    mitarbeiter = Benutzer.objects.create_user(
        "team@muster.test", name="Team", rolle=Benutzer.Rolle.MITARBEITER
    )
    anonym.force_login(mitarbeiter)
    hochladen(anonym, kunde, ("Foto.png", b"\x89PNG"))
    assert Datei.objects.get().benutzer == mitarbeiter


def test_ohne_anmeldung_nichts(anonym, client, kunde):
    hochladen(client, kunde, ("Vertrag.pdf", PDF))
    datei = Datei.objects.get()
    antwort = anonym.get(reverse("historie:datei", args=[datei.pk]))
    assert antwort.status_code == 302
    assert "/konto/anmelden/" in antwort["Location"]
