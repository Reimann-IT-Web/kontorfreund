"""Serienrechnungen aus einer Teilnehmerliste (Spezifikation B-11).

Die Liste hat die Form der Webinar-Listen, die Inhalte sind erfunden: Namen,
Anschriften und Nummern ausgedacht, E-Mails auf example.org, Telefonnummern aus den
Bereichen für Film und Fernsehen. Echte Listen gehören nicht ins Repository.
"""

import json
import smtplib
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail.backends import locmem
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from pypdf import PdfReader, PdfWriter

from contacts import datenschutz
from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing import beleg, versand
from invoicing.models import Rechnung
from protokoll.models import Eintrag
from serien import auswertung
from serien.models import Liste, Serie, Teilnehmer, Vorlage
from zahlungen import mahnen
from zahlungen.models import Mahnung, Zahlung

pytestmark = pytest.mark.django_db

HEUTE = date.today()
SPALTEN = [
    "Einloggzeit", "Tätig seit", "Sepa erteilt", "Kd-Nr.", "Betreuungsverein/-büro",
    "Name", "Vorname", "Anrede", "Titel", "Adresse", "PLZ", "Ort", "Telefon",
    "Handy", "FAX", "E-Mail", "Rg.nr.", "Versand", "Termin", "Thema", "Link",
    "Zertifikat Versand",
]  # fmt: skip
TERMIN = "03.12.2026, 10-13 Uhr"
THEMA = "Beispielthema: Digitale Akten in der Betreuungspraxis"
LINK = "https://example.com/webinar/beispiel-digitale-akten/100001"
# Mandate: zwei gültige, eines von 2019 ohne bekannten Einzug.
FRISCH = HEUTE - timedelta(days=400)
NEU = HEUTE - timedelta(days=90)

# sepa, kdnr, verein, name, vorname, anrede, titel, adresse, plz, ort, tel, handy, mail
TEILNEHMER = [
    (None, 9001, "Betreuungsbüro Sonnenberg", "Sonnenberg", "Petra", "Frau", None,
     "Am Mühlbach 4", 6108, "Halle (Saale)", "030 23125 101", None,
     "p.sonnenberg@example.org"),
    (None, 9002, "Betreuungsverein Musterstadt e. V.", "Lindner", "Tobias", "Herr",
     None, "Lindenallee 12", 39104, "Magdeburg", "040 66969 211", None,
     "t.lindner@example.org"),
    (None, 9002, "Betreuungsverein Musterstadt e. V.", "Albrecht", "Sabine", "Frau",
     None, "Lindenallee 12", 39104, "Magdeburg", "040 66969 213", None,
     "s.albrecht@example.org"),
    (FRISCH, 9003, "Betreuungsbüro", "Kaminski", "Jana", "Frau", None,
     "Gartenstraße 7a", 4109, "Leipzig", "089 99998 301", None,
     "kontakt@betreuung-kaminski.example.org"),
    (date(2019, 5, 12), 9004, "Kanzlei Dr. Wegener", "Wegener", "Martin", "Herr",
     "Dr.", "Schillerplatz 2", 99084, "Erfurt", "0221 4710 401", None,
     "info@kanzlei-wegener.example.org"),
    (None, 9005, "Betreuungsbüro", "Brandt", "Ulrike", "Frau", None,
     "Postfach 1234", 20095, "Hamburg", None, "0171 3920 050",
     "u.brandt@example.org"),
    (None, 9006, "Betreuungsbüro Krüger", "Krüger", "Elke", "Frau", None,
     "Weißeritzstraße 15", 1067, "Dresden", "069 90009 601", None,
     "e.krueger@example.org"),
    (NEU, 9007, "Betreuungsbüro", "Neumann", "Felix", "Herr", None,
     "Hauptstraße 88", 14467, "Potsdam", "030 23125 701", None,
     "f.neumann@example.org"),
]  # fmt: skip


def pdf_datei():
    """Eine leere PDF-Seite als Beilage."""
    schreiber = PdfWriter()
    schreiber.add_blank_page(width=595, height=842)
    ausgabe = BytesIO()
    schreiber.write(ausgabe)
    return ausgabe.getvalue()


def kleine_liste(*zeilen):
    """Liste mit wenigen Spalten: (Kd-Nr., Verein, Name, Vorname, Anrede, Adresse, Ort)."""
    mappe = Workbook()
    blatt = mappe.active
    blatt.append(["Kd-Nr.", "Betreuungsverein/-büro", "Name", "Vorname", "Anrede",
                  "Adresse", "PLZ", "Ort", "E-Mail", "Termin", "Thema"])  # fmt: skip
    for kdnr, verein, name, vorname, anrede, adresse, ort in zeilen:
        email = f"{vorname.lower()}@example.org"
        blatt.append([kdnr, verein, name, vorname, anrede, adresse, "53111", ort,
                      email, TERMIN, THEMA])  # fmt: skip
    ausgabe = BytesIO()
    mappe.save(ausgabe)
    return ausgabe.getvalue()


def teilnehmerliste(titelzeile=False):
    """Die Beispielliste als XLSX, mit allen Fallen der echten Form."""
    mappe = Workbook()
    blatt = mappe.active
    if titelzeile:
        blatt.append(["Teilnehmerliste Webinar"])
    blatt.append(SPALTEN)
    for (
        sepa,
        kdnr,
        verein,
        name,
        vorname,
        anrede,
        titel,
        adr,
        plz,
        ort,
        tel,
        handy,
        email,
    ) in TEILNEHMER:
        blatt.append(
            [None, None, sepa, kdnr, verein, name, vorname, anrede, titel, adr, plz,
             ort, tel, handy, None, email, f"09{kdnr % 100:02d}", HEUTE, TERMIN, THEMA,
             LINK, None]
        )  # fmt: skip
    for _ in range(3):  # vorausgefüllt, sonst leer
        blatt.append([None] * 18 + [TERMIN, THEMA, LINK])
    blatt.append([])
    blatt.append([None] * 4 + ['An Neu-WebinarTN "Einlogghinweise"'])
    blatt.append([])
    blatt.append([None] * 4 + ["Stornierung"])
    rot = Font(color="FF0000")
    blatt.append(
        [None, None, "15.11.26 per Mail storniert", 9008, "Betreuungsbüro", "Fischer",
         "Anke", "Frau", None, "Rosenweg 3", 18055, "Rostock", "040 66969 801", None,
         None, "a.fischer@example.org"]
    )  # fmt: skip
    blatt.append(
        ["Storno 20.11.26 wg. Krankheit", None, None, 9009, "Betreuungsbüro", "Peters",
         "Holger", "Herr", None, "Kirchgasse 9", 24103, "Kiel", "089 99998 901", None,
         None, "h.peters@example.org"]
    )  # fmt: skip
    for zelle in blatt[blatt.max_row]:
        zelle.font = rot
    blatt.append([])
    blatt.append([None] * 16 + ["0904", HEUTE])  # rot, außerhalb der Tabelle
    for zeile in blatt.iter_rows():
        for zelle in zeile:
            if isinstance(zelle.value, date):
                zelle.number_format = "DD.MM.YYYY"
    ausgabe = BytesIO()
    mappe.save(ausgabe)
    return ausgabe.getvalue()


@pytest.fixture
def firma():
    f = Firmendaten.laden()
    f.name = "Muster Seminare"
    f.inhaber = "Mara Beispiel"
    f.strasse = "Gartenweg 1"
    f.plz = "10115"
    f.ort = "Berlin"
    f.steuernummer = "12/345/67890"
    f.email = "post@seminare.test"
    f.iban = "DE02120300000000202051"
    f.umsatzsteuer = Firmendaten.Umsatzsteuer.STEUERFREI
    f.steuerfrei_hinweis = "Umsatzsteuerfrei nach § 4 Nr. 21 UStG"
    f.glaeubiger_id = "DE98ZZZ09999999999"
    f.save()
    return f


@pytest.fixture
def daten(tmp_path, settings):
    settings.DATA_DIR = tmp_path
    return tmp_path


def hochladen(client, inhalt=None):
    antwort = client.post(
        reverse("serien:hochladen"),
        {"datei": SimpleUploadedFile("Teilnehmer.xlsx", inhalt or teilnehmerliste())},
    )
    liste = Liste.objects.latest("pk")
    assert antwort.url == reverse("serien:vorschau", args=[liste.pk])
    return liste


def vorschau_formular(antwort, **mehr):
    """Was die Vorschau abschicken würde, mit ihren Vorschlägen."""
    ctx = antwort.context
    werte = {
        "termin": TERMIN,
        "thema": THEMA,
        "link": LINK,
        "leistungsdatum": "2026-12-03",
        "datum": HEUTE.isoformat(),
        "preis": "89,00",
        "zahlungsziel": "14",
    }
    for f in ctx["zuordnung_form"]:
        werte[f.html_name] = f.value() or ""
    werte["gezeigt"] = [str(z.nr) for z in ctx["teilnehmer"]]
    werte["waehlen"] = [str(z.nr) for z in ctx["teilnehmer"] if z.waehlen]
    werte["beilage"] = [str(z.nr) for z in ctx["teilnehmer"] if z.beilage]
    werte["uebernehmen"] = [str(z.nr) for z in ctx["teilnehmer"] if z.uebernehmen]
    for z in ctx["teilnehmer"]:
        werte[f"zahlweg_{z.nr}"] = z.zahlweg
    werte["aktion"] = "anlegen"
    return {**werte, **mehr}


def serie_anlegen(client, inhalt=None, **mehr):
    liste = hochladen(client, inhalt)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))
    client.post(
        reverse("serien:vorschau", args=[liste.pk]), vorschau_formular(antwort, **mehr)
    )
    return Serie.objects.latest("pk")


def test_vorschau_erkennt_teilnehmer_und_fallen(client, firma):
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))

    a = antwort.context["auswertung"]
    assert [z.werte["name"] for z in a.teilnehmer] == [t[3] for t in TEILNEHMER]
    assert a.leere == 3
    assert [z.grund for z in a.uebersprungen] == [
        "storniert (Abschnitt „Stornierung“)",
        "storniert (Abschnitt „Stornierung“)",
        "ohne Namen",
    ]
    # Termin, Thema und Link aus der Liste, das Leistungsdatum aus dem Termin.
    angaben = antwort.context["angaben"]
    assert angaben["termin"].value() == TERMIN
    assert angaben["leistungsdatum"].value() == date(2026, 12, 3)
    zahlwege = {z.kdnr: z.zahlweg for z in a.teilnehmer}
    assert zahlwege == {
        9001: "ueberweisung",
        9002: "ueberweisung",
        9003: "lastschrift",
        9004: "ueberweisung",
        9005: "ueberweisung",
        9006: "ueberweisung",
        9007: "lastschrift",
    }
    wegener = next(z for z in a.teilnehmer if z.kdnr == 9004)
    assert wegener.lastschrift_moeglich
    assert any("unterschrieben am 12.05.2019" in h for h in wegener.hinweise)
    assert [z.daten["plz"] for z in a.teilnehmer][:4] == [
        "06108",
        "39104",
        "39104",
        "04109",
    ]
    assert all(z.waehlen for z in a.teilnehmer)
    seite = antwort.content.decode()
    assert "Angelegt ist noch nichts" in seite
    assert "Fischer" in seite  # übersprungen, aber genannt


def test_entwuerfe_anlegen(client, firma, daten):
    serie = serie_anlegen(client)

    assert not Liste.objects.exists()  # die Datei bleibt nicht liegen
    teilnehmer = list(serie.teilnehmer.order_by("zeile"))
    assert len(teilnehmer) == 8
    assert Kontakt.objects.count() == 7  # 9002 ist ein Verein mit zwei Teilnehmern
    # Stornos speichert Kontorfreund nicht, auch nicht den Grund.
    assert not Kontakt.objects.filter(nachname__in=["Fischer", "Peters"]).exists()
    assert not Rechnung.objects.filter(kopftext__icontains="Krankheit").exists()

    verein = Kontakt.objects.get(nummer=9002)
    assert verein.art == Kontakt.Art.FIRMA
    assert verein.nachname == "Lindner"  # erster Teilnehmer als Ansprechpartner
    albrecht = next(t for t in teilnehmer if t.nachname == "Albrecht")
    r = albrecht.rechnung
    assert r.kontakt == verein
    assert r.email_an == "s.albrecht@example.org"
    assert r.kopftext.startswith("Sehr geehrte Frau Albrecht,")
    assert r.status == Rechnung.Status.ENTWURF
    assert r.steuerfall == Rechnung.Steuerfall.STEUERFREI
    position = r.positionen.get()
    assert position.bezeichnung == f"Teilnahme an „{THEMA}“ am {TERMIN}"
    assert position.preis == Decimal("89.00") and position.einheit == ""
    assert r.leistung_von == date(2026, 12, 3)
    assert LINK in r.fusstext and "Mara Beispiel" in r.fusstext

    assert Kontakt.objects.get(nummer=9001).plz == "06108"
    assert Kontakt.objects.get(nummer=9006).plz == "01067"
    kaminski = Kontakt.objects.get(nummer=9003)
    assert (kaminski.mandat_referenz, kaminski.mandat_datum) == ("9003", FRISCH)
    assert kaminski.rechnungen.get().zahlweg == Rechnung.Zahlweg.LASTSCHRIFT
    wegener = next(t for t in teilnehmer if t.nachname == "Wegener").rechnung
    assert wegener.kopftext.startswith("Sehr geehrter Herr Dr. Wegener,")
    assert wegener.zahlweg == Rechnung.Zahlweg.UEBERWEISUNG

    vorlage = Vorlage.laden()
    assert vorlage.preis == Decimal("89.00")
    assert vorlage.zuordnung["name"] == "Name"


def test_festschreiben_in_der_reihenfolge_der_liste(client, firma, daten):
    serie = serie_anlegen(client)
    # Ein gelöschter Entwurf erzeugt keine Lücke.
    serie.teilnehmer.get(nachname="Brandt").rechnung.delete()

    antwort = client.post(reverse("serien:festschreiben", args=[serie.pk]), follow=True)

    rechnungen = [t.rechnung for t in serie.teilnehmer.order_by("zeile")]
    assert [r.nummer for r in rechnungen] == [f"26000{i}" for i in range(1, 8)]
    assert (
        "7 Rechnungen festgeschrieben (260001 bis 260007)" in antwort.content.decode()
    )
    albrecht = serie.teilnehmer.get(nachname="Albrecht").rechnung
    assert albrecht.beleg["empfaenger"]["zeilen"] == [
        "Betreuungsverein Musterstadt e. V.",
        "Frau Sabine Albrecht",
        "Lindenallee 12",
        "39104 Magdeburg",
    ]
    text = PdfReader(BytesIO((daten / albrecht.datei).read_bytes())).pages[0]
    assert "Frau Sabine Albrecht" in text.extract_text()
    kaminski = serie.teilnehmer.get(nachname="Kaminski").rechnung
    assert kaminski.beleg["lastschrift"]["mandat"] == "9003"
    assert kaminski.beleg["girocode"] is False


def test_fehlende_angaben_halten_nur_diese_rechnung_auf(client, firma, daten):
    serie = serie_anlegen(client)
    entwurf = serie.teilnehmer.get(nachname="Krüger").rechnung
    entwurf.positionen.all().delete()

    antwort = client.post(reverse("serien:festschreiben", args=[serie.pk]), follow=True)

    entwurf.refresh_from_db()
    assert entwurf.ist_entwurf
    assert serie.teilnehmer.exclude(rechnung__status="entwurf").count() == 7
    assert "Krüger: Noch nicht vollständig: Menge und Art der Leistung" in (
        antwort.content.decode()
    )


def test_dieselbe_liste_ein_zweites_mal(client, firma, daten):
    serie_anlegen(client)
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))

    teilnehmer = antwort.context["teilnehmer"]
    assert not any(z.waehlen for z in teilnehmer)
    assert all(
        "schon eine Rechnung zu diesem Termin" in " ".join(z.hinweise)
        for z in teilnehmer
    )
    assert all(z.kontakt for z in teilnehmer)


def test_abweichende_anschrift_wird_auf_wunsch_uebernommen(client, firma, daten):
    alt = Kontakt.objects.create(
        nummer=9006,
        art=Kontakt.Art.FIRMA,
        firmenname="Betreuungsbüro Krüger",
        vorname="Elke",
        nachname="Krüger",
        strasse="Alte Straße 1",
        plz="01067",
        ort="Dresden",
        archiviert=True,
    )
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))
    z = next(z for z in antwort.context["teilnehmer"] if z.kdnr == 9006)
    assert [(a[1], a[2], a[3]) for a in z.abweichungen] == [
        ("Adresse", "Weißeritzstraße 15", "Alte Straße 1"),
        ("E-Mail", "e.krueger@example.org", ""),
    ]
    assert z.uebernehmen

    client.post(reverse("serien:vorschau", args=[liste.pk]), vorschau_formular(antwort))
    alt.refresh_from_db()
    assert alt.strasse == "Weißeritzstraße 15"
    assert alt.email == "e.krueger@example.org"
    assert not alt.archiviert


def test_ohne_glaeubiger_id_keine_lastschrift(client, firma):
    firma.glaeubiger_id = ""
    firma.save()
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))

    assert {z.zahlweg for z in antwort.context["teilnehmer"]} == {"ueberweisung"}
    assert not any(z.lastschrift_moeglich for z in antwort.context["teilnehmer"])
    assert "Ihre Gläubiger-ID fehlt" in antwort.content.decode()


def test_wahl_der_vorschau_gilt(client, firma, daten):
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))
    formular = vorschau_formular(antwort)
    neumann = next(z.nr for z in antwort.context["teilnehmer"] if z.kdnr == 9007)
    wegener = next(z.nr for z in antwort.context["teilnehmer"] if z.kdnr == 9004)
    formular["waehlen"].remove(str(neumann))
    formular[f"zahlweg_{wegener}"] = "lastschrift"  # Mandat ist doch noch gültig
    client.post(reverse("serien:vorschau", args=[liste.pk]), formular)

    serie = Serie.objects.get()
    assert not serie.teilnehmer.filter(nachname="Neumann").exists()
    assert (
        serie.teilnehmer.get(nachname="Wegener").rechnung.zahlweg
        == Rechnung.Zahlweg.LASTSCHRIFT
    )


def test_ohne_preis_wird_nichts_angelegt(client, firma):
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))
    antwort = client.post(
        reverse("serien:vorschau", args=[liste.pk]),
        vorschau_formular(antwort, preis=""),
    )
    assert "Bitte die markierten Angaben prüfen." in antwort.content.decode()
    assert not Serie.objects.exists() and not Rechnung.objects.exists()


def test_ueberschriften_unter_einer_titelzeile(client, firma):
    liste = hochladen(client, teilnehmerliste(titelzeile=True))
    assert liste.spalten[:4] == ["Einloggzeit", "Tätig seit", "Sepa erteilt", "Kd-Nr."]


def test_gespeicherte_zuordnung_geht_vor():
    spalten = ["Kunde", "Nachname", "E-Mail"]
    assert auswertung.vorschlagen(spalten) == {"name": "Nachname", "email": "E-Mail"}
    assert auswertung.vorschlagen(spalten, {"kdnr": "Kunde", "ort": "Fehlt"}) == {
        "name": "Nachname",
        "email": "E-Mail",
        "kdnr": "Kunde",
    }


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("03.02.2025", date(2025, 2, 3)),
        ("3.2.25", date(2025, 2, 3)),
        ("03.02.2025 00:00", date(2025, 2, 3)),
        ("15.11.26 per Mail storniert", None),
        ("31.02.2025", None),
        ("ja", None),
    ],
)
def test_sepa_datum(text, erwartet):
    assert auswertung.datum_lesen(text) == erwartet


@pytest.fixture
def postfach(monkeypatch, firma):
    monkeypatch.setattr(versand, "SmtpVersand", lambda **_: locmem.EmailBackend())
    firma.mail_server = "smtp.seminare.test"
    firma.save()


def test_alle_senden_mit_beilage(client, firma, daten, postfach):
    vorlage = Vorlage.laden()
    vorlage.beilage = pdf_datei()
    vorlage.beilage_name = "Hinweise.pdf"
    vorlage.save()
    serie = serie_anlegen(client)
    client.post(reverse("serien:festschreiben", args=[serie.pk]))

    antwort = client.post(
        reverse("serien:senden", args=[serie.pk]), {"kopie": "on"}, follow=True
    )

    assert "8 Rechnungen per E-Mail gesendet" in antwort.content.decode()
    assert len(mail.outbox) == 8
    an_albrecht = next(m for m in mail.outbox if m.to == ["s.albrecht@example.org"])
    assert an_albrecht.body.startswith("Sehr geehrte Frau Albrecht,")
    assert an_albrecht.bcc == ["post@seminare.test"]
    nummer = serie.teilnehmer.get(nachname="Albrecht").rechnung.nummer
    assert an_albrecht.subject == f"Rechnung {nummer} – {THEMA}"
    assert [a[0] for a in an_albrecht.attachments] == [
        f"Rechnung-{nummer}.pdf",
        "Hinweise.pdf",
    ]
    assert not serie.teilnehmer.filter(rechnung__versendet_am__isnull=True).exists()
    # Ein zweiter Klick sendet nichts doppelt.
    client.post(reverse("serien:senden", args=[serie.pk]))
    assert len(mail.outbox) == 8


def test_ein_fehler_beim_senden_haelt_die_anderen_nicht_auf(
    client, firma, daten, postfach, monkeypatch
):
    serie = serie_anlegen(client)
    client.post(reverse("serien:festschreiben", args=[serie.pk]))
    echt = versand.senden

    def senden(beleg, firma, an, *args, **kwargs):
        if an == "u.brandt@example.org":
            raise smtplib.SMTPRecipientsRefused({an: (550, b"unbekannt")})
        return echt(beleg, firma, an, *args, **kwargs)

    monkeypatch.setattr(versand, "senden", senden)
    antwort = client.post(reverse("serien:senden", args=[serie.pk]), follow=True)

    assert len(mail.outbox) == 7
    assert "Zeile 7, Ulrike Brandt:" in antwort.content.decode()
    assert serie.teilnehmer.get(nachname="Brandt").rechnung.versendet_am is None


def test_ohne_e_mail_zum_drucken(client, firma, daten):
    vorlage = Vorlage.laden()
    serie = serie_anlegen(client)
    brandt = serie.teilnehmer.get(nachname="Brandt")
    Teilnehmer.objects.filter(pk=brandt.pk).update(email="")
    Kontakt.objects.filter(pk=brandt.rechnung.kontakt_id).update(email="")
    client.post(reverse("serien:festschreiben", args=[serie.pk]))
    vorlage.save()

    antwort = client.get(reverse("serien:drucken", args=[serie.pk]))

    assert antwort["Content-Type"] == "application/pdf"
    pdf = PdfReader(BytesIO(antwort.content))
    assert "Ulrike Brandt" in pdf.pages[0].extract_text()


def test_lastschriften_eingezogen_buchen(client, firma, daten):
    serie = serie_anlegen(client, datum=(HEUTE - timedelta(days=20)).isoformat())
    client.post(reverse("serien:festschreiben", args=[serie.pk]))

    client.post(reverse("serien:eingezogen", args=[serie.pk]))

    zahlungen = Zahlung.objects.filter(art=Zahlung.Art.LASTSCHRIFT)
    assert sorted(z.rechnung.kontakt.nummer for z in zahlungen) == [9003, 9007]
    faellig = HEUTE - timedelta(days=6)
    assert {z.datum for z in zahlungen} == {faellig}
    assert Kontakt.objects.get(nummer=9003).mandat_zuletzt == faellig
    # Nichts doppelt.
    client.post(reverse("serien:eingezogen", args=[serie.pk]))
    assert zahlungen.count() == 2


def test_uebersicht_als_excel(client, firma, daten):
    serie = serie_anlegen(client)
    client.post(reverse("serien:festschreiben", args=[serie.pk]))

    antwort = client.get(reverse("serien:serie", args=[serie.pk]), {"format": "xlsx"})

    blatt = load_workbook(BytesIO(antwort.content)).active
    zeilen = list(blatt.iter_rows(values_only=True))
    assert zeilen[0][:4] == ("Zeile der Liste", "Kd-Nr.", "Name", "Rechnungsnummer")
    assert zeilen[1][1:5] == ("9001", "Petra Sonnenberg", "260001", 89)
    assert zeilen[4][5] == "SEPA-Lastschrift"


def test_seiten_der_serie(client, firma, daten):
    serie = serie_anlegen(client)
    for adresse in (
        reverse("serien:liste"),
        reverse("serien:serie", args=[serie.pk]),
        reverse("serien:vorlage"),
    ):
        assert client.get(adresse).status_code == 200


def test_vorlage_prueft_platzhalter_und_beilage(client):
    werte = {
        "betreff": "Rechnung {nummer}",
        "position": "Teilnahme am {termin}",
        "kopftext": "",
        "fusstext": "",
        "mail_betreff": "Rechnung {nummer}",
        "mail_text": "Anbei {nummer}.",
        "beilage_datei": SimpleUploadedFile("hinweise.txt", b"kein PDF"),
    }
    antwort = client.post(reverse("serien:vorlage"), werte)
    seite = antwort.content.decode()
    assert "kennt Kontorfreund hier nicht: {nummer}" in seite
    assert "Bitte eine PDF-Datei wählen." in seite

    werte["betreff"] = "Rechnung für {termin}"
    werte["beilage_datei"] = SimpleUploadedFile("Hinweise.pdf", b"%PDF-1.4 kaputt")
    antwort = client.post(reverse("serien:vorlage"), werte)
    assert "lässt sich nicht lesen" in antwort.content.decode()
    werte["beilage_datei"] = SimpleUploadedFile("Hinweise.pdf", pdf_datei())
    client.post(reverse("serien:vorlage"), werte)
    vorlage = Vorlage.laden()
    assert (vorlage.betreff, vorlage.beilage_name) == (
        "Rechnung für {termin}",
        "Hinweise.pdf",
    )
    assert bytes(vorlage.beilage) == pdf_datei()


def test_liste_gehoert_dem_der_sie_hochlud(client, firma, django_user_model):
    liste = hochladen(client)
    liste.benutzer = django_user_model.objects.create_user(
        email="mitarbeiter@seminare.test", password="x" * 16
    )
    liste.save()
    assert client.get(reverse("serien:vorschau", args=[liste.pk])).status_code == 404


@pytest.mark.parametrize(
    ("text", "storniert"),
    [
        ("Storno 20.11.26 wg. Krankheit", True),
        ("15.11.26 per Mail storniert", True),
        ("Stornierung", True),
        ("storn. am 3.11.", True),
        ("Storndorf", False),  # ein Ort in Hessen
        ("Am Stornbach 2", False),
    ],
)
def test_storno_erkennen(text, storniert):
    assert bool(auswertung.STORNO.search(text)) == storniert


def test_kd_nr_eines_anderen_kunden_wird_nicht_ueberschrieben(client, firma, daten):
    fremd = Kontakt.objects.create(
        nummer=9001,
        art=Kontakt.Art.PERSON,
        nachname="Fremd",
        strasse="Andere Straße 1",
        plz="10115",
        ort="Berlin",
    )
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))
    z = next(z for z in antwort.context["teilnehmer"] if z.kdnr == 9001)

    assert not z.waehlen and not z.uebernehmen
    assert any("gehört in Kontorfreund zu „Fremd“" in h for h in z.hinweise)

    client.post(reverse("serien:vorschau", args=[liste.pk]), vorschau_formular(antwort))
    fremd.refresh_from_db()
    assert (fremd.nachname, fremd.strasse) == ("Fremd", "Andere Straße 1")
    assert not fremd.rechnungen.exists()
    assert Serie.objects.get().teilnehmer.count() == 7


def test_alter_fehler_an_einer_adresse_haelt_die_serie_nicht_auf(client, firma, daten):
    Kontakt.objects.create(
        nummer=9006,
        art=Kontakt.Art.FIRMA,
        firmenname="Betreuungsbüro Krüger",
        vorname="Elke",
        nachname="Krüger",
        strasse="Alte Straße 1",
        ust_id="DE1",  # ungültig, aus einer älteren Version
    )
    serie = serie_anlegen(client)

    assert serie.teilnehmer.count() == 8
    assert Kontakt.objects.get(nummer=9006).strasse == "Weißeritzstraße 15"


def test_storno_und_mahnung_gehen_an_den_teilnehmer(client, firma, daten):
    serie = serie_anlegen(client)
    client.post(reverse("serien:festschreiben", args=[serie.pk]))
    original = serie.teilnehmer.get(nachname="Albrecht").rechnung

    betrag = Decimal("89.00")
    mahnung = Mahnung(
        rechnung=original,
        stufe=1,
        frist=HEUTE + timedelta(days=7),
        offen=betrag,
        gesamt=betrag,
    )
    vorschlag = mahnen.mail_vorschlag(mahnung, firma)
    assert vorschlag["an"] == "s.albrecht@example.org"
    assert vorschlag["text"].startswith("Sehr geehrte Frau Albrecht,")

    client.post(reverse("invoicing:stornieren", args=[original.pk]))
    storno = Rechnung.objects.get(storno_zu=original)
    assert "Frau Sabine Albrecht" in storno.beleg["empfaenger"]["zeilen"]
    assert storno.kopftext.startswith("Sehr geehrte Frau Albrecht,")
    assert storno.email_an == "s.albrecht@example.org"


def test_editor_nennt_den_teilnehmer(client, firma, daten):
    serie = serie_anlegen(client)
    entwurf = serie.teilnehmer.get(nachname="Albrecht").rechnung

    seite = client.get(reverse("invoicing:bearbeiten", args=[entwurf.pk]))
    assert "zu Händen Frau Sabine Albrecht" in seite.content.decode()


def test_loeschung_auf_verlangen_schwaerzt_auch_die_teilnehmer(client, firma, daten):
    serie_anlegen(client)
    verein = Kontakt.objects.get(nummer=9002)
    daten_vorher = datenschutz.auskunft_daten(
        verein, datenschutz.belege(verein), timezone.now()
    )
    assert [t["Name"] for t in daten_vorher["Teilnehmer"]] == [
        "Tobias Lindner",
        "Sabine Albrecht",
    ]

    datenschutz.loeschen(verein)

    assert not Teilnehmer.objects.filter(nachname__in=["Lindner", "Albrecht"]).exists()
    inhalt = json.dumps(
        list(Eintrag.objects.values("beschreibung", "aenderungen")),
        ensure_ascii=False,
    )
    for spur in ("Albrecht", "Lindner", "s.albrecht@example.org"):
        assert spur not in inhalt, spur


def test_zeilenumbruch_in_termin_und_thema(client, firma, daten, postfach):
    serie = serie_anlegen(
        client, termin="03.12.2026,\r\n10-13 Uhr", thema="Digitale\nAkten"
    )
    assert (serie.termin, serie.thema) == ("03.12.2026, 10-13 Uhr", "Digitale Akten")
    client.post(reverse("serien:festschreiben", args=[serie.pk]))
    client.post(reverse("serien:senden", args=[serie.pk]))
    assert len(mail.outbox) == 8
    assert all("\n" not in m.subject for m in mail.outbox)


def test_abweichendes_mandatsdatum_wird_genannt(client, firma):
    Kontakt.objects.create(
        nummer=9003,
        art=Kontakt.Art.FIRMA,
        firmenname="Betreuungsbüro",
        vorname="Jana",
        nachname="Kaminski",
        mandat_referenz="9003",
        mandat_datum=date(2024, 1, 2),
    )
    liste = hochladen(client)
    antwort = client.get(reverse("serien:vorschau", args=[liste.pk]))
    z = next(z for z in antwort.context["teilnehmer"] if z.kdnr == 9003)
    assert any("Mandat vom 02.01.2024" in h for h in z.hinweise)


def test_neue_adresse_ohne_kd_nr_nimmt_keine_nummer_der_liste(client, firma, daten):
    Kontakt.objects.create(nummer=9001, firmenname="Vorhanden")
    inhalt = kleine_liste(
        (9002, "", "Albers", "Anna", "Frau", "Weg 1", "Bonn"),
        (None, "", "Berger", "Bert", "Herr", "Weg 2", "Bonn"),
        (9003, "", "Conrad", "Clara", "Frau", "Weg 3", "Bonn"),
    )
    serie = serie_anlegen(client, inhalt)

    assert serie.teilnehmer.count() == 3
    nummern = {k.nachname: k.nummer for k in Kontakt.objects.exclude(nummer=9001)}
    assert nummern == {"Albers": 9002, "Conrad": 9003, "Berger": 9004}


def test_verein_ohne_kd_nr_wird_eine_adresse(client, firma, daten):
    vorhanden = Kontakt.objects.create(firmenname="BV Alt", ort="Bonn")
    inhalt = kleine_liste(
        (None, "BV Alt", "Erst", "Eva", "Frau", "Ring 1", "Bonn"),
        (None, "BV Alt", "Zweit", "Zoe", "Frau", "Ring 1", "Bonn"),
        (None, "BV Neu", "Dritt", "Dora", "Frau", "Ring 2", "Bonn"),
        (None, "BV Neu", "Viert", "Vera", "Frau", "Ring 2", "Bonn"),
    )
    serie = serie_anlegen(client, inhalt)

    assert serie.teilnehmer.count() == 4
    vorhanden.refresh_from_db()
    assert vorhanden.nachname == "Erst"  # der erste Teilnehmer, nicht der letzte
    assert vorhanden.rechnungen.count() == 2
    neu = Kontakt.objects.get(firmenname="BV Neu")
    assert neu.rechnungen.count() == 2


def test_stornierte_rechnung_wird_nicht_gesendet_die_kopie_schon(
    client, firma, daten, postfach
):
    serie = serie_anlegen(client)
    client.post(reverse("serien:festschreiben", args=[serie.pk]))
    original = serie.teilnehmer.get(nachname="Albrecht").rechnung
    client.post(reverse("invoicing:stornieren", args=[original.pk]), {"kopie": "on"})

    kopie = Rechnung.objects.filter(status="entwurf").get()
    assert kopie.teilnehmer_daten.nachname == "Albrecht"
    assert kopie.email_an == "s.albrecht@example.org"
    assert (
        "Frau Sabine Albrecht"
        in beleg.beleg_daten(kopie, firma, "")["empfaenger"]["zeilen"]
    )
    client.post(reverse("serien:festschreiben", args=[serie.pk]))
    client.post(reverse("serien:senden", args=[serie.pk]))

    an_albrecht = [m for m in mail.outbox if m.to == ["s.albrecht@example.org"]]
    kopie.refresh_from_db()
    assert [m.subject for m in an_albrecht] == [f"Rechnung {kopie.nummer} – {THEMA}"]
    assert len(mail.outbox) == 8


def test_betrag_in_der_position(client, firma, daten):
    vorlage = Vorlage.laden()
    vorlage.position = "Teilnahme an {thema} ({betrag})"
    vorlage.save()
    serie = serie_anlegen(client)

    position = serie.teilnehmer.first().rechnung.positionen.get()
    assert "{betrag}" not in position.bezeichnung
    assert "89,00" in position.bezeichnung


def test_rechnungstexte_kennen_kein_datum(client):
    werte = {
        "betreff": "Rechnung vom {datum}",
        "position": "Teilnahme",
        "kopftext": "",
        "fusstext": "Einzug am {faellig}",
        "mail_betreff": "Rechnung {nummer} vom {datum}",
        "mail_text": "Fällig am {faellig}.",
    }
    seite = client.post(reverse("serien:vorlage"), werte).content.decode()
    assert "kennt Kontorfreund hier nicht: {datum}" in seite
    assert "kennt Kontorfreund hier nicht: {faellig}" in seite
    werte.update(betreff="Rechnung", fusstext="")
    client.post(reverse("serien:vorlage"), werte)
    assert Vorlage.laden().mail_betreff == "Rechnung {nummer} vom {datum}"
