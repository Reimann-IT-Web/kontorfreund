"""Nachrichten über einen eigenen Telegram-Bot; die Bot-API ist kostenlos.

Siehe https://core.telegram.org/bots/api. Den Bot legt der Nutzer bei @BotFather an.
Verbunden wird über einen Link mit Code (`https://t.me/<bot>?start=<code>`): Tippt
er darauf auf „Starten“, schickt Telegram „/start <code>“, und `chat_finden` erkennt
daran seinen Chat. Fremde, die den Bot finden, können sich so nicht verbinden.

Knöpfe unter einer Nachricht (`senden` mit `knoepfe`) liefert Telegram als
„callback_query“ über getUpdates (`neuigkeiten`); `knoepfe.py` wertet sie aus.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

ADRESSE = "https://api.telegram.org/bot{schluessel}/{methode}"
SCHLUESSEL = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")


class _OhneUmleitung(urllib.request.HTTPRedirectHandler):
    """Eine Umleitung wäre eine Antwort von woanders; sie gilt als Fehler (ASVS 15.3.2)."""

    def redirect_request(self, *args, **kwargs):
        return None


_oeffnen = urllib.request.build_opener(_OhneUmleitung).open


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
        with _oeffnen(anfrage, timeout=20) as antwort:
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


# Telegram merkt sich die Auswahl; beide Aufrufe nennen deshalb immer dieselbe.
ARTEN = json.dumps(["message", "callback_query"])


def chat_finden(schluessel, code):
    """Chat, in dem jemand über den Link mit diesem Code auf „Starten“ getippt hat."""
    for eintrag in reversed(_aufrufen(schluessel, "getUpdates", allowed_updates=ARTEN)):
        nachricht = eintrag.get("message") or {}
        chat = nachricht.get("chat") or {}
        if nachricht.get("text") == f"/start {code}" and chat.get("type") == "private":
            return str(chat["id"])
    return None


def senden(schluessel, chat, text, knoepfe=None):
    """Nachricht, auf Wunsch mit Knöpfen darunter: [(Beschriftung, Daten), …]."""
    werte = {"chat_id": chat, "text": text}
    if knoepfe:
        werte["reply_markup"] = json.dumps(
            {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in knoepfe]]}
        )
    _aufrufen(schluessel, "sendMessage", **werte)


def neuigkeiten(schluessel, ab):
    """Was seit `ab` (update_id) beim Bot einging; frühere gelten damit als gelesen."""
    return _aufrufen(
        schluessel, "getUpdates", offset=ab, timeout=0, allowed_updates=ARTEN
    )


def antworten(schluessel, frage, text=""):
    """Bestätigt einen Knopfdruck; nach einigen Minuten lehnt Telegram das ab."""
    _aufrufen(schluessel, "answerCallbackQuery", callback_query_id=frage, text=text)


def aendern(schluessel, chat, nachricht, text):
    """Ersetzt den Text einer Nachricht; ihre Knöpfe verschwinden dabei."""
    _aufrufen(
        schluessel, "editMessageText", chat_id=chat, message_id=nachricht, text=text
    )
