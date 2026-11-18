"""Platzhalter in den Texten der Serienrechnungen (B-11).

Die Texte der Rechnung füllt Kontorfreund beim Anlegen der Entwürfe; danach sind sie
im Entwurf frei änderbar. Die Nummer gibt es erst beim Festschreiben, deshalb kennt
nur die E-Mail {nummer}.
"""

import re

RECHNUNG = ("termin", "thema", "link", "betrag", "datum", "faellig", "kundennummer")
MAIL = RECHNUNG + ("nummer",)


def unbekannte(text, erlaubt):
    namen = dict.fromkeys(re.findall(r"\{([^{}]*)\}", text))
    return [n for n in namen if n not in erlaubt]


def liste(namen):
    teile = ["{" + n + "}" for n in namen]
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def fuellen(text, werte):
    for name, wert in werte.items():
        text = text.replace("{" + name + "}", wert)
    return text.replace("\r\n", "\n").strip()
