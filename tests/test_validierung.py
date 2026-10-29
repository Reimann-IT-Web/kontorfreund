"""Offizielle Prüfung der E-Rechnungen mit KoSIT-Validator und Mustang.

Läuft nur, wo die Werkzeuge bereitliegen: Die CI lädt sie mit fester Prüfsumme
herunter (.github/workflows/ci.yml) und nennt die Pfade in KOSIT_VALIDATOR
(Ordner mit Validator und libs/), KOSIT_KONFIGURATION (Prüfregeln XRechnung)
und MUSTANG (Mustang-CLI). Ohne diese Angaben wird übersprungen.
"""

import os
import re
import subprocess
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import pytest
from django.urls import reverse
from pypdf import PdfReader

from contacts.models import Kontakt
from core.models import Firmendaten
from invoicing.models import Rechnung

WERKZEUGE = ("KOSIT_VALIDATOR", "KOSIT_KONFIGURATION", "MUSTANG")
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not all(os.environ.get(name) for name in WERKZEUGE),
        reason="KoSIT-Validator und Mustang liegen nur in der CI bereit",
    ),
]

REP = {"rep": "http://www.xoev.de/de/validator/varl/1"}
LEITWEG_ID = "991-33333TEST-33"

# Name, Steuerfall, Angaben der Adresse; jede Rechnung wird auch storniert.
FAELLE = [
    ("kleinunternehmer", "kleinunternehmer", {}),
    ("regel", "regel", {}),
    ("13b", "13b", {"land": "Österreich", "ust_id": "ATU12345678"}),
    (
        "xrechnung-leitweg",
        "kleinunternehmer",
        {"kaeuferreferenz": LEITWEG_ID, "xrechnung": True},
    ),
    (
        "xrechnung-mail",
        "regel",
        {"kaeuferreferenz": "Kostenstelle 4711", "xrechnung": True},
    ),
]


def java(*argumente):
    return subprocess.run(  # noqa: S603
        ["java", *argumente],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def rechnungen(client, settings):
    """Je Steuerfall eine Rechnung und ihre Stornorechnung, festgeschrieben."""
    f = Firmendaten.laden()
    f.name = "Muster IT"
    f.inhaber = "Max Muster"
    f.strasse = "Gartenweg 1"
    f.plz = "55116"
    f.ort = "Mainz"
    f.steuernummer = "12/345/67890"
    f.ust_id = "DE123456789"
    f.email = "post@muster.test"
    f.telefon = "06131 123456"
    f.iban = "DE02120300000000202051"
    f.save()

    dateien = {}
    for name, steuerfall, adresse in FAELLE:
        kunde = Kontakt.objects.create(
            firmenname=f"Kunde {name}",
            strasse="Lindenweg 4",
            plz="55116",
            ort="Mainz",
            email="buchhaltung@kunde.test",
            **adresse,
        )
        client.post(
            reverse("invoicing:neu"),
            {
                "kontakt": kunde.pk,
                "datum": "2026-10-29",
                "leistung_von": "2026-10-01",
                "leistung_bis": "2026-10-31",
                "zahlungsziel": "14",
                "steuerfall": steuerfall,
                "kopftext": "Sehr geehrte Damen und Herren,",
                "fusstext": "Mit freundlichen Grüßen",
                "bezeichnung": ["Webdesign", "Hosting"],
                "beschreibung": ["- Startseite\n- Galerie", ""],
                "menge": ["29,5", "12"],
                "einheit": ["Std.", "Monat"],
                "preis": ["80,00", "9,99"],
                "aktion": "festschreiben",
            },
        )
        original = Rechnung.objects.get(kontakt=kunde)
        assert not original.ist_entwurf, name
        client.post(reverse("invoicing:stornieren", args=[original.pk]))
        storno = Rechnung.objects.get(storno_zu=original)
        dateien[name] = Path(settings.DATA_DIR) / original.datei
        dateien[f"{name}-storno"] = Path(settings.DATA_DIR) / storno.datei
    return dateien


def test_kosit_akzeptiert_jede_xml(rechnungen, tmp_path):
    xml = tmp_path / "xml"
    xml.mkdir()
    for name, pdf in rechnungen.items():
        (anhang,) = PdfReader(BytesIO(pdf.read_bytes())).attachments["factur-x.xml"]
        (xml / f"{name}.xml").write_bytes(anhang)

    validator = Path(os.environ["KOSIT_VALIDATOR"])
    konfiguration = Path(os.environ["KOSIT_KONFIGURATION"])
    berichte = tmp_path / "berichte"
    lauf = java(
        "-cp",
        os.pathsep.join(
            [str(validator / "validator-1.6.3.jar"), str(validator / "libs" / "*")]
        ),
        "de.kosit.validationtool.cmd.CommandLineApplication",
        "-s",
        str(konfiguration / "scenarios.xml"),
        "-r",
        str(konfiguration),
        "-o",
        str(berichte),
        *sorted(str(p) for p in xml.iterdir()),
    )
    assert berichte.is_dir(), lauf.stdout + lauf.stderr

    ergebnis = {}
    for bericht in berichte.glob("*.xml"):
        wurzel = ElementTree.parse(bericht).getroot()  # noqa: S314 – vom Validator
        datei = wurzel.findtext(
            ".//rep:documentIdentification/rep:documentReference", namespaces=REP
        )
        szenario = wurzel.findtext(
            ".//rep:scenarioMatched/{*}scenario/{*}name", namespaces=REP
        )
        fehler = [
            f"{m.get('code')}: {m.text.strip()}"
            for m in wurzel.iterfind(".//rep:message", REP)
            if m.get("level") == "error"
        ]
        angenommen = wurzel.find("rep:assessment/rep:accept", REP) is not None
        ergebnis[Path(datei).stem] = (angenommen, szenario, fehler)

    assert sorted(ergebnis) == sorted(rechnungen), lauf.stdout + lauf.stderr
    for name, (angenommen, szenario, fehler) in sorted(ergebnis.items()):
        erwartet = (
            "EN16931 XRechnung (CII)"
            if name.startswith("xrechnung")
            else "EN16931 (CII)"
        )
        assert szenario == erwartet, name
        assert angenommen, f"{name}: {fehler}"


def test_mustang_akzeptiert_jedes_pdf(rechnungen):
    abgelehnt = {}
    for name, pdf in sorted(rechnungen.items()):
        lauf = java(
            "-jar",
            os.environ["MUSTANG"],
            "--action",
            "validate",
            "--no-notices",
            "--disable-file-logging",
            "--source",
            str(pdf),
        )
        status = re.search(r'<summary status="(\w+)"', lauf.stdout)
        if not status or status[1] != "valid":
            abgelehnt[name] = lauf.stdout[-3000:] + lauf.stderr[-1000:]
    assert not abgelehnt, "\n\n".join(f"{n}:\n{t}" for n, t in abgelehnt.items())
