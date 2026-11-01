"""Notfall ohne zweiten Inhaber: Sperre aufheben, auf Wunsch die Zwei-Faktor-Anmeldung aus.

    Kontorfreund entsperren <email> [--ohne-zwei-faktor]

Ein neues Kennwort setzt `Kontorfreund changepassword <email>`. Wer diese Befehle
ausführen kann, hat ohnehin Zugriff auf den Datenordner.
"""

from django.core.management.base import BaseCommand, CommandError

from konten.models import Benutzer


class Command(BaseCommand):
    help = "Hebt die Sperre nach Fehlversuchen auf; auf Wunsch auch die Zwei-Faktor-Anmeldung."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "--ohne-zwei-faktor",
            action="store_true",
            help="Zwei-Faktor-Anmeldung ausschalten, etwa wenn das Telefon fehlt.",
        )

    def handle(self, email, ohne_zwei_faktor, **optionen):
        benutzer = Benutzer.objects.filter(email__iexact=email).first()
        if not benutzer:
            raise CommandError(f"Kein Konto mit der E-Mail-Adresse {email}.")
        benutzer.entsperren()
        meldung = f"Die Sperre für {benutzer.email} ist aufgehoben."
        if ohne_zwei_faktor:
            benutzer.totp_geheimnis = ""
            benutzer.save(update_fields=["totp_geheimnis"])
            meldung += " Die Zwei-Faktor-Anmeldung ist ausgeschaltet."
        self.stdout.write(meldung)
