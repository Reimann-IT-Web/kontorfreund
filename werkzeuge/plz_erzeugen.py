"""Erzeugt contacts/daten/plz.tsv (Orte zu deutschen Postleitzahlen) aus OpenPLZ.

Quelle: src/de/osm/streets.updated.csv aus https://github.com/openpotato/openplzapi.data
(aus OpenStreetMap, © OpenStreetMap-Mitwirkende, Open Database License 1.0). Je PLZ
zählt das Skript die Straßen jeder Gemeinde. Gemeinden mit höchstens zwei Straßen neben
einer mit mindestens 20 sind Ungenauigkeiten an PLZ-Grenzen und fallen weg.

    uv run python werkzeuge/plz_erzeugen.py streets.updated.csv contacts/daten/plz.tsv 2025-11-22
"""

import collections
import csv
import re
import sys

KOPF = """\
# Orte zu deutschen Postleitzahlen: PLZ, Ort (Gemeinde), Zahl der Straßen mit dieser PLZ
# in diesem Ort. Quelle: OpenPLZ API Data (https://github.com/openpotato/openplzapi.data),
# Stand {stand}, aus OpenStreetMap, © OpenStreetMap-Mitwirkende. Lizenz: Open Database
# License 1.0 (https://opendatacommons.org/licenses/odbl/1-0/); diese Datei steht unter
# derselben Lizenz. Erzeugt mit werkzeuge/plz_erzeugen.py.
"""


def erzeugen(quelle, ziel, stand):
    strassen = collections.defaultdict(collections.Counter)
    with open(quelle, encoding="utf-8", newline="") as f:
        for zeile in csv.DictReader(f):
            plz, ort = zeile["PostalCode"], zeile["Locality"].strip()
            if re.fullmatch(r"\d{5}", plz) and ort and "\t" not in ort:
                strassen[plz][ort] += 1
    with open(ziel, "w", encoding="utf-8", newline="\n") as f:
        f.write(KOPF.format(stand=stand))
        for plz in sorted(strassen):
            orte = sorted(strassen[plz].items(), key=lambda e: (-e[1], e[0]))
            for ort, anzahl in orte:
                if anzahl > 2 or orte[0][1] < 20:
                    f.write(f"{plz}\t{ort}\t{anzahl}\n")


if __name__ == "__main__":
    erzeugen(*sys.argv[1:4])
