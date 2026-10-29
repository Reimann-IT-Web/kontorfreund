"""Kennwortregeln nach Spezifikation K-5: mindestens 12 Zeichen, nichts Häufiges."""

import re

from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError

MINDESTLAENGE = 12

# Häufige deutsche Kennwörter und Wortstämme, ergänzend zu Djangos englischer Liste.
DEUTSCH = {
    "passwort",
    "kennwort",
    "geheim",
    "hallo",
    "hallohallo",
    "qwertz",
    "qwertzuiop",
    "asdfgh",
    "schatz",
    "schatzi",
    "sonne",
    "sommer",
    "winter",
    "fruehling",
    "herbst",
    "fussball",
    "fußball",
    "ichliebedich",
    "willkommen",
    "deutschland",
    "berlin",
    "hamburg",
    "muenchen",
    "münchen",
    "schalke",
    "bayern",
    "borussia",
    "admin",
    "administrator",
    "test",
    "benutzer",
    "rechnung",
    "kontorfreund",
}


class Kennwortregeln:
    """Lehnt kurze und häufige Kennwörter ab, auch mit angehängten Ziffern (passwort1234)."""

    def __init__(self):
        self.englisch = CommonPasswordValidator().passwords

    def validate(self, password, user=None):
        if len(password) < MINDESTLAENGE:
            raise ValidationError(
                f"Das Kennwort braucht mindestens {MINDESTLAENGE} Zeichen.",
                code="password_too_short",
            )
        klein = password.lower().strip()
        kern = re.sub(r"^[\d\W_]+|[\d\W_]+$", "", klein)
        if not kern or {klein, kern} & (DEUTSCH | self.englisch):
            raise ValidationError(
                "Dieses Kennwort ist zu verbreitet und leicht zu erraten. "
                "Nehmen Sie zum Beispiel drei, vier Wörter, die nichts miteinander zu tun haben.",
                code="password_too_common",
            )

    def get_help_text(self):
        return f"Mindestens {MINDESTLAENGE} Zeichen, kein verbreitetes Kennwort."
