"""Platzhalter in den Texten der Serienrechnungen (B-11).

Die Texte der Rechnung füllt Kontorfreund beim Anlegen der Entwürfe; danach sind sie
im Entwurf frei änderbar. Nummer, Rechnungsdatum und Fälligkeit stehen erst beim
Festschreiben fest (das Datum rückt dann womöglich auf heute), deshalb kennt sie nur
die E-Mail, die danach entsteht.
"""

from invoicing.beleg import unbekannte_platzhalter as unbekannte

RECHNUNG = ("termin", "thema", "link", "betrag", "kundennummer")
MAIL = RECHNUNG + ("nummer", "datum", "faellig")

__all__ = ["MAIL", "RECHNUNG", "fuellen", "liste", "unbekannte"]


def liste(namen):
    teile = ["{" + n + "}" for n in namen]
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def fuellen(text, werte):
    for name, wert in werte.items():
        text = text.replace("{" + name + "}", wert)
    return text.replace("\r\n", "\n").strip()
