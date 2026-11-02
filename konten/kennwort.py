"""Kennwortregeln nach Spezifikation K-5 und OWASP ASVS 6.2: mindestens 12 Zeichen,
nichts Häufiges, nichts aus Datenlecks und nicht nur Namen von Firma und Benutzer."""

import re
from functools import cache
from pathlib import Path

from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError

MINDESTLAENGE = 12
# Kennwörter aus Datenlecks ab MINDESTLAENGE Zeichen (werkzeuge/kennwoerter_erzeugen.py).
DATENLECKS = Path(__file__).parent / "daten" / "kennwoerter.txt"

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

# Wörter, die jeder errät, der das Programm kennt (ASVS 6.1.2). Dazu kommen die Wörter
# aus Firmenname, Marke und Inhaber sowie aus Name und E-Mail-Adresse des Benutzers.
KONTEXT = {
    "kontorfreund",
    "kontor",
    "inhaber",
    "mitarbeiter",
    "pruefer",
    "prüfer",
    "betriebspruefung",
    "betriebsprüfung",
    "finanzamt",
    "rechnung",
    "rechnungen",
}


@cache
def _datenlecks():
    with DATENLECKS.open(encoding="utf-8") as f:
        return frozenset(z.rstrip("\n") for z in f if not z.startswith("#"))


def _kontext(benutzer):
    from core.models import Firmendaten

    firma = Firmendaten.laden()
    texte = [firma.name, firma.marke, firma.inhaber]
    if benutzer is not None:
        texte += [benutzer.name, benutzer.email]
    woerter = {
        wort
        for text in texte
        for wort in re.split(r"[\W\d_]+", (text or "").lower())
        if len(wort) >= 4
    }
    # Lange Wörter zuerst, damit „kontorfreund“ nicht als „kontor“ + „freund“ übrig bleibt.
    return sorted(KONTEXT | woerter, key=len, reverse=True)


class Kennwortregeln:
    """Lehnt kurze, häufige und aus Datenlecks bekannte Kennwörter ab, auch mit
    Ziffern und Zeichen dazwischen (pass-wort-1234), sowie solche, die nur aus Namen von
    Firma, Benutzer und Programm bestehen (reimann2026!)."""

    def __init__(self):
        self.haeufig = DEUTSCH | CommonPasswordValidator().passwords

    def validate(self, password, user=None):
        if len(password) < MINDESTLAENGE:
            raise ValidationError(
                f"Das Kennwort braucht mindestens {MINDESTLAENGE} Zeichen.",
                code="password_too_short",
            )
        klein = password.lower().strip()
        if klein in _datenlecks():
            raise ValidationError(
                "Dieses Kennwort stammt aus einem Datenleck. Angreifer probieren "
                "solche Kennwörter als Erstes aus. Bitte wählen Sie ein anderes.",
                code="password_breached",
            )
        rest = klein
        for wort in _kontext(user):
            rest = rest.replace(wort, " ")
        kern = re.sub(r"[\d\W_]+", "", rest)
        wiederholt = re.fullmatch(r"(.+?)\1+", kern)
        if rest != klein and len(kern) < 4:
            raise ValidationError(
                "Das Kennwort besteht fast nur aus Ihrem Namen, dem Namen der Firma "
                "oder des Programms. Das errät man leicht.",
                code="password_too_similar",
            )
        if (
            len(kern) < 4
            or kern in self.haeufig
            or (
                wiederholt and (len(wiederholt[1]) < 4 or wiederholt[1] in self.haeufig)
            )
        ):
            raise ValidationError(
                "Dieses Kennwort ist zu verbreitet und leicht zu erraten. "
                "Nehmen Sie zum Beispiel drei, vier Wörter, die nichts miteinander zu tun haben.",
                code="password_too_common",
            )

    def get_help_text(self):
        return f"Mindestens {MINDESTLAENGE} Zeichen, kein verbreitetes Kennwort."
