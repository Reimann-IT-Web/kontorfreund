"""Briefkopf (Spezifikation B-6): Logo, Kopfbild, Lage, Farbe und Angaben im Kopf."""

import base64
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw
from pypdf import PdfReader

from contacts import datenschutz
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import beleg
from invoicing.models import Rechnung
from konten.models import Benutzer

LOGO = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    b'<rect width="32" height="32" rx="9" fill="#0b1220"/></svg>'
)
pytestmark = pytest.mark.django_db

A4_HOEHE_PT = 841.89
PT_JE_MM = 72 / 25.4


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
    f.save()
    return f


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Muster Bäckerei GmbH",
        strasse="Lindenweg 4",
        plz="55116",
        ort="Mainz",
    )


@pytest.fixture
def daten(tmp_path, settings):
    settings.DATA_DIR = tmp_path
    return tmp_path


@pytest.fixture
def mitarbeiter():
    benutzer = Benutzer.objects.create_user(
        "mia@muster.test", name="Mia Muster", rolle=Benutzer.Rolle.MITARBEITER
    )
    c = Client()
    c.force_login(benutzer)
    return c


def bild(breite, hoehe, rand=0, modus="RGB", grund=(255, 255, 255), art="PNG"):
    """Rotes Rechteck mit `rand` Pixeln Grund ringsum."""
    b = Image.new(modus, (breite, hoehe), grund)
    ImageDraw.Draw(b).rectangle(
        [rand, rand, breite - rand - 1, hoehe - rand - 1], fill=(200, 30, 30)
    )
    ausgabe = BytesIO()
    b.save(ausgabe, format=art)
    return ausgabe.getvalue()


def weiss(breite, hoehe):
    ausgabe = BytesIO()
    Image.new("RGB", (breite, hoehe), (255, 255, 255)).save(ausgabe, format="PNG")
    return ausgabe.getvalue()


def briefkopf_absenden(client, **mehr):
    """Wie der Browser: Kästchen fehlen, wenn sie nicht angekreuzt sind."""
    werte = {
        "kopf_art": "logo",
        "logo_lage": "links",
        "logo_hoehe": "12",
        "kopf_name": "on",
        "kopf_anschrift": "on",
        "kopf_linie": "on",
        "akzentfarbe": "#1d5f6e",
        "kopfbild_breite": "text",
        **mehr,
    }
    return client.post(
        reverse("core:briefkopf"), {k: v for k, v in werte.items() if v is not None}
    )


def rechnung_schreiben(client, kunde, daten):
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": "2026-10-29",
            "leistung_von": "2026-10-01",
            "zahlungsziel": "14",
            "steuerfall": "kleinunternehmer",
            "kopftext": "Sehr geehrte Damen und Herren,",
            "fusstext": "Mit freundlichen Grüßen",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["1"],
            "einheit": ["Stück"],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    rechnung = Rechnung.objects.latest("pk")
    assert rechnung.status == Rechnung.Status.FESTGESCHRIEBEN
    return (daten / rechnung.datei).read_bytes()


def seite_1(pdf):
    return PdfReader(BytesIO(pdf)).pages[0]


def von_oben_mm(pdf, gesucht):
    """Abstand der ersten Grundlinie mit `gesucht` vom oberen Blattrand."""
    funde = []

    def merken(text, cm, tm, *_):
        if gesucht in text:
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            funde.append((A4_HOEHE_PT - y) / PT_JE_MM)

    seite_1(pdf).extract_text(visitor_text=merken)
    assert funde, gesucht
    return funde[0]


def vorschau_bild(firma):
    url = beleg.kopf_vorschau(firma)
    return Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


# ---------- Seite und Formular ----------


def test_nur_fuer_den_inhaber(client, mitarbeiter, firma):
    assert mitarbeiter.get(reverse("core:briefkopf")).status_code == 403
    seite = client.get(reverse("core:briefkopf")).text
    assert 'class="kopf-vorschau"' in seite
    assert 'src="data:image/png;base64,' in seite
    # Die Einstellungen führen dorthin.
    assert reverse("core:briefkopf") in client.get(reverse("core:einstellungen")).text


def test_vorgaben_ergeben_den_bisherigen_kopf(firma):
    kopf = beleg.kopf_einstellungen(firma)
    assert kopf == {
        "art": "logo",
        "lage": "links",
        "logo_hoehe": 12,
        "logo_breite": 65,
        "name": True,
        "anschrift": True,
        "linie": True,
        "farbe": "#1d5f6e",
        "breite": "text",
        "bild": b"",
    }


def test_vorgaben_setzen_dasselbe_wie_ohne_einstellungen(client, firma, kunde, daten):
    briefkopf_absenden(
        client, logo_datei=SimpleUploadedFile("logo.svg", LOGO, "image/svg+xml")
    )
    rechnung_schreiben(client, kunde, daten)
    b = Rechnung.objects.get().beleg
    bilder = beleg.druckbilder(Firmendaten.laden())

    mit = beleg.pdf(b, logo=bilder["logo"], kopf=bilder["kopf"], format="png")
    ohne = beleg.pdf(b, logo=bilder["logo"], format="png")
    assert mit == ohne


def test_einstellungen_speichern(client, firma):
    antwort = briefkopf_absenden(
        client,
        logo_lage="mitte",
        logo_hoehe="20",
        logo_zuschneiden="on",
        kopf_name=None,
        kopf_linie=None,
        akzentfarbe="#AA3300",
        marke="Muster Netz & Web",
    )
    assert antwort.status_code == 302

    f = Firmendaten.laden()
    assert (f.logo_lage, f.logo_hoehe, f.akzentfarbe) == ("mitte", 20, "#aa3300")
    assert f.logo_zuschneiden and f.kopf_anschrift
    assert not f.kopf_name and not f.kopf_linie
    assert f.marke == "Muster Netz & Web"


@pytest.mark.parametrize("hoehe", ["5", "21", ""])
def test_hoehe_des_logos_begrenzt(client, firma, hoehe):
    antwort = briefkopf_absenden(client, logo_hoehe=hoehe)
    assert antwort.status_code == 200
    assert Firmendaten.laden().logo_hoehe == 12


def test_farbe_muss_eine_farbe_sein(client, firma):
    antwort = briefkopf_absenden(client, akzentfarbe="rot")
    assert "Format #1d5f6e" in antwort.text
    assert Firmendaten.laden().akzentfarbe == "#1d5f6e"


def test_kopfbild_noetig_fuer_eigenes_kopfbild(client, firma):
    antwort = briefkopf_absenden(client, kopf_art="bild")
    assert "Bitte wählen Sie ein Kopfbild" in antwort.text
    assert Firmendaten.laden().kopf_art == "logo"

    kopfbild = bild(1200, 250)
    briefkopf_absenden(
        client,
        kopf_art="bild",
        kopfbild_datei=SimpleUploadedFile("kopf.png", kopfbild, "image/png"),
    )
    f = Firmendaten.laden()
    assert (f.kopf_art, bytes(f.kopfbild)) == ("bild", kopfbild)

    # Entfernen geht nur zusammen mit dem Wechsel zurück zum Logo.
    antwort = briefkopf_absenden(client, kopf_art="bild", kopfbild_entfernen="on")
    assert "Bitte wählen Sie ein Kopfbild" in antwort.text
    briefkopf_absenden(client, kopfbild_entfernen="on")
    assert bytes(Firmendaten.laden().kopfbild) == b""


# ---------- Logo und Marke (bis 0.38 unter Einstellungen) ----------


def test_logo_hochladen_und_auf_rechnung(client, firma, kunde, daten):
    briefkopf_absenden(
        client, logo_datei=SimpleUploadedFile("logo.svg", LOGO, "image/svg+xml")
    )
    assert bytes(Firmendaten.laden().logo) == LOGO
    seite = client.get(reverse("core:briefkopf")).text
    assert 'src="data:image/svg+xml;base64,' in seite

    ohne = client.get(reverse("invoicing:pdf", args=[Rechnung.objects.create().pk]))
    inhalt = rechnung_schreiben(client, kunde, daten)
    assert len(inhalt) > len(ohne.content)  # Logo als Vektorgrafik im Kopf

    # Leeres Feld behält das Logo, „entfernen“ löscht es.
    briefkopf_absenden(client)
    assert bytes(Firmendaten.laden().logo) == LOGO
    briefkopf_absenden(client, logo_entfernen="on")
    assert bytes(Firmendaten.laden().logo) == b""


def test_marke_unter_dem_firmennamen(client, firma, kunde, daten):
    briefkopf_absenden(client, marke="Muster Netz & Web")
    pdf = rechnung_schreiben(client, kunde, daten)

    assert Rechnung.objects.get().beleg["absender"]["marke"] == "Muster Netz & Web"
    assert "Muster IT\nMuster Netz & Web" in seite_1(pdf).extract_text()


def test_kaputtes_logo_abgelehnt(client, firma):
    antwort = briefkopf_absenden(
        client,
        logo_datei=SimpleUploadedFile("logo.png", b"\x89PNG kaputt", "image/png"),
    )
    assert "nicht als Bild lesen" in antwort.text
    assert bytes(Firmendaten.laden().logo) == b""


# ---------- Auf dem Beleg ----------


def test_name_und_anschrift_im_kopf_abschaltbar(client, firma, kunde, daten):
    mit = seite_1(rechnung_schreiben(client, kunde, daten)).extract_text()
    briefkopf_absenden(client, kopf_name=None, kopf_anschrift=None)
    ohne = seite_1(rechnung_schreiben(client, kunde, daten)).extract_text()

    # Rücksendeangabe und Fußzeile behalten beides.
    assert ohne.count("Muster IT") == mit.count("Muster IT") - 1 >= 2
    assert ohne.count("Gartenweg 1") == mit.count("Gartenweg 1") - 1 >= 2
    assert "post@muster.test" in ohne  # Fußzeile


@pytest.mark.parametrize("lage", ["links", "mitte", "rechts"])
def test_logo_in_jeder_lage_und_groesse(client, firma, kunde, daten, lage):
    # Sehr breit: wird schmaler gesetzt statt Name und Anschrift zu verdrängen.
    breit = bild(3000, 100)
    briefkopf_absenden(
        client,
        logo_lage=lage,
        logo_hoehe="20",
        logo_datei=SimpleUploadedFile("logo.png", breit, "image/png"),
    )
    text = seite_1(rechnung_schreiben(client, kunde, daten)).extract_text()
    assert "Muster IT" in text and "Rechnungsnummer" in text


def test_text_beginnt_nie_im_anschriftfeld(client, firma, kunde, daten):
    normal = von_oben_mm(rechnung_schreiben(client, kunde, daten), "Rechnung 26")
    briefkopf_absenden(client, kopf_name=None, kopf_anschrift=None, kopf_linie=None)
    flach = von_oben_mm(rechnung_schreiben(client, kunde, daten), "Rechnung 26")
    briefkopf_absenden(
        client,
        logo_hoehe="20",
        logo_datei=SimpleUploadedFile("logo.svg", LOGO, "image/svg+xml"),
    )
    hoch = von_oben_mm(rechnung_schreiben(client, kunde, daten), "Rechnung 26")

    # Inhalt frühestens 94 mm unter der Blattkante (20 mm Rand + 74 mm).
    assert flach > 94
    assert normal > 94
    # Ein höherer Kopf schiebt den Text nach unten, statt ihn zu überdecken.
    assert hoch > normal


def test_kopfbild_ersetzt_logo_und_angaben(client, firma, kunde, daten):
    kopfbild = bild(1240, 200)
    briefkopf_absenden(
        client,
        kopf_art="bild",
        logo_datei=SimpleUploadedFile("logo.svg", LOGO, "image/svg+xml"),
        kopfbild_datei=SimpleUploadedFile("kopf.png", kopfbild, "image/png"),
    )
    assert beleg.druckbilder(Firmendaten.laden())["logo"] == b""

    seite = seite_1(rechnung_schreiben(client, kunde, daten))
    assert [b.image.size for b in seite.images] == [(1240, 200)]
    # Firmenname nur noch in Rücksendeangabe und Fußzeile.
    assert seite.extract_text().count("Muster IT") == 2


def test_kopfbild_bis_an_den_rand(client, firma):
    briefkopf_absenden(
        client,
        kopf_art="bild",
        kopf_linie=None,
        kopfbild_datei=SimpleUploadedFile("kopf.png", bild(2480, 300), "image/png"),
    )
    # So breit wie der Text: Der Rand der Seite bleibt weiß.
    assert vorschau_bild(Firmendaten.laden()).getpixel((3, 3)) == (255, 255, 255)

    briefkopf_absenden(
        client, kopf_art="bild", kopfbild_breite="seite", kopf_linie=None
    )
    r, g, b = vorschau_bild(Firmendaten.laden()).getpixel((3, 3))
    assert r > 150 and g < 80 and b < 80


@pytest.mark.parametrize(
    "einstellung",
    [
        {"logo": LOGO, "logo_hoehe": 20},
        {"kopf_art": "bild", "kopfbild": bild(1240, 900)},
        {"kopf_art": "bild", "kopfbild": bild(2480, 2000), "kopfbild_breite": "seite"},
    ],
    ids=["logo-20mm", "kopfbild-zu-hoch", "kopfbild-seite-zu-hoch"],
)
def test_kopf_endet_vor_dem_infoblock(firma, einstellung):
    for feld, wert in einstellung.items():
        setattr(firma, feld, wert)
    firma.save()
    vorschau = vorschau_bild(Firmendaten.laden())
    zeile = lambda mm: round(mm / 25.4 * 150)  # noqa: E731 (Vorschau mit 150 ppi)

    # Die Linie endet vor 46,6 mm, der Infoblock beginnt bei 50 mm unter der Blattkante.
    streifen = vorschau.crop((0, zeile(46.6), vorschau.width, zeile(49)))
    assert streifen.getcolors() == [(streifen.width * streifen.height, (255, 255, 255))]
    # Darüber steht wirklich etwas, die Prüfung ist also nicht leer.
    oben = vorschau.crop((0, zeile(20), vorschau.width, zeile(46.6)))
    assert len(oben.getcolors(maxcolors=100_000)) > 1


def test_akzentfarbe_auf_dem_beleg(client, firma):
    briefkopf_absenden(client, akzentfarbe="#cc0000")
    vorschau = vorschau_bild(Firmendaten.laden())
    farben = {farbe for _, farbe in vorschau.getcolors(maxcolors=100_000)}
    assert any(r > 180 and g < 60 and b < 60 for r, g, b in farben)


def test_auskunft_mit_eigenem_briefkopf(firma, kunde):
    firma.kopf_art = Firmendaten.Kopfart.BILD
    firma.kopfbild = bild(1240, 200)
    firma.save()
    bilder = beleg.druckbilder(Firmendaten.laden())
    jetzt = timezone.localtime()

    pdf = datenschutz.setzen(
        datenschutz.druckdaten(
            kunde,
            datenschutz.auskunft_daten(kunde, [], jetzt),
            None,
            jetzt,
            bilder["logo"],
            bilder["kopf"],
        )
    )
    assert [b.image.size for b in seite_1(pdf).images] == [(1240, 200)]


# ---------- Weißen Rand abschneiden ----------


def test_weissen_rand_abschneiden():
    with Image.open(BytesIO(beleg.zuschneiden(bild(300, 200, rand=40)))) as b:
        assert b.size == (220, 120)
        assert b.format == "PNG"


def test_durchsichtigen_rand_abschneiden():
    daten = bild(300, 200, rand=50, modus="RGBA", grund=(0, 0, 0, 0))
    with Image.open(BytesIO(beleg.zuschneiden(daten))) as b:
        assert b.size == (200, 100)
        assert b.mode == "RGBA"


def test_jpg_bleibt_jpg():
    with Image.open(
        BytesIO(beleg.zuschneiden(bild(300, 200, rand=30, art="JPEG")))
    ) as b:
        assert b.format == "JPEG"
        # Die Kompression hinterlässt am Rand des Inhalts ein paar helle Pixel.
        assert 240 <= b.width < 260 and 140 <= b.height < 165


@pytest.mark.parametrize("daten", [LOGO, bild(100, 50), weiss(100, 50)])
def test_unveraendert_ohne_rand_oder_inhalt(daten):
    # SVG, Bild ohne Rand und ganz weißes Bild
    assert beleg.zuschneiden(daten) == daten


def test_zuschneiden_nur_auf_wunsch(firma):
    daten = bild(300, 200, rand=40)
    firma.logo = daten
    firma.save()
    assert beleg.druckbilder(Firmendaten.laden())["logo"] == daten

    firma.logo_zuschneiden = True
    firma.save()
    zugeschnitten = beleg.druckbilder(Firmendaten.laden())["logo"]
    assert Image.open(BytesIO(zugeschnitten)).size == (220, 120)
    assert bytes(Firmendaten.laden().logo) == daten  # das Original bleibt
