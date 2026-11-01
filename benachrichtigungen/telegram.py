"""Nachrichten über einen eigenen Telegram-Bot; die Bot-API ist kostenlos.

Siehe https://core.telegram.org/bots/api. Den Bot legt der Nutzer bei @BotFather an.
Verbunden wird über einen Link mit Code (`https://t.me/<bot>?start=<code>`): Tippt
er darauf auf „Starten“, schickt Telegram „/start <code>“, und `chat_finden` erkennt
daran seinen Chat. Fremde, die den Bot finden, können sich so nicht verbinden.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

ADRESSE = "https://api.telegram.org/bot{schluessel}/{methode}"
SCHLUESSEL = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")


class Fehler(Exception):
    pass


def _meldung(code, text):
    if code in (401, 404):
        return (
            "Telegram kennt diesen Bot-Schlüssel nicht. Bitte so einfügen, wie "
            "BotFather ihn geschickt hat."
        )
    if code == 403:
        return (
            "Der Bot ist in Telegram gestoppt. Öffnen Sie den Chat mit dem Bot und "
            "tippen Sie auf „Neu starten“."
        )
    if "chat not found" in text:
        return "Telegram findet den Chat nicht mehr. Bitte neu verbinden."
    return f"Telegram hat abgelehnt: {text or code}."


def _aufrufen(schluessel, methode, **werte):
    # Schema und Rechner stehen fest; der Schlüssel landet nur im Pfad.
    anfrage = urllib.request.Request(  # noqa: S310
        ADRESSE.format(
            schluessel=urllib.parse.quote(schluessel, safe=":"), methode=methode
        ),
        data=urllib.parse.urlencode(werte).encode(),
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:  # noqa: S310 – feste https-Adresse
            daten = json.load(antwort)
    except urllib.error.HTTPError as fehler:
        try:
            text = json.load(fehler).get("description", "")
        except ValueError:
            text = ""
        raise Fehler(_meldung(fehler.code, text)) from None
    except OSError:
        raise Fehler("Keine Verbindung zu Telegram. Ist der Rechner online?") from None
    except ValueError:
        raise Fehler("Telegram hat unerwartet geantwortet.") from None
    if not daten.get("ok"):
        raise Fehler(_meldung(daten.get("error_code"), daten.get("description", "")))
    return daten["result"]


def bot(schluessel):
    """Benutzername des Bots, etwa für den Link t.me/<name>."""
    return _aufrufen(schluessel, "getMe")["username"]


def chat_finden(schluessel, code):
    """Chat, in dem jemand über den Link mit diesem Code auf „Starten“ getippt hat."""
    for eintrag in reversed(_aufrufen(schluessel, "getUpdates")):
        nachricht = eintrag.get("message") or {}
        chat = nachricht.get("chat") or {}
        if nachricht.get("text") == f"/start {code}" and chat.get("type") == "private":
            return str(chat["id"])
    return None


def senden(schluessel, chat, text):
    _aufrufen(schluessel, "sendMessage", chat_id=chat, text=text)
