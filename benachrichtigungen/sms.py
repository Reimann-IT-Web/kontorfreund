"""SMS über seven.io (Kiel), siehe https://docs.seven.io/en/rest-api/endpoints/sms."""

import json
import urllib.error
import urllib.parse
import urllib.request

ADRESSE = "https://gateway.seven.io/api/sms"

# Antwortcodes von seven.io, die der Nutzer selbst beheben kann.
MELDUNGEN = {
    "202": "Die Handynummer stimmt nicht. Bitte prüfen.",
    "403": "Für diese Handynummer ist das Tageslimit bei seven.io erreicht.",
    "500": "Das Guthaben bei seven.io ist aufgebraucht. Bitte dort aufladen.",
    "501": "Das Ausgabenlimit bei seven.io ist erreicht.",
    "900": "seven.io kennt den API-Schlüssel nicht. Bitte prüfen.",
    "902": "Der API-Schlüssel darf keine SMS senden. Bitte bei seven.io einen "
    "Schlüssel mit dem Recht „SMS“ anlegen.",
}


class Fehler(Exception):
    pass


def senden(schluessel, nummer, text):
    anfrage = urllib.request.Request(
        ADRESSE,
        data=urllib.parse.urlencode({"to": nummer, "text": text}).encode(),
        headers={"X-Api-Key": schluessel, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:  # noqa: S310 – feste https-Adresse
            daten = json.load(antwort)
    except urllib.error.HTTPError as fehler:
        code = "900" if fehler.code in (401, 403) else f"HTTP {fehler.code}"
    except OSError:
        raise Fehler("Keine Verbindung zu seven.io. Ist der Rechner online?") from None
    except ValueError:
        code = "unbekannt"
    else:
        code = str(daten.get("success", "") if isinstance(daten, dict) else daten)
    if code != "100":
        raise Fehler(
            MELDUNGEN.get(code, f"seven.io hat die SMS abgelehnt (Code {code or '–'}).")
        )
