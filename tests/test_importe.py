"""Import von Adressen und Artikeln (Spezifikation M-6) – mit erfundenen Daten."""

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from artikel.models import Artikel
from auswertungen import tabelle
from contacts.models import Kontakt
from importe import lesen, uebernahme, vorlagen
from importe.models import Import, Zuordnung
from konten.models import Benutzer
from protokoll.models import Eintrag

pytestmark = pytest.mark.django_db


def xlsx(zeilen):
    mappe = Workbook()
    for zeile in zeilen:
        mappe.active.append(zeile)
    ausgabe = BytesIO()
    mappe.save(ausgabe)
    return ausgabe.getvalue()


def ods_datei(content):
    ausgabe = BytesIO()
    with zipfile.ZipFile(ausgabe, "w") as archiv:
        archiv.writestr(
            "mimetype", tabelle.TYPEN["ods"], compress_type=zipfile.ZIP_STORED
        )
        archiv.writestr("content.xml", content)
    return ausgabe.getvalue()


def hochladen(client, inhalt, name="liste.csv", ziel="adressen"):
    return client.post(
        reverse(f"importe:{ziel}"), {"datei": SimpleUploadedFile(name, inhalt)}
    )


def bestaetigen(client, imp, **mehr):
    """Die vorgeschlagene Zuordnung so absenden, wie das Formular sie zeigt."""
    daten = {f"spalte_{feld}": spalte for feld, spalte in imp.zuordnung.items()}
    return client.post(
        reverse("importe:zuordnen", args=[imp.pk]),
        {"kategorie": "kunde", "dubletten_anlegen": "", **daten, **mehr},
    )


# ---------- Dateien lesen ----------


def test_csv_aus_excel_in_windows_1252():
    inhalt = (
        "Firma;Vorname;Nachname;PLZ;Ort\r\n"
        "Bäckerei Korn;;;1067;Dresden\r\n"
        ";;;;\r\n"
        ";Lea;Sommer;55116;Mainz\r\n"
    ).encode("cp1252")

    spalten, zeilen = lesen.lesen(inhalt)

    assert spalten == ["Firma", "Vorname", "Nachname", "PLZ", "Ort"]
    assert zeilen == [
        [2, ["Bäckerei Korn", "", "", "1067", "Dresden"]],
        [4, ["", "Lea", "Sommer", "55116", "Mainz"]],
    ]


def test_csv_utf8_mit_komma_zeilenumbruch_und_formelschutz():
    inhalt = (
        '﻿Name,Name,Notiz,\n"Korn, Bäckerei",zwei,"Zeile eins\nZeile zwei",\n'
        "x,'=1+1,'Hallo,\n"
    ).encode()

    spalten, zeilen = lesen.lesen(inhalt)

    assert spalten == ["Name", "Name (2)", "Notiz"], "leere Spalte am Ende fällt weg"
    assert zeilen[0] == [2, ["Korn, Bäckerei", "zwei", "Zeile eins\nZeile zwei"]]
    assert zeilen[1][1][1:] == ["=1+1", "'Hallo"], (
        "nur das Hochkomma vor Formeln fällt weg"
    )


def test_xlsx_mit_zahlen_und_datum():
    inhalt = xlsx(
        [
            [],
            ["Bezeichnung", "Preis", "PLZ", "Seit"],
            ["Wartung", 12.5, 1067, date(2026, 1, 31)],
            ["Beratung", 0.1 + 0.2, 55116.0, None],
        ]
    )

    spalten, zeilen = lesen.lesen(inhalt)

    assert spalten == ["Bezeichnung", "Preis", "PLZ", "Seit"]
    assert zeilen[0] == [3, ["Wartung", "12,5", "1067", "31.01.2026"]]
    assert zeilen[1] == [4, ["Beratung", "0,3", "55116", ""]]


def test_ods_aus_eigenem_export():
    inhalt = tabelle.ods(
        [("Name", "text"), ("Preis", "betrag"), ("Datum", "datum")],
        [
            ["Wartung", Decimal("12.50"), date(2026, 1, 31)],
            [None, None, None],
            ["B", None, None],
        ],
        "Artikel",
    )

    spalten, zeilen = lesen.lesen(inhalt)

    assert spalten == ["Name", "Preis", "Datum"]
    assert zeilen == [[2, ["Wartung", "12,5", "31.01.2026"]], [4, ["B", "", ""]]]


def test_ods_mit_wiederholten_zellen_leerzeichen_und_kommentar():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
<office:body><office:spreadsheet><table:table table:name="A">
<table:table-row><table:table-cell office:value-type="string"><text:p>A</text:p></table:table-cell>
<table:table-cell table:number-columns-repeated="2"/><table:table-cell office:value-type="string"><text:p>D</text:p></table:table-cell>
<table:table-cell table:number-columns-repeated="16380"/></table:table-row>
<table:table-row><table:table-cell office:value-type="string"><office:annotation><text:p>Kommentar</text:p></office:annotation><text:p>zwei<text:s text:c="3"/>Leer</text:p><text:p>zeilen</text:p></table:table-cell>
<table:table-cell table:number-columns-repeated="2" office:value-type="string"><text:p>x</text:p></table:table-cell></table:table-row>
<table:table-row table:number-rows-repeated="1048570"><table:table-cell table:number-columns-repeated="16384"/></table:table-row>
</table:table></office:spreadsheet></office:body></office:document-content>"""

    spalten, zeilen = lesen.lesen(ods_datei(content))

    assert spalten == ["A", "Spalte 2", "Spalte 3", "D"]
    assert zeilen == [[2, ["zwei   Leer\nzeilen", "x", "x", ""]]]


def _xlsx_mit_dtd():
    quelle = zipfile.ZipFile(BytesIO(xlsx([["a"], ["b"]])))
    ausgabe = BytesIO()
    with zipfile.ZipFile(ausgabe, "w") as ziel:
        for teil in quelle.infolist():
            inhalt = quelle.read(teil)
            if teil.filename == "xl/worksheets/sheet1.xml":
                kopf, _, rest = (
                    inhalt.partition(b"?>")
                    if inhalt.startswith(b"<?xml")
                    else (b"", b"", inhalt)
                )
                inhalt = kopf + _ + b'<!DOCTYPE x [<!ENTITY a "b">]>' + rest
            ziel.writestr(teil, inhalt)
    return ausgabe.getvalue()


@pytest.mark.parametrize(
    ("inhalt", "meldung"),
    [
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", "alte Excel-Format"),
        (
            ods_datei('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>'),
            "Dokumenttyp-Definition",
        ),
        (_xlsx_mit_dtd(), "Dokumenttyp-Definition"),
        (b"PK\x03\x04kaputt", "beschädigt"),
        (b"\n;;\n", "leer"),
        (b"Name;Ort\n", "keine Zeilen"),
        (b"Name\x00\x01\x02", "weder eine CSV-Datei"),
    ],
)
def test_unlesbare_dateien(inhalt, meldung):
    with pytest.raises(lesen.Unlesbar, match=meldung):
        lesen.lesen(inhalt)


def test_grenzen(monkeypatch):
    monkeypatch.setattr(lesen, "ZEILEN", 2)
    with pytest.raises(lesen.Unlesbar, match="mehr als 2 Zeilen"):
        lesen.lesen(b"Name\na\nb\nc\n")
    monkeypatch.setattr(lesen, "ENTPACKT", 100)
    with pytest.raises(lesen.Unlesbar, match="größer als 100 MB"):
        lesen.lesen(xlsx([["a"], ["b"]]))


# ---------- Vorlagen ----------


def test_vorlagen_erkennen():
    from contacts.views import EXPORT

    name, zuordnung = vorlagen.vorschlagen("kontakte", [t for t, _ in EXPORT], [])
    assert name == "Kontorfreund"
    assert zuordnung["firmenname"] == "Name" and zuordnung["xrechnung"] == "XRechnung"

    lexware = [
        "Kundennummer",
        "Firmenname",
        "Anrede",
        "Vorname",
        "Nachname",
        "Notiz",
        "Straße (Rechnungsadresse)",
        "Ort (Rechnungsadresse)",
        "PLZ (Rechnungsadresse)",
        "Land (Rechnungsadresse)",
        "Geschäftlich (Rufnummer)",
        "Geschäftlich (E-Mail)",
        "IBAN",
    ]
    name, zuordnung = vorlagen.vorschlagen("kontakte", lexware, [])
    assert name == "Lexware Office"
    assert zuordnung["strasse"] == "Straße (Rechnungsadresse)"
    assert zuordnung["email"] == "Geschäftlich (E-Mail)"

    allgemein = [
        "Firma",
        "Straße",
        "Hausnummer",
        "postleitzahl",
        "Ort",
        "E-Mail-Adresse",
    ]
    name, zuordnung = vorlagen.vorschlagen("kontakte", allgemein, [])
    assert name == ""
    assert zuordnung == {
        "firmenname": "Firma",
        "strasse": "Straße",
        "hausnummer": "Hausnummer",
        "plz": "postleitzahl",
        "ort": "Ort",
        "email": "E-Mail-Adresse",
    }

    eigene = Zuordnung.objects.create(
        ziel="kontakte",
        name="Altprogramm",
        felder={"firmenname": "Firma", "ort": "Ort"},
    )
    name, zuordnung = vorlagen.vorschlagen("kontakte", allgemein, [eigene])
    assert name == "Altprogramm" and zuordnung["plz"] == "postleitzahl"


# ---------- Probelauf und Übernahme ----------


def _import(inhaber, ziel, inhalt, **mehr):
    spalten, zeilen = lesen.lesen(inhalt)
    _, zuordnung = vorlagen.vorschlagen(ziel, spalten, [])
    return Import.objects.create(
        ziel=ziel,
        dateiname="liste.csv",
        spalten=spalten,
        zeilen=zeilen,
        zuordnung=zuordnung,
        benutzer=inhaber,
        bestaetigt=True,
        **mehr,
    )


def test_probelauf_adressen(inhaber):
    Kontakt.objects.create(
        firmenname="Gärtnerei Lind", ort="Mainz", email="post@lind.test"
    )
    inhalt = (
        "Kundennummer;Firma;Anrede;Vorname;Nachname;Kategorie;PLZ;Ort;Land;E-Mail\n"
        ";Bäckerei Korn;Firma;;;;1067;Dresden;DE;info@korn.test\n"
        ";;Mrs.;Lea;Sommer;Interessenten;55116;Mainz;;\n"
        ";;Dr.;;;;;;;lea@\n"
        ";Lind & Söhne;;;;;;Bonn;;POST@lind.test\n"
        ";bäckerei korn;;;;;;dresden;;\n"
        "K-0001;Studio Hell;Dr.;;;;;Wien;AT;\n"
        "500;Hof Ahorn;;;;Lieferant;;;;\n"
        ";Kiosk;;;;Partner;;;;\n"
    ).encode()

    bericht = uebernahme.pruefen(_import(inhaber, "kontakte", inhalt))

    korn, sommer, hell, ahorn = bericht.neu
    assert (korn.art, korn.plz, korn.land, korn.anrede) == (
        "firma",
        "01067",
        "Deutschland",
        "",
    )
    assert (sommer.art, sommer.anrede, sommer.kategorie) == (
        "person",
        "Frau",
        "interessent",
    )
    assert (hell.land, ahorn.kategorie) == ("Österreich", "lieferant")
    assert [k.nummer for k in bericht.neu] == [501, 502, 503, 500]
    assert bericht.dubletten == [
        (5, "Lind & Söhne", "K-0001 Gärtnerei Lind"),
        (6, "bäckerei korn", "Zeile 2"),
    ]
    (nr, meldungen), (nr_kiosk, meldungen_kiosk) = bericht.fehler
    assert nr == 4 and len(meldungen) == 2
    assert any("Nachname" in m for m in meldungen) and any(
        "E-Mail" in m for m in meldungen
    )
    assert nr_kiosk == 9 and "Partner" in meldungen_kiosk[0]
    assert bericht.hinweise == [
        (7, "Die Anrede „Dr.“ kennt Kontorfreund nicht; sie bleibt leer."),
        (7, "Die Nummer K-0001 ist schon vergeben; es gibt eine neue."),
    ]
    assert Kontakt.objects.count() == 1, "der Probelauf legt nichts an"


def test_dubletten_trotzdem_anlegen(inhaber):
    Kontakt.objects.create(firmenname="Bäckerei Korn", ort="Dresden")
    imp = _import(
        inhaber,
        "kontakte",
        b"Firma;Ort\nB\xc3\xa4ckerei Korn;Dresden\n",
        dubletten_anlegen=True,
    )

    bericht = uebernahme.uebernehmen(imp)

    assert len(bericht.dubletten) == 1 and len(bericht.neu) == 1
    assert Kontakt.objects.filter(firmenname="Bäckerei Korn").count() == 2


def test_probelauf_artikel(inhaber):
    Artikel.objects.create(bezeichnung="Beratung", preis=Decimal("80"))
    inhalt = (
        "Art.-Nr.;Artikel;Einheit;VK netto\n"
        "A-0007;Stundensatz;h;1.234,50 €\n"
        ";Wartung;Psch.;99.5\n"
        ";Kabel;kg;abc\n"
        ";stundensatz;Std.;10\n"
        ";beratung;;80\n"
        ";Rabatt;;-5\n"
    ).encode()

    bericht = uebernahme.pruefen(_import(inhaber, "artikel", inhalt))

    stunde, wartung = bericht.neu
    assert (stunde.nummer, stunde.einheit, stunde.preis) == (
        7,
        "Std.",
        Decimal("1234.50"),
    )
    assert (wartung.nummer, wartung.einheit, wartung.preis) == (
        8,
        "Pauschale",
        Decimal("99.50"),
    )
    assert [(nr, name) for nr, name, _ in bericht.dubletten] == [
        (5, "stundensatz"),
        (6, "beratung"),
    ]
    (nr, kabel), (nr_rabatt, rabatt) = bericht.fehler
    assert nr == 4 and "kg" in kabel[0] and "„abc“ ist kein Betrag" in kabel[1]
    assert len(kabel) == 2, "der Preis wird nicht doppelt gemeldet"
    assert nr_rabatt == 7 and "Einzelpreis" in rabatt[0]


def test_ablauf_im_browser(client, inhaber):
    inhalt = "Firma;PLZ;Ort;E-Mail\nBäckerei Korn;01067;Dresden;info@korn.test\nHof Ahorn;;Bonn;\n".encode()

    antwort = hochladen(client, inhalt)
    imp = Import.objects.get()
    assert antwort.url == reverse("importe:zuordnen", args=[imp.pk])
    seite = client.get(antwort.url).text
    assert "Spalten zuordnen" in seite and "info@korn.test" in seite
    assert client.get(reverse("importe:bericht", args=[imp.pk])).url == antwort.url, (
        "ohne bestätigte Zuordnung kein Probelauf"
    )

    antwort = bestaetigen(client, imp)
    assert antwort.url == reverse("importe:bericht", args=[imp.pk])
    seite = client.get(antwort.url).text
    assert "Adressen werden angelegt" in seite and "2 Adressen übernehmen" in seite
    assert not Kontakt.objects.exists()

    antwort = client.post(reverse("importe:uebernehmen", args=[imp.pk]), follow=True)
    assert antwort.redirect_chain[-1][0] == reverse("contacts:liste")
    assert "2 Adressen übernommen." in antwort.text
    assert sorted(Kontakt.objects.values_list("firmenname", flat=True)) == [
        "Bäckerei Korn",
        "Hof Ahorn",
    ]
    assert not Import.objects.exists()
    eintraege = Eintrag.objects.filter(aktion=Eintrag.Aktion.ANGELEGT, art="Adresse")
    assert eintraege.count() == 2 and {e.benutzer_id for e in eintraege} == {inhaber.pk}


def test_pflichtfelder_der_zuordnung(client):
    hochladen(client, b"Bezeichnung;Preis\nWartung;10\n", ziel="artikel")
    imp = Import.objects.get()

    seite = client.post(
        reverse("importe:zuordnen", args=[imp.pk]),
        {"spalte_bezeichnung": "Bezeichnung"},
    ).text

    assert "Ohne Einzelpreis netto lässt sich kein Artikel anlegen." in seite
    imp.refresh_from_db()
    assert not imp.bestaetigt


def test_zuordnung_speichern_wiedererkennen_und_loeschen(client):
    inhalt = b"Kunde;Wohnort\nHof Ahorn;Bonn\n"
    hochladen(client, inhalt)
    imp = Import.objects.get()
    assert imp.vorlage == "" and "firmenname" not in imp.zuordnung

    bestaetigen(
        client,
        imp,
        spalte_firmenname="Kunde",
        spalte_ort="Wohnort",
        speichern_als="Altprogramm",
    )
    zuordnung = Zuordnung.objects.get()
    assert (zuordnung.name, zuordnung.felder) == (
        "Altprogramm",
        {"firmenname": "Kunde", "ort": "Wohnort"},
    )

    hochladen(client, inhalt)
    imp = Import.objects.get()
    assert imp.vorlage == "Altprogramm" and imp.zuordnung["firmenname"] == "Kunde"
    assert "Altprogramm" in client.get(reverse("importe:adressen")).text

    client.post(reverse("importe:zuordnung_loeschen", args=[zuordnung.pk]))
    assert not Zuordnung.objects.exists()


def test_vorlage_anwenden(client):
    hochladen(client, b"Firma;Ort;Name\nHof Ahorn;Bonn;x\n")
    imp = Import.objects.get()

    client.post(reverse("importe:zuordnen", args=[imp.pk]), {"vorlage": "Kontorfreund"})

    imp.refresh_from_db()
    assert imp.vorlage == "Kontorfreund" and imp.zuordnung == {
        "firmenname": "Name",
        "ort": "Ort",
    }


def test_rundreise_mit_der_adressliste(client):
    Kontakt.objects.create(
        firmenname="Bäckerei Korn",
        vorname="Lea",
        nachname="Sommer",
        strasse="Hauptstr. 1",
        plz="01067",
        ort="Dresden",
        email="info@korn.test",
        kategorie="lieferant",
    )
    Kontakt.objects.create(
        art="person", anrede="Herr", vorname="Tom", nachname="Lind", ort="Bonn"
    )
    datei = client.get(reverse("contacts:liste"), {"format": "xlsx"}).content
    Kontakt.objects.all().delete()

    hochladen(client, datei, name="Adressen.xlsx")
    imp = Import.objects.get()
    assert imp.vorlage == "Kontorfreund"
    bestaetigen(client, imp)
    client.post(reverse("importe:uebernehmen", args=[imp.pk]))

    korn, lind = Kontakt.objects.order_by("nummer")
    assert (korn.kundennummer, korn.art, korn.kategorie, korn.ansprechpartner) == (
        "K-0001",
        "firma",
        "lieferant",
        "Lea Sommer",
    )
    assert (korn.strasse, korn.plz, korn.email) == (
        "Hauptstr. 1",
        "01067",
        "info@korn.test",
    )
    assert (lind.kundennummer, lind.art, lind.anrede, lind.firmenname) == (
        "K-0002",
        "person",
        "Herr",
        "",
    )


def test_nur_wer_hochgeladen_hat_sieht_den_import(client, anonym):
    hochladen(client, b"Firma\nHof Ahorn\n")
    imp = Import.objects.get()
    team = Benutzer.objects.create_user(
        "team@muster.test", name="Team", rolle=Benutzer.Rolle.MITARBEITER
    )
    anonym.force_login(team)

    assert anonym.get(reverse("importe:zuordnen", args=[imp.pk])).status_code == 404
    assert anonym.post(reverse("importe:uebernehmen", args=[imp.pk])).status_code == 404


def test_abbrechen_und_zu_grosse_datei(client, monkeypatch):
    hochladen(client, b"Firma\nHof Ahorn\n")
    imp = Import.objects.get()
    client.post(reverse("importe:verwerfen", args=[imp.pk]))
    assert not Import.objects.exists() and not Kontakt.objects.exists()

    monkeypatch.setattr(lesen, "GROESSTE_DATEI", 2**20)
    seite = hochladen(client, b"Firma\n" + b"x" * 2**20).text
    assert "Die Datei ist größer als 1 MB." in seite
    assert not Import.objects.exists()


def test_links_in_den_listen(client):
    assert reverse("importe:adressen") in client.get(reverse("contacts:liste")).text
    assert reverse("importe:artikel") in client.get(reverse("artikel:liste")).text
