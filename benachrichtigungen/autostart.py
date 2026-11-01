"""Kontorfreund beim Anmelden an Windows im Hintergrund starten (kontorfreund.py
--hintergrund), damit SMS und tägliche Sicherung auch ohne Doppelklick kommen.

Der Eintrag steht unter HKCU\\...\\Run; das Deinstallieren entfernt ihn
(packaging/windows/kontorfreund.iss).
"""

import sys

SCHLUESSEL = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Kontorfreund"


def moeglich():
    """Nur im installierten Programm unter Windows."""
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def _befehl():
    return f'"{sys.executable}" --hintergrund'


def an():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHLUESSEL) as schluessel:
            wert, _ = winreg.QueryValueEx(schluessel, NAME)
    except OSError:
        return False
    return wert == _befehl()


def setzen(ein):
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, SCHLUESSEL, 0, winreg.KEY_SET_VALUE
    ) as schluessel:
        if ein:
            winreg.SetValueEx(schluessel, NAME, 0, winreg.REG_SZ, _befehl())
        else:
            try:
                winreg.DeleteValue(schluessel, NAME)
            except FileNotFoundError:
                pass
