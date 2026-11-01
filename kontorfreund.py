"""Startet Kontorfreund als Einzelplatz-Programm (Spezifikation D-3).

Ohne Angaben: Datenbank auf den neuesten Stand bringen (vorher entsteht eine
Sicherung, siehe backups.sicherung.vor_update), den Server auf diesem Rechner
starten und den Browser öffnen. Läuft Kontorfreund schon, öffnet es nur den
Browser. Mit Angaben wirkt es wie manage.py, z. B. `Kontorfreund changepassword
<email>`.

Die Daten liegen im Benutzerordner (`datenordner`), nicht im Programmordner,
damit ein Update oder Deinstallieren sie nicht berührt. APP_DATA_DIR und APP_PORT
ändern Ort und Port, APP_KEIN_BROWSER=1 lässt den Browser zu.
"""

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

PORT = int(os.environ.get("APP_PORT", "8765"))
ADRESSE = f"http://127.0.0.1:{PORT}/"


def datenordner():
    if sys.platform == "win32":
        basis = Path(
            os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        )
    elif sys.platform == "darwin":
        basis = Path.home() / "Library" / "Application Support"
    else:
        basis = Path(
            os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        )
    return basis / "Kontorfreund"


def laeuft_schon():
    with socket.socket() as verbindung:
        return verbindung.connect_ex(("127.0.0.1", PORT)) == 0


def browser_oeffnen():
    if os.environ.get("APP_KEIN_BROWSER") != "1":
        webbrowser.open(ADRESSE)


def main():
    os.environ.setdefault("APP_DATA_DIR", str(datenordner()))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if len(sys.argv) > 1:
        from django.core.management import execute_from_command_line

        execute_from_command_line(sys.argv)
        return
    if laeuft_schon():
        browser_oeffnen()
        return

    import django
    from django.conf import settings
    from django.core.management import call_command

    django.setup()
    print(f"Kontorfreund {settings.VERSION}")
    print(f"Daten: {settings.DATA_DIR}")
    call_command("migrate", interactive=False, verbosity=0)

    from waitress import serve

    from config.wsgi import application

    print(f"Läuft unter {ADRESSE}")
    print("Dieses Fenster bitte offen lassen. Zum Beenden einfach schließen.")
    threading.Timer(1, browser_oeffnen).start()
    serve(application, host="127.0.0.1", port=PORT, threads=8)


if __name__ == "__main__":
    main()
