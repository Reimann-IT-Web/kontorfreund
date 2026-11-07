"""Startet Kontorfreund als Einzelplatz-Programm (Spezifikation D-3).

Ohne Angaben: Datenbank auf den neuesten Stand bringen (vorher entsteht eine
Sicherung, siehe backups.sicherung.vor_update), den Server auf diesem Rechner
starten und den Browser öffnen. Läuft Kontorfreund schon, öffnet es nur den
Browser. Mit --hintergrund startet es ohne Browser in einem minimierten Fenster,
etwa beim Anmelden an Windows. Mit anderen Angaben wirkt es wie manage.py für die
zuletzt geöffnete Firma, z. B. `Kontorfreund changepassword <email>`.

Der Server läuft als eigener Prozess. Das Startprogramm startet ihn neu, wenn im
Programm eine andere Firma geöffnet wird (core/firmen.py), und lässt alle fünf
Minuten die fälligen Benachrichtigungen jeder Firma senden (benachrichtigungen).

Die Daten liegen im Benutzerordner (`datenordner`), nicht im Programmordner,
damit ein Update oder Deinstallieren sie nicht berührt. Liegt portabel.txt neben
dem Programm (portable Fassung, ZIP für Windows), liegen sie im Ordner „Daten“
daneben, und der Server läuft auf 8766, damit sie sich nie mit einer installierten
Fassung auf demselben Rechner vermischen: Läuft die schon, öffnete der Start sonst
deren Browser (`laeuft_schon`). APP_DATA_DIR und APP_PORT ändern Ort und Port,
APP_KEIN_BROWSER=1 lässt den Browser zu.
"""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from core import firmen


def programmordner():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def portabel():
    return (programmordner() / "portabel.txt").is_file()


PORT = int(os.environ.get("APP_PORT") or (8766 if portabel() else 8765))
ADRESSE = f"http://127.0.0.1:{PORT}/"
# Intern: der Prozess, den das Startprogramm für den Server startet.
SERVER = "--server"
HINTERGRUND = "--hintergrund"
# Abstand zwischen zwei Runden der Benachrichtigungen, in Sekunden.
TAKT = 300


def datenordner():
    if portabel():
        return programmordner() / "Daten"
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


def selbst():
    """Aufruf dieses Programms, als Installationspaket oder aus dem Quellcode."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


def minimieren():
    if sys.platform == "win32":
        import ctypes

        fenster = ctypes.windll.kernel32.GetConsoleWindow()
        if fenster:
            ctypes.windll.user32.ShowWindow(fenster, 6)  # SW_MINIMIZE


def server():
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


def erinnern(haupt):
    """Für jede Firma mit eingeschalteten Benachrichtigungen die fälligen senden."""
    time.sleep(30)  # erst den Server starten lassen
    while True:
        for firma in firmen.alle(haupt):
            if firmen.benachrichtigt(firma.ordner):
                try:
                    subprocess.run(  # noqa: S603 – das eigene Programm
                        [*selbst(), "erinnern"],
                        env={**os.environ, **firmen.umgebung(haupt, firma.kennung)},
                        timeout=TAKT,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    pass
        time.sleep(TAKT)


def betreiben(haupt, hintergrund):
    """Server starten und nach einem Firmenwechsel mit der neuen Firma neu starten."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    threading.Thread(target=erinnern, args=(haupt,), daemon=True).start()
    browser = not hintergrund
    while True:
        umgebung = {
            **os.environ,
            **firmen.umgebung(haupt, firmen.aktiv(haupt)),
            "APP_NEUSTART": "1",
        }
        if not browser:
            umgebung["APP_KEIN_BROWSER"] = "1"
        kind = subprocess.Popen([*selbst(), SERVER], env=umgebung)  # noqa: S603
        try:
            code = kind.wait()
        except BaseException:  # Strg+C oder beendet: den Server mitnehmen
            kind.terminate()
            raise
        if code != firmen.WECHSELN:
            return code
        browser = False


def main():
    if portabel():
        os.environ["APP_PORTABEL"] = "1"  # für config/settings.py
    if "APP_HAUPTORDNER" not in os.environ:
        haupt = Path(os.environ.get("APP_DATA_DIR") or datenordner())
        os.environ.update(firmen.umgebung(haupt, firmen.aktiv(haupt)))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    argumente = sys.argv[1:]
    if argumente == [SERVER]:
        server()
        return
    if argumente and argumente != [HINTERGRUND]:
        from django.core.management import execute_from_command_line

        execute_from_command_line(sys.argv)
        return
    hintergrund = bool(argumente)
    if laeuft_schon():
        if not hintergrund:
            browser_oeffnen()
        return
    if hintergrund:
        minimieren()
    try:
        sys.exit(betreiben(Path(os.environ["APP_HAUPTORDNER"]), hintergrund))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
