"""Erzeugt konten/daten/kennwoerter.txt: Kennwörter aus Datenlecks, die lang genug für
die Kennwortregeln wären (konten.kennwort) und deshalb eigens abgelehnt werden.

Quelle: SecLists (https://github.com/danielmiessler/SecLists, MIT-Lizenz), Ordner
Passwords/Common-Credentials: Pwdb_top-1000000.txt, 100k-most-used-passwords-NCSC.txt
und Language-Specific/German_common-password-list-top-100000.txt.

    uv run python werkzeuge/kennwoerter_erzeugen.py konten/daten/kennwoerter.txt <Stand> <Dateien …>
"""

import sys

# Wie konten.kennwort.MINDESTLAENGE; kürzere lehnen die Regeln ohnehin ab.
MINDESTLAENGE = 12

KOPF = """\
# Kennwörter aus Datenlecks mit mindestens {laenge} Zeichen, kleingeschrieben, eins je Zeile.
# Quelle: SecLists (https://github.com/danielmiessler/SecLists), Stand {stand}, Dateien
# {dateien}.
# SecLists steht unter der MIT-Lizenz, Copyright (c) 2018 Daniel Miessler; der Lizenztext
# steht in SecLists-LICENSE.txt daneben.
# Erzeugt mit werkzeuge/kennwoerter_erzeugen.py.
"""


def erzeugen(ziel, stand, quellen):
    alle = set()
    for quelle in quellen:
        with open(quelle, encoding="utf-8", errors="replace") as f:
            for zeile in f:
                kennwort = zeile.strip().lower()
                if (
                    len(kennwort) >= MINDESTLAENGE
                    and kennwort.isprintable()
                    and "�" not in kennwort
                ):
                    alle.add(kennwort)
    namen = ", ".join(q.replace("\\", "/").rsplit("/", 1)[-1] for q in quellen)
    with open(ziel, "w", encoding="utf-8", newline="\n") as f:
        f.write(KOPF.format(laenge=MINDESTLAENGE, stand=stand, dateien=namen))
        f.writelines(f"{k}\n" for k in sorted(alle))
    return len(alle)


if __name__ == "__main__":
    print(erzeugen(sys.argv[1], sys.argv[2], sys.argv[3:]), "Kennwörter")
