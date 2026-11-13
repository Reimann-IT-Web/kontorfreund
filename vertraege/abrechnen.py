"""Rechnungsentwürfe aus Verträgen anlegen (Spezifikation B-10).

Im Voraus: Am ersten Tag eines Zeitraums entsteht ein Entwurf über den ganzen Zeitraum,
datiert auf den Tag, an dem er entsteht. Lief Kontorfreund am Stichtag nicht, holt der
nächste Lauf jeden offenen Zeitraum einzeln nach. Vor jedem Zeitraum legt er auf Wunsch
eine Wiedervorlage an, einmal je Zeitraum; nicht, wenn der Vertrag erst nach dem Tag der
Wiedervorlage angelegt wurde (dann ist gerade alles besprochen). Angestoßen von der Middleware nach
einer angemeldeten Anfrage und vom Befehl `erinnern` vor den Telegram-Nachrichten.
"""

import logging
import time
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from contacts.models import Anschrift
from invoicing.beleg import briefanrede, grussformel
from invoicing.models import Position as Rechnungsposition
from invoicing.models import Rechnung, positionsfelder
from wiedervorlagen.models import Wiedervorlage

from .models import Vertrag, monate_spaeter

logger = logging.getLogger(__name__)

# Höchstens so oft je Prozess nachsehen (Sekunden), damit nicht jede Anfrage abfragt.
ABSTAND = 600
_naechste_suche = 0.0


def vorgaben(kontakt, firma):
    """Texte wie bei einer neuen Rechnung."""
    return {
        "kopftext": f"{briefanrede(kontakt)}\n\n"
        "vereinbarungsgemäß berechne ich Ihnen für den unten genannten Zeitraum:",
        "fusstext": grussformel(firma),
    }


def entwurf(vertrag, beginn, heute):
    """Rechnungsentwurf für den Zeitraum ab `beginn`, mit den Positionen des Vertrags."""
    von, bis = vertrag.zeitraum(beginn)
    kontakt = vertrag.kontakt
    rechnung = Rechnung.objects.create(
        vertrag=vertrag,
        kontakt=kontakt,
        anschrift=kontakt.anschrift_fuer(Anschrift.Art.RECHNUNG),
        datum=heute,
        leistung_von=von,
        leistung_bis=bis,
        zahlungsziel=vertrag.zahlungsziel,
        rabatt_prozent=vertrag.rabatt_prozent,
        steuerfall=vertrag.steuerfall,
        betreff=vertrag.betreff,
        kopftext=vertrag.kopftext,
        fusstext=vertrag.fusstext,
    )
    Rechnungsposition.objects.bulk_create(
        Rechnungsposition(rechnung=rechnung, **positionsfelder(p))
        for p in vertrag.positionen.all()
    )
    return rechnung


def nachfragen(heute):
    """Wiedervorlage vor einer Verlängerung: Fortsetzung und Preis klären."""
    for vertrag in Vertrag.objects.filter(
        nachfragen__gt=0, kontakt__gesperrt_am__isnull=True
    ).select_related("kontakt"):
        beginn = vertrag.naechster
        am = beginn - timedelta(days=vertrag.nachfragen)
        if (
            not vertrag.laeuft
            or vertrag.nachgefragt_fuer == beginn
            or heute < am
            or timezone.localdate(vertrag.angelegt) > am
        ):
            continue
        with transaction.atomic():
            updated = (
                Vertrag.objects.filter(pk=vertrag.pk)
                .exclude(nachgefragt_fuer=beginn)
                .update(nachgefragt_fuer=beginn)
            )
            if updated:
                Wiedervorlage.objects.create(
                    titel=f"Vertrag „{vertrag}“ ab {beginn:%d.%m.%Y}: Fortsetzung "
                    "und Preis klären",
                    faellig=max(heute, am),
                    kontakt=vertrag.kontakt,
                    notiz="Möchte der Kunde den Vertrag fortsetzen, zum selben Preis? "
                    "Wenn nicht, tragen Sie im Vertrag das Ende ein oder ändern die "
                    f"Positionen; der Entwurf entsteht am {beginn:%d.%m.%Y}.",
                )


def faellige(heute=None):
    """Legt für jeden fälligen Zeitraum einen Entwurf an und liefert die neuen."""
    heute = heute or date.today()
    nachfragen(heute)
    neu = []
    offen = Vertrag.objects.filter(
        naechster__lte=heute, kontakt__gesperrt_am__isnull=True
    ).values_list("pk", flat=True)
    for pk in offen:
        while True:
            with transaction.atomic():
                # Neu gelesen in der Transaktion: Ein zweiter Lauf zur selben Zeit sieht
                # den weitergezählten Zeitraum (SQLite schreibt nur nacheinander).
                vertrag = Vertrag.objects.select_related("kontakt").get(pk=pk)
                beginn = vertrag.naechster
                if beginn > heute or not vertrag.laeuft:
                    break
                try:
                    with transaction.atomic():
                        neu.append(entwurf(vertrag, beginn, heute))
                except IntegrityError:
                    pass  # gibt es schon
                Vertrag.objects.filter(pk=pk).update(
                    naechster=monate_spaeter(beginn, vertrag.rhythmus)
                )
    return neu


def bei_bedarf():
    """Höchstens alle zehn Minuten nachsehen; Fehler dürfen keine Seite verhindern."""
    global _naechste_suche
    if time.monotonic() < _naechste_suche:
        return
    _naechste_suche = time.monotonic() + ABSTAND
    try:
        faellige()
    except Exception:
        logger.exception("Entwürfe aus Verträgen fehlgeschlagen")
