import hashlib
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.hashers import check_password, make_password
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.templatetags.static import static
from django.test import Client, override_settings
from django.utils import timezone

from auswertungen import pruefer, tabelle
from backups import sicherung
from contacts import datenschutz, plz
from contacts.models import Kontakt
from core.models import Firmendaten
from dokumentation import fassungen
from dokumentation.models import Fassung
from eingang import lesen
from importe import lesen as tabellen
from invoicing import beleg
from invoicing.models import Rechnung


class Command(BaseCommand):
    help = (
        "Prüft, ob alle Teile des Programms vorhanden sind und arbeiten: Seiten, "
        "Kennwörter, PDF, E-Rechnung, Tabellen und Datensicherung. Für das "
        "Installationspaket; alles, was dabei in der Datenbank entsteht, wird "
        "zurückgenommen, die Datensicherung läuft mit eigener Datenbank in einem "
        "Wegwerf-Ordner."
    )

    def handle(self, **optionen):
        browser = Client(HTTP_HOST="127.0.0.1")
        seite = browser.get("/konto/anmelden/", follow=True)
        self.pruefen(
            seite.status_code == 200 and b"Kontorfreund" in seite.content,
            "Anmeldeseite",
        )
        for datei in ("css/app.css", "js/app.js", "img/icon.svg"):
            self.pruefen(browser.get(static(datei)).status_code == 200, datei)
        self.pruefen(check_password("probe", make_password("probe")), "Kennwörter")
        self.pruefen(plz.orte("55116")[1] == "Mainz", "Orte zu Postleitzahlen")
        self.pruefen(
            pruefer.DTD.is_file()
            and hashlib.sha256(pruefer.DTD.read_bytes()).hexdigest()
            == pruefer.DTD_SHA256,
            "Beschreibungsstandard für die Betriebsprüfung",
        )

        with transaction.atomic():
            kunde = Kontakt.objects.create(
                firmenname="Kunde", strasse="Weg 2", plz="12345", ort="Teststadt"
            )
            rechnung = Rechnung.objects.create(
                kontakt=kunde,
                leistung_von=date.today(),
                steuerfall=Rechnung.Steuerfall.REGEL,
            )
            rechnung.positionen.create(
                nr=1, bezeichnung="Prüfung", einheit="Std.", preis=Decimal("80.00")
            )
            firma = Firmendaten(
                name="Selbsttest",
                strasse="Teststraße 1",
                plz="12345",
                ort="Teststadt",
                steuernummer="12/345/67890",
                iban="DE02120300000000202051",
            )
            pdf, xml = beleg.endgueltiges_pdf(beleg.beleg_daten(rechnung, firma, "T-1"))
            jetzt = timezone.localtime()
            auskunft = datenschutz.setzen(
                datenschutz.druckdaten(
                    kunde, datenschutz.auskunft_daten(kunde, [], jetzt), None, jetzt
                )
            )
            dokumente = [
                fassungen.setzen(
                    fassungen.druckdaten(
                        Fassung(
                            art=art,
                            nummer=1,
                            version="selbsttest",
                            inhalt=fassungen.entwurf(art),
                        ),
                        [],
                    )
                )
                for art in Fassung.Art.values
            ]
            transaction.set_rollback(True)
        self.pruefen(b"AtkinsonHyperlegibleNext" in pdf, "PDF mit eigener Schrift")
        self.pruefen(len(beleg.seitenbilder(pdf)) == 1, "Seitenbild")
        self.pruefen(auskunft.startswith(b"%PDF"), "Auskunft nach Art. 15 DSGVO")
        self.pruefen(
            all(d.startswith(b"%PDF") for d in dokumente),
            "Verfahrensdokumentation und Verzeichnis von Verarbeitungstätigkeiten",
        )
        d = lesen.auswerten(lesen.einlesen(pdf)[1])
        self.pruefen(
            d["nummer"] == "T-1" and d["summen"]["zahlbetrag"] == Decimal("95.20"),
            "ZUGFeRD schreiben und lesen",
        )
        spalten, zeilen = (
            [("Name", "text"), ("Preis", "betrag")],
            [["Prüfung", Decimal("12.50")]],
        )
        self.pruefen(
            all(
                tabellen.lesen(datei) == (["Name", "Preis"], [[2, ["Prüfung", "12,5"]]])
                for datei in (
                    tabelle.xlsx(spalten, zeilen, "Selbsttest"),
                    tabelle.ods(spalten, zeilen, "Selbsttest"),
                )
            ),
            "Tabellen aus Excel und LibreOffice lesen",
        )
        self.pruefen(
            self.sichern_und_wiederherstellen(),
            "Datensicherung verschlüsseln und wiederherstellen",
        )
        self.stdout.write(self.style.SUCCESS("Selbsttest bestanden."))

    def sichern_und_wiederherstellen(self):
        """Wie auf einem frischen Rechner (Abnahme Phase 4): neue Datenbank, ein Beleg,
        sichern, beides löschen, wiederherstellen. Die Datenbank dieser Installation
        bleibt dabei unberührt."""
        echt = connections["default"]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as ordner:
            ordner = Path(ordner)
            probe = type(echt)({**echt.settings_dict, "NAME": ordner / "db.sqlite3"})
            connections["default"] = probe
            try:
                with override_settings(DATA_DIR=ordner):
                    call_command("migrate", interactive=False, verbosity=0)
                    Kontakt.objects.create(firmenname="Kunde", ort="Teststadt")
                    beleg = ordner / "archiv" / "selbsttest" / "beleg.pdf"
                    beleg.parent.mkdir(parents=True)
                    beleg.write_bytes(b"%PDF-1.7 Selbsttest")
                    sicherung.einrichten("Selbsttest der Datensicherung")
                    datei, _ = sicherung.sichern()
                    Kontakt.objects.all().delete()
                    beleg.unlink()
                    sicherung.wiederherstellen(datei, "Selbsttest der Datensicherung")
                    return (
                        Kontakt.objects.filter(firmenname="Kunde").exists()
                        and beleg.read_bytes() == b"%PDF-1.7 Selbsttest"
                    )
            finally:
                probe.close()
                connections["default"] = echt

    def pruefen(self, bedingung, was):
        if not bedingung:
            raise CommandError(f"Fehlgeschlagen: {was}")
        self.stdout.write(f"in Ordnung: {was}")
