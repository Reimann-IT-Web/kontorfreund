"""Aufbewahrungsfristen (Spezifikation D-1) – mit erfundenen Daten."""

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from archive import fristen
from archive.models import Altbeleg
from contacts.models import Kontakt
from invoicing.models import Rechnung
from konten.models import Benutzer
from protokoll.models import Eintrag
from zahlungen.models import Mahnung, Zahlung

pytestmark = pytest.mark.django_db

JAHR = date.today().year


@pytest.fixture
def kunde():
    return Kontakt.objects.create(
        firmenname="Bäckerei Korn", strasse="Markt 3", plz="55116", ort="Mainz"
    )


def altbeleg(kunde, art, nummer, datum):
    pfad = f"archiv/altbelege/{datum.year}/{nummer}.pdf"
    ziel = Path(settings.DATA_DIR) / pfad
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(f"%PDF {nummer}".encode())
    return Altbeleg.objects.create(
        art=art,
        nummer=nummer,
        datum=datum,
        kontakt=kunde,
        empfaenger="Bäckerei Korn\nMarkt 3",
        betrag=Decimal("99.00"),
        datei=pfad,
        sha256=hashlib.sha256(nummer.encode()).hexdigest(),
        originalname=f"{nummer}.pdf",
    )


def rechnung(kunde, nummer, datum, **felder):
    return Rechnung.objects.create(
        kontakt=kunde,
        status=Rechnung.Status.FESTGESCHRIEBEN,
        nummer=nummer,
        datum=datum,
        brutto=Decimal("100.00"),
        **felder,
    )


def test_abgelaufene_belege_nach_jahren_loeschen(
    client, kunde, django_capture_on_commit_callbacks
):
    alt = altbeleg(kunde, Altbeleg.Art.RECHNUNG, "2015-001", date(2015, 3, 1))
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, "2016-001", date(2016, 3, 1))
    angebot = altbeleg(kunde, Altbeleg.Art.ANGEBOT, "A-2019", date(2019, 5, 1))
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, "2019-001", date(2019, 5, 2))
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, f"{JAHR}-001", date(JAHR, 1, 2))

    start = client.get(reverse("core:start")).text
    assert "Für 3 Belege ist die Aufbewahrungsfrist abgelaufen." in start

    seite = client.get(reverse("archive:fristen")).text
    for erwartet in ("2015</strong> · 1 Rechnung", "2019</strong> · 1 Angebot"):
        assert erwartet in seite
    assert "aufzubewahren bis 31.12.2025" in seite
    assert "2019-001" not in seite, "die Rechnung von 2019 läuft bis Ende 2027"

    with django_capture_on_commit_callbacks(execute=True):
        antwort = client.post(
            reverse("archive:fristen"), {"jahr": ["2015", "2019"]}, follow=True
        )
    assert "2 Belege aus 2015 und 2019 gelöscht." in antwort.text
    assert set(Altbeleg.objects.values_list("nummer", flat=True)) == {
        "2016-001",
        "2019-001",
        f"{JAHR}-001",
    }
    daten = Path(settings.DATA_DIR)
    assert not (daten / alt.datei).exists()
    assert not (daten / alt.datei).parent.exists(), "leerer Jahresordner mit weg"
    assert not (daten / angebot.datei).exists()
    assert (daten / "archiv/altbelege/2019/2019-001.pdf").exists()

    geschwaerzt = Eintrag.objects.filter(art="Altbeleg", objekt_id=str(alt.pk))
    assert geschwaerzt.exists()
    assert all(e.beschreibung == fristen.ABGELAUFEN for e in geschwaerzt)
    assert all(e.aenderungen == [] for e in geschwaerzt)
    entscheidung = Eintrag.objects.get(aktion=Eintrag.Aktion.FRISTEN)
    assert entscheidung.beschreibung == "2 Belege aus 2015 und 2019 gelöscht"

    # Entschieden: bis zum Jahresende kein Hinweis mehr, obwohl 2016 noch da ist.
    assert "Aufbewahrungsfrist abgelaufen" not in client.get(reverse("core:start")).text
    seite = client.get(reverse("archive:fristen")).text
    assert f"Am {timezone.localdate():%d.%m.%Y} entschieden" in seite
    assert "2016</strong>" in seite


def test_alle_behalten(client, kunde):
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, "2015-001", date(2015, 3, 1))
    antwort = client.post(
        reverse("archive:fristen"),
        {"jahr": ["2015"], "aktion": "behalten"},
        follow=True,
    )
    assert "Die Belege bleiben." in antwort.text
    assert Altbeleg.objects.count() == 1
    assert fristen.entscheidung().beschreibung == "abgelaufene Belege behalten"
    assert fristen.hinweis() is None


def test_storno_vor_rechnung_und_geschuetzte_rechnung_bleibt(
    kunde, django_capture_on_commit_callbacks
):
    original = rechnung(kunde, "150001", date(2015, 3, 1))
    Zahlung.objects.create(rechnung=original, datum=date(2015, 3, 9), betrag=10)
    rechnung(kunde, "150002", date(2015, 4, 1), storno_zu=original)
    gemahnt = rechnung(kunde, "150003", date(2015, 5, 1))
    # Mahnungen bleiben 6 Jahre; diese bis Ende 2027 und mit ihr die Rechnung.
    Mahnung.objects.create(
        rechnung=gemahnt,
        stufe=1,
        datum=date(2021, 6, 1),
        frist=date(2021, 6, 15),
        offen=Decimal("100.00"),
        gesamt=Decimal("100.00"),
        datei="archiv/mahnungen/2021/Zahlungserinnerung-150003.pdf",
        sha256="m",
    )

    weg = {b.nummer for b in fristen.abgelaufen()}
    assert weg == {"150001", "150002"}

    with django_capture_on_commit_callbacks(execute=True):
        fristen.loeschen({2015})
    assert list(Rechnung.objects.values_list("nummer", flat=True)) == ["150003"]
    assert not Zahlung.objects.exists()
    assert Mahnung.objects.count() == 1


def test_gesperrte_adresse_nach_ablauf_loeschen(
    client, kunde, django_capture_on_commit_callbacks
):
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, "2015-001", date(2015, 3, 1))
    Kontakt.objects.filter(pk=kunde.pk).update(
        gesperrt_am=timezone.now(), archiviert=True
    )
    assert fristen.hinweis() == (1, 1)
    start = client.get(reverse("core:start")).text
    assert "und 1 gesperrte Adresse darf jetzt gelöscht werden." in start
    assert "Bäckerei Korn" in client.get(reverse("archive:fristen")).text

    with django_capture_on_commit_callbacks(execute=True):
        antwort = client.post(
            reverse("archive:fristen"), {"adresse": [str(kunde.pk)]}, follow=True
        )
    assert "1 gesperrte Adresse gelöscht." in antwort.text
    assert not Kontakt.objects.exists()
    assert not Altbeleg.objects.exists()
    assert Eintrag.objects.filter(aktion=Eintrag.Aktion.LOESCHUNG).exists()


def test_nichts_abgelaufen(client, kunde):
    altbeleg(kunde, Altbeleg.Art.ANGEBOT, f"A-{JAHR}", date(JAHR, 2, 1))
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, f"{JAHR}-001", date(JAHR, 2, 2))
    assert fristen.hinweis() is None
    seite = client.get(reverse("archive:fristen")).text
    assert "Nichts abgelaufen" in seite
    assert f"Die nächste Frist endet am 31.12.{JAHR + 6} für 1 Beleg." in seite
    nichts = client.post(reverse("archive:fristen"), follow=True)
    assert "Bitte wählen Sie aus" in nichts.text
    assert not Eintrag.objects.filter(aktion=Eintrag.Aktion.FRISTEN).exists()


def test_nur_fuer_den_inhaber(kunde):
    altbeleg(kunde, Altbeleg.Art.RECHNUNG, "2015-001", date(2015, 3, 1))
    mitarbeiter = Client()
    mitarbeiter.force_login(
        Benutzer.objects.create_user(
            "mia@muster.test", name="Mia", rolle=Benutzer.Rolle.MITARBEITER
        )
    )
    url = reverse("archive:fristen")
    assert mitarbeiter.get(url).status_code == 403
    assert mitarbeiter.post(url, {"jahr": ["2015"]}).status_code == 403
    assert Altbeleg.objects.count() == 1
    start = mitarbeiter.get(reverse("core:start")).text
    assert "Aufbewahrungsfrist abgelaufen" not in start
    assert url not in start
