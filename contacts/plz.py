"""Orte zu deutschen Postleitzahlen, damit „Ort“ sich nach der PLZ von selbst ausfüllt.

Daten: daten/plz.tsv (PLZ, Ort, Zahl der Straßen), erzeugt mit werkzeuge/plz_erzeugen.py
aus OpenPLZ (© OpenStreetMap-Mitwirkende, ODbL 1.0). Teilen sich mehrere Gemeinden eine
PLZ, gilt ein Ort als der richtige, wenn mindestens 90 % der Straßen zu ihm gehören;
sonst wählt der Nutzer.
"""

from functools import cache
from pathlib import Path

DATEI = Path(__file__).parent / "daten" / "plz.tsv"
EINDEUTIG = 0.9


@cache
def _tabelle():
    tabelle = {}
    with DATEI.open(encoding="utf-8") as f:
        for zeile in f:
            if not zeile.startswith("#"):
                plz, ort, strassen = zeile.rstrip("\n").split("\t")
                tabelle.setdefault(plz, []).append((ort, int(strassen)))
    return tabelle


def orte(plz):
    """Orte zur PLZ, der größte zuerst, und der eindeutige Ort (sonst "")."""
    eintraege = _tabelle().get(plz.strip(), [])
    gesamt = sum(n for _, n in eintraege)
    eindeutig = (
        eintraege[0][0] if eintraege and eintraege[0][1] >= EINDEUTIG * gesamt else ""
    )
    return [ort for ort, _ in eintraege], eindeutig
