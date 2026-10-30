"""Offene Posten, Zahlungen und Mahnungen – mit erfundenen Daten."""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from pypdf import PdfReader

from contacts.models import Kontakt
from core.models import Firmendaten
from core.templatetags.kf import euro
from invoicing.models import Rechnung
from zahlungen import mahnen
from zahlungen.models import Basiszins, Mahnstufe, Mahnung, Zahlung
from zahlungen.zinsen import verzug_ab, verzugszinsen

pytestmark = pytest.mark.django_db


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
def firmenkunde():
    return Kontakt.objects.create(
        firmenname="Muster Bäckerei GmbH",
        strasse="Lindenweg 4",
        plz="55116",
        ort="Mainz",
        email="buchhaltung@baeckerei.test",
    )


@pytest.fixture
def privatkunde():
    return Kontakt.objects.create(
        art=Kontakt.Art.PERSON,
        anrede="Frau",
        vorname="Erika",
        nachname="Beispiel",
        strasse="Ahornweg 2",
        plz="55116",
        ort="Mainz",
    )


def rechnung_schreiben(client, kunde, datum="2026-08-03"):
    """1.000 € (12,5 Std. × 80 €), Kleinunternehmer, 14 Tage Zahlungsziel."""
    client.post(
        reverse("invoicing:neu"),
        {
            "kontakt": kunde.pk,
            "datum": datum,
            "leistung_von": datum,
            "zahlungsziel": "14",
            "steuerfall": "kleinunternehmer",
            "kopftext": "Sehr geehrte Damen und Herren,",
            "fusstext": "Mit freundlichen Grüßen",
            "bezeichnung": ["Webdesign"],
            "beschreibung": [""],
            "menge": ["12,5"],
            "einheit": ["Std."],
            "preis": ["80,00"],
            "aktion": "festschreiben",
        },
    )
    rechnung = Rechnung.objects.filter(kontakt=kunde).latest("pk")
    assert not rechnung.ist_entwurf
    return rechnung


def zahlen(client, rechnung, betrag, datum="2026-09-01", **mehr):
    return client.post(
        reverse("zahlungen:buchen", args=[rechnung.pk]),
        {
            "zahlung-datum": datum,
            "zahlung-betrag": betrag,
            "zahlung-art": "ueberweisung",
            "zahlung-notiz": "",
            **mehr,
        },
        follow=True,
    )


def frisch(rechnung):
    return mahnen.posten(rechnung.kontakt)[-1]


def test_festgeschriebene_rechnung_ist_offen_und_ueberfaellig(
    client, firma, firmenkunde
):
    rechnung = rechnung_schreiben(client, firmenkunde)
    r = frisch(rechnung)
    assert r.offen == Decimal("1000.00")
    assert r.faellig == date(2026, 8, 17)
    assert r.zahlstand == "ueberfaellig"

    liste = client.get(reverse("zahlungen:liste")).text
    assert rechnung.nummer in liste
    assert "1.000,00" in liste
    assert "Mahnung fällig" in liste
    start = client.get(reverse("core:start")).text
    assert "Überfällige Rechnungen" in start
    assert "Zahlungserinnerung" in start
    assert "Überfällig" in client.get(reverse("invoicing:liste")).text


def test_teilzahlung_und_rest(client, firma, firmenkunde):
    # Noch nicht fällig, sonst wäre sie trotz Teilzahlung „überfällig“.
    heute = date.today().isoformat()
    rechnung = rechnung_schreiben(client, firmenkunde, datum=heute)
    antwort = zahlen(client, rechnung, "400,00", datum=heute)
    assert "Offen bleiben 600,00" in antwort.text
    assert frisch(rechnung).zahlstand == "teilbezahlt"

    antwort = zahlen(client, rechnung, "600,00", datum=heute)
    assert "Die Rechnung ist bezahlt" in antwort.text
    r = frisch(rechnung)
    assert r.offen == 0
    assert r.zahlstand == "bezahlt"
    assert rechnung.nummer not in client.get(reverse("zahlungen:liste")).text
    assert (
        rechnung.nummer
        in client.get(reverse("zahlungen:liste") + "?zeigen=bezahlt").text
    )
    assert "Bezahlt" in client.get(reverse("invoicing:liste")).text


def test_ueberzahlung_und_rueckzahlung(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    antwort = zahlen(client, rechnung, "1.050,00")
    assert f"{euro(50)} zu viel gezahlt" in antwort.text
    assert frisch(rechnung).zahlstand == "ueberzahlt"
    zahlen(client, rechnung, "-50,00", datum="2026-09-05")
    assert frisch(rechnung).zahlstand == "bezahlt"


def test_ausbuchen_nur_mit_grund_und_hoechstens_offen(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    zahlen(client, rechnung, "995,00")
    url = reverse("zahlungen:ausbuchen", args=[rechnung.pk])
    client.post(
        url,
        {
            "ausbuchen-datum": "2026-09-02",
            "ausbuchen-betrag": "5,00",
            "ausbuchen-grund": "",
        },
    )
    assert frisch(rechnung).offen == Decimal("5.00")
    client.post(
        url,
        {
            "ausbuchen-datum": "2026-09-02",
            "ausbuchen-betrag": "6,00",
            "ausbuchen-grund": "Bankgebühr",
        },
    )
    assert frisch(rechnung).offen == Decimal("5.00")
    client.post(
        url,
        {
            "ausbuchen-datum": "2026-09-02",
            "ausbuchen-betrag": "5,00",
            "ausbuchen-grund": "Bankgebühr",
        },
    )
    r = frisch(rechnung)
    assert r.offen == 0
    assert r.ausgebucht == Decimal("5.00")
    assert r.zahlstand == "bezahlt"


def test_zahlung_loeschen(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    zahlen(client, rechnung, "400,00")
    zahlung = Zahlung.objects.get()
    client.post(reverse("zahlungen:zahlung_loeschen", args=[zahlung.pk]))
    assert frisch(rechnung).offen == Decimal("1000.00")


def test_storno_nach_zahlung_ist_zu_viel_gezahlt(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    zahlen(client, rechnung, "1.000,00")
    client.post(reverse("invoicing:stornieren", args=[rechnung.pk]))
    r = frisch(rechnung)
    assert r.storniert
    assert r.offen == Decimal("-1000.00")
    assert r.zahlstand == "ueberzahlt"
    # Die Stornorechnung selbst ist kein offener Posten.
    assert len(mahnen.posten()) == 1


def test_verzug_unternehmen_30_tage_nach_rechnung(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    r = frisch(rechnung)
    # Zugang 3 Tage nach Rechnungsdatum, Fälligkeit 17.08., 30 Tage später Verzug.
    assert verzug_ab(r, []) == date(2026, 9, 17)
    aufstellung = mahnen.berechnen(r, 1, date(2026, 10, 1), Decimal("0"), True, False)
    assert aufstellung["im_verzug"]
    # 14 Tage × 1.000 € × 10,52 % / 365
    assert aufstellung["zinsen"] == Decimal("4.04")
    assert aufstellung["gesamt"] == Decimal("1004.04")


def test_verbraucher_erst_nach_mahnung_in_verzug(client, firma, privatkunde):
    rechnung = rechnung_schreiben(client, privatkunde)
    r = frisch(rechnung)
    erinnerung = mahnen.berechnen(r, 1, date(2026, 10, 1), Decimal("2.50"), True, True)
    assert not erinnerung["im_verzug"]
    assert erinnerung["zinsen"] == 0
    assert erinnerung["pauschale"] == 0
    assert "darf es noch nicht kosten" in erinnerung["hinweise"][0]

    client.post(
        reverse("zahlungen:mahnen", args=[rechnung.pk]),
        {
            "datum": "2026-10-01",
            "frist": "2026-10-11",
            "text": "Bitte zahlen Sie.",
            "gebuehr": "0,00",
            "zinsen": "on",
            "aktion": "erstellen",
        },
    )
    r = frisch(rechnung)
    assert verzug_ab(r, list(r.mahnungen.all())) == date(2026, 10, 12)
    mahnung = mahnen.berechnen(r, 2, date(2026, 10, 21), Decimal("0"), True, True)
    assert mahnung["im_verzug"]
    # 9 Tage × 1.000 € × 6,52 % / 365; keine Pauschale gegenüber Verbrauchern
    assert mahnung["zinsen"] == Decimal("1.61")
    assert mahnung["pauschale"] == 0


def test_zinsen_mit_satzwechsel_und_teilzahlung(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde, datum="2026-05-04")
    Zahlung.objects.create(
        rechnung=rechnung, datum=date(2026, 7, 15), betrag=Decimal("400")
    )
    r = frisch(rechnung)
    zinsen, tage, saetze = verzugszinsen(r, date(2026, 6, 1), date(2026, 8, 1))
    # 30 Tage 10,27 % auf 1.000 €, 14 Tage 10,52 % auf 1.000 €, 17 Tage 10,52 % auf 600 €
    assert zinsen == Decimal("15.42")
    assert tage == 61
    assert saetze == [Decimal("10.27"), Decimal("10.52")]


def test_mahnung_erstellen_als_pdf(client, firma, firmenkunde, settings):
    rechnung = rechnung_schreiben(client, firmenkunde)
    seite = client.get(reverse("zahlungen:mahnen", args=[rechnung.pk])).text
    assert "Zahlungserinnerung schreiben" in seite
    assert f"meine Rechnung {rechnung.nummer} vom 03.08.2026 ist noch offen" in seite

    vorschau = client.post(
        reverse("zahlungen:mahnen", args=[rechnung.pk]),
        {
            "datum": "2026-10-01",
            "frist": "2026-10-11",
            "text": "Bitte zahlen Sie.",
            "gebuehr": "0,00",
            "zinsen": "on",
            "pauschale": "on",
            "aktion": "vorschau",
        },
    )
    assert "data:image/png;base64," in vorschau.text
    assert not Mahnung.objects.exists()

    antwort = client.post(
        reverse("zahlungen:mahnen", args=[rechnung.pk]),
        {
            "datum": "2026-10-01",
            "frist": "2026-10-11",
            "text": "Bitte zahlen Sie.",
            "gebuehr": "0,00",
            "zinsen": "on",
            "pauschale": "on",
            "aktion": "erstellen",
        },
    )
    mahnung = Mahnung.objects.get()
    assert antwort.url == reverse("zahlungen:mahnung", args=[mahnung.pk])
    assert mahnung.stufe == 1
    assert mahnung.zinsen == Decimal("4.04")
    assert mahnung.pauschale == Decimal("40.00")
    assert mahnung.gesamt == Decimal("1044.04")
    inhalt = (settings.DATA_DIR / mahnung.datei).read_bytes()
    text = PdfReader(BytesIO(inhalt)).pages[0].extract_text()
    assert "Zahlungserinnerung" in text
    assert "Verzugspauschale" in text
    assert "1.044,04" in text
    assert "11.10.2026" in text

    mahnung.frist = date(2026, 12, 1)
    with pytest.raises(ValidationError):
        mahnung.save()

    # Als Nächstes die 1. Mahnung, sieben Tage nach Ablauf der Frist.
    r = frisch(rechnung)
    stufe, ab = mahnen.naechste_stufe(r, Mahnstufe.alle())
    assert (stufe.stufe, ab) == (2, date(2026, 10, 18))
    ansicht = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk])).text
    assert "1. Mahnung" in ansicht

    client.post(reverse("zahlungen:mahnung_loeschen", args=[mahnung.pk]))
    assert not Mahnung.objects.exists()
    assert not (settings.DATA_DIR / mahnung.datei).exists()


def test_zahlung_deckt_mahnkosten(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    client.post(
        reverse("zahlungen:mahnen", args=[rechnung.pk]),
        {
            "datum": "2026-10-01",
            "frist": "2026-10-11",
            "text": "Bitte zahlen Sie.",
            "gebuehr": "2,50",
            "zinsen": "on",
            "aktion": "erstellen",
        },
    )
    mahnung = Mahnung.objects.get()
    assert mahnung.gesamt == Decimal("1006.54")
    antwort = zahlen(client, rechnung, "1.006,54", datum="2026-10-05")
    assert f"Davon {euro(Decimal('6.54'))} für Mahnkosten und Zinsen" in antwort.text
    zahlung = Zahlung.objects.get()
    assert (zahlung.betrag, zahlung.nebenkosten) == (
        Decimal("1000.00"),
        Decimal("6.54"),
    )
    r = frisch(rechnung)
    assert r.zahlstand == "bezahlt"
    assert mahnen.naechste_stufe(r, Mahnstufe.alle()) is None


def test_keine_mahnung_nach_der_letzten_stufe(client, firma, firmenkunde):
    rechnung = rechnung_schreiben(client, firmenkunde)
    for stufe, datum in ((1, "2026-09-20"), (2, "2026-10-10"), (3, "2026-10-25")):
        frist = date.fromisoformat(datum) + timedelta(days=7)
        client.post(
            reverse("zahlungen:mahnen", args=[rechnung.pk]),
            {
                "datum": datum,
                "frist": frist.isoformat(),
                "text": "Bitte zahlen Sie.",
                "gebuehr": "0,00",
                "aktion": "erstellen",
            },
        )
        assert Mahnung.objects.filter(stufe=stufe).exists()
    assert mahnen.naechste_stufe(frisch(rechnung), Mahnstufe.alle()) is None
    antwort = client.get(reverse("zahlungen:mahnen", args=[rechnung.pk]))
    assert antwort.status_code == 302
    ansicht = client.get(reverse("invoicing:bearbeiten", args=[rechnung.pk])).text
    assert "Alle Mahnstufen sind ausgeschöpft" in ansicht
    # Nur das letzte Schreiben lässt sich löschen.
    erste = Mahnung.objects.get(stufe=1)
    assert (
        client.post(reverse("zahlungen:mahnung_loeschen", args=[erste.pk])).status_code
        == 404
    )


def test_kontoauszug_mit_saldo(client, firma, firmenkunde):
    erste = rechnung_schreiben(client, firmenkunde)
    zweite = rechnung_schreiben(client, firmenkunde, datum="2026-09-01")
    zahlen(client, erste, "1.000,00", datum="2026-08-20")
    zahlen(client, zweite, "250,00", datum="2026-09-10")
    seite = client.get(reverse("zahlungen:kontoauszug", args=[firmenkunde.pk])).text
    assert f"Rechnung {erste.nummer}" in seite
    assert f"Überweisung zu Rechnung {zweite.nummer}" in seite
    assert 'Offen: <strong class="amount">750,00' in seite


def test_mahnwesen_einstellen_nur_inhaber(client, firma):
    seite = client.get(reverse("zahlungen:einstellungen"))
    assert seite.status_code == 200
    daten = {"aktion": "stufen"}
    for nummer, stufe in Mahnstufe.alle().items():
        daten.update(
            {
                f"s{nummer}-abstand": "5",
                f"s{nummer}-frist": "14",
                f"s{nummer}-gebuehr": "0,00",
                f"s{nummer}-text": stufe.text,
            }
        )
    client.post(reverse("zahlungen:einstellungen"), daten)
    assert Mahnstufe.objects.get(stufe=2).abstand == 5
    assert not Mahnstufe.objects.get(stufe=2).zinsen

    client.post(
        reverse("zahlungen:einstellungen"),
        {"aktion": "basiszins", "gueltig_ab": "2027-01-15", "satz": "1,40"},
    )
    assert not Basiszins.objects.filter(gueltig_ab=date(2027, 1, 15)).exists()
    client.post(
        reverse("zahlungen:einstellungen"),
        {"aktion": "basiszins", "gueltig_ab": "2027-01-01", "satz": "1,40"},
    )
    assert Basiszins.am(date(2027, 3, 1)) == Decimal("1.40")
    assert not Basiszins.veraltet(heute=date(2027, 3, 1))
    assert Basiszins.veraltet(heute=date(2027, 7, 2))


def test_mitarbeiter_darf_mahnwesen_nicht_einstellen(anonym, db):
    from konten.models import Benutzer

    mitarbeiter = Benutzer.objects.create_user(
        "team@muster.test", name="Team", rolle=Benutzer.Rolle.MITARBEITER
    )
    anonym.force_login(mitarbeiter)
    assert anonym.get(reverse("zahlungen:einstellungen")).status_code == 403
    assert anonym.get(reverse("zahlungen:liste")).status_code == 200
