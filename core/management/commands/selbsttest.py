from datetime import date
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.templatetags.static import static
from django.test import Client

from contacts import plz
from contacts.models import Kontakt
from core.models import Firmendaten
from eingang import lesen
from invoicing import beleg
from invoicing.models import Rechnung


class Command(BaseCommand):
    help = (
        "Prüft, ob alle Teile des Programms vorhanden sind und arbeiten: Seiten, "
        "Kennwörter, PDF und E-Rechnung. Für das Installationspaket; alles, was "
        "dabei in der Datenbank entsteht, wird zurückgenommen."
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
            transaction.set_rollback(True)
        self.pruefen(b"AtkinsonHyperlegibleNext" in pdf, "PDF mit eigener Schrift")
        self.pruefen(len(beleg.seitenbilder(pdf)) == 1, "Seitenbild")
        d = lesen.auswerten(lesen.einlesen(pdf)[1])
        self.pruefen(
            d["nummer"] == "T-1" and d["summen"]["zahlbetrag"] == Decimal("95.20"),
            "ZUGFeRD schreiben und lesen",
        )
        self.stdout.write(self.style.SUCCESS("Selbsttest bestanden."))

    def pruefen(self, bedingung, was):
        if not bedingung:
            raise CommandError(f"Fehlgeschlagen: {was}")
        self.stdout.write(f"in Ordnung: {was}")
