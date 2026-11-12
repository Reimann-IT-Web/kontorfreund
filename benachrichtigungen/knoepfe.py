"""Knöpfe unter den Telegram-Nachrichten: Entwurf senden, mahnen, als bezahlt buchen.

Jeder Knopf trägt Aktion, Rechnung und eine Signatur (HMAC mit dem SECRET_KEY), und
angenommen wird er nur aus dem verbundenen Chat; ein veränderter oder fremder Knopf
bewirkt nichts. Ausgewertet wird in jeder Runde von `nachrichten.erinnern`, also mit
bis zu fünf Minuten Verzug. Die Position (`Einstellung.gelesen_bis`) wird vor der
Aktion gespeichert, damit ein Absturz nichts doppelt verschickt.

Was ein Knopf tut, ist dasselbe wie in der Oberfläche: festschreiben mit denselben
Prüfungen, versenden an die E-Mail-Adresse der Adresse mit dem vorgeschlagenen Text,
mahnen mit den Vorgaben der Mahnstufe. Im Protokoll steht der Empfänger der
Benachrichtigungen als Benutzer. Die Antwort in Telegram nennt Nummern und Beträge,
keine Namen und keine E-Mail-Adressen.
"""

import base64
import hashlib
import hmac
import logging
import smtplib
from datetime import date, timedelta
from types import SimpleNamespace

from django.conf import settings

from core import umsatz
from core.models import Firmendaten
from core.templatetags.kf import euro
from invoicing import beleg, versand
from invoicing.models import Rechnung
from protokoll.erfassen import ANFRAGE
from zahlungen import mahnen
from zahlungen.models import Mahnstufe, Zahlung

from . import telegram
from .models import Einstellung, Gemeldet

logger = logging.getLogger(__name__)


def _signatur(text):
    schluessel = f"telegram-knopf:{settings.SECRET_KEY}".encode()
    roh = hmac.new(schluessel, text.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(roh)[:16].decode()


def knopf(titel, *teile):
    """(Beschriftung, Daten) für telegram.senden; höchstens 64 Bytes Daten."""
    text = ":".join(str(t) for t in teile)
    return (titel, f"{text}:{_signatur(text)}")


def _lesen(daten):
    text, _, signatur = (daten or "").rpartition(":")
    if not text or not hmac.compare_digest(signatur, _signatur(text)):
        return None
    return text.split(":")


def entwurf_knoepfe(rechnung):
    return [
        knopf("Festschreiben und senden", "e", rechnung.pk),
        knopf("Später", "se", rechnung.pk),
    ]


def mahn_knoepfe(rechnung, stufe, mit_senden):
    return [
        *([knopf("Senden", "m", rechnung.pk, stufe.stufe)] if mit_senden else []),
        knopf("Ist bezahlt", "b", rechnung.pk),
        knopf("Später", "sm", rechnung.pk, stufe.stufe),
    ]


def verarbeiten(einstellung):
    """Knopfdrücke seit der letzten Runde ausführen und in Telegram beantworten."""
    for neu in telegram.neuigkeiten(
        einstellung.bot_schluessel, einstellung.gelesen_bis
    ):
        einstellung.gelesen_bis = neu["update_id"] + 1
        Einstellung.objects.filter(pk=1).update(gelesen_bis=einstellung.gelesen_bis)
        if frage := neu.get("callback_query"):
            _beantworten(einstellung, frage)


def _beantworten(einstellung, frage):
    nachricht = frage.get("message") or {}
    chat = str((nachricht.get("chat") or {}).get("id", ""))
    von = str((frage.get("from") or {}).get("id", ""))
    teile = _lesen(frage.get("data"))
    if chat != einstellung.chat or von != einstellung.chat or teile is None:
        logger.warning("Telegram-Knopf abgelehnt (fremder Chat oder verändert)")
        return
    # Wie eine Anfrage des Inhabers, der die Benachrichtigungen eingerichtet hat.
    anfrage = ANFRAGE.set(SimpleNamespace(user=einstellung.empfaenger))
    try:
        ergebnis = ausfuehren(teile)
    except Exception:
        logger.exception("Telegram-Knopf fehlgeschlagen: %s", teile)
        ergebnis = "Das hat nicht geklappt. Bitte in Kontorfreund erledigen."
    finally:
        ANFRAGE.reset(anfrage)
    schluessel = einstellung.bot_schluessel
    try:
        telegram.antworten(schluessel, frage["id"])
    except telegram.Fehler:
        pass  # Telegram nimmt Antworten nur wenige Minuten lang an.
    text = f"{nachricht.get('text', '')}\n\n{ergebnis}".strip()
    try:
        telegram.aendern(schluessel, chat, nachricht.get("message_id"), text)
    except telegram.Fehler:
        # Nachrichten älter als 48 Stunden lassen sich nicht mehr ändern.
        telegram.senden(schluessel, chat, text)


def ausfuehren(teile):
    """Führt einen Knopf aus und liefert die Antwort für Telegram."""
    aktion, nr, *rest = teile
    if aktion == "e":
        return entwurf_senden(int(nr))
    if aktion == "m":
        return mahnung_senden(int(nr), int(rest[0]))
    if aktion == "b":
        return bezahlt(int(nr))
    if aktion == "se":
        Gemeldet.objects.filter(anlass="entwurf", schluessel=nr).delete()
        return "Kommt morgen wieder in der Übersicht."
    if aktion == "sm":
        Gemeldet.objects.filter(
            anlass="mahnstufe", schluessel=f"{nr}:{rest[0]}"
        ).delete()
        return "Kommt morgen wieder in der Übersicht."
    raise ValueError(aktion)


def _verschicken(beleg_, firma, vorschlag, was):
    if not (firma.mail_bereit and vorschlag["an"]):
        return (
            f"{was} ist erstellt. Für den Versand fehlt eine E-Mail-Adresse; "
            "bitte in Kontorfreund verschicken."
        )
    try:
        versand.senden(beleg_, firma, **vorschlag)
    except (smtplib.SMTPException, OSError) as fehler:
        logger.warning("Versand über Telegram fehlgeschlagen: %s", fehler)
        return f"{was} ist erstellt, aber nicht gesendet: {versand.fehlertext(fehler)}"
    return f"✓ {was} gesendet."


def entwurf_senden(pk):
    """Rechnungsentwurf festschreiben wie im Editor und an den Kunden senden."""
    rechnung = Rechnung.objects.select_related("kontakt").filter(pk=pk).first()
    if rechnung is None:
        return "Den Entwurf gibt es nicht mehr."
    if not rechnung.ist_entwurf:
        return f"Schon erledigt: Rechnung {rechnung.nummer}."
    firma = Firmendaten.laden()
    # Wie beim Öffnen im Editor (B-8): Festgeschrieben wird mit dem heutigen Datum.
    rechnung.datum = max(rechnung.datum, date.today())
    if (
        rechnung.steuerfall == Rechnung.Steuerfall.KLEINUNTERNEHMER
        and not rechnung.ist_korrektur
        and umsatz.ueber_laufender_grenze(rechnung.datum.year, rechnung.summen()[0])
    ):
        return (
            f"Nicht festgeschrieben: Mit dieser Rechnung läge Ihr Umsatz über "
            f"{euro(umsatz.LAUFEND)}. Bitte in Kontorfreund auf 19 % umstellen."
        )
    fehlt = rechnung.fehlende_angaben(firma)
    if fehlt:
        return f"Nicht festgeschrieben, es fehlt: {', '.join(fehlt)}."
    beleg.festschreiben(rechnung, firma)
    return _verschicken(
        rechnung,
        firma,
        versand.vorschlag(rechnung, firma),
        f"Rechnung {rechnung.nummer} über {euro(rechnung.brutto)}",
    )


def _offene(pk):
    return next((r for r in mahnen.posten() if r.pk == pk), None)


def mahnung_senden(pk, nummer):
    """Die fällige Mahnstufe mit ihren Vorgaben erstellen und senden."""
    rechnung = _offene(pk)
    naechste = mahnen.naechste_stufe(rechnung, Mahnstufe.alle()) if rechnung else None
    if not naechste or naechste[0].stufe != nummer:
        return "Schon erledigt: Diese Stufe ist nicht mehr fällig."
    stufe, firma, heute = naechste[0], Firmendaten.laden(), date.today()
    pauschale = stufe.pauschale and not rechnung.kontakt.ist_verbraucher
    aufstellung = mahnen.berechnen(
        rechnung, stufe.stufe, heute, stufe.gebuehr, stufe.zinsen, pauschale
    )
    if aufstellung["fehler"]:
        return "Nicht erstellt: " + " ".join(aufstellung["fehler"])
    mahnung = mahnen.erstellen(
        rechnung,
        firma,
        stufe.stufe,
        heute,
        heute + timedelta(days=stufe.frist),
        stufe.text_fuer(rechnung),
        stufe.gebuehr,
        stufe.zinsen,
        pauschale,
    )
    return _verschicken(
        mahnung,
        firma,
        mahnen.mail_vorschlag(mahnung, firma),
        f"{mahnung.bezeichnung} zu Rechnung {rechnung.nummer} über "
        f"{euro(mahnung.gesamt)}",
    )


def bezahlt(pk):
    """Den offenen Betrag als Überweisung von heute buchen."""
    rechnung = _offene(pk)
    if rechnung is None or rechnung.offen <= 0:
        return "Schon erledigt: Die Rechnung ist bezahlt."
    betrag = rechnung.offen
    Zahlung.objects.create(
        rechnung=rechnung,
        datum=date.today(),
        betrag=betrag,
        art=Zahlung.Art.UEBERWEISUNG,
        notiz="Über Telegram als bezahlt gemeldet",
    )
    hinweis = (
        " Mahnkosten und Zinsen sind nicht mitgebucht."
        if mahnen.offene_nebenkosten(rechnung)
        else ""
    )
    return (
        f"✓ Zahlung über {euro(betrag)} zu Rechnung {rechnung.nummer} gebucht, mit "
        f"Datum von heute.{hinweis} Stimmt das Datum nicht, löschen Sie die Buchung "
        "in Kontorfreund und buchen neu."
    )
