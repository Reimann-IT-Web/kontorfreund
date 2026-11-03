"""Änderungsprotokoll (Spezifikation K-6): wer wann was angelegt, geändert oder gelöscht hat.

Signale an den Modellen in ERFASST schreiben die Einträge, in derselben Transaktion
wie die Änderung. Positionen von Rechnungen und Angeboten protokollieren die Editoren
als Ganzes (`positionen_text`), weil sie beim Speichern alle neu angelegt werden.
"""

from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.text import capfirst

from core.templatetags.kf import euro, zahl

from .models import GESCHWAERZT, Eintrag

# Die laufende Anfrage, gesetzt von middleware.anfrage_merken: daraus der Benutzer.
ANFRAGE = ContextVar("anfrage", default=None)

ERFASST = [
    "contacts.Kontakt",
    "contacts.Kategorie",
    "invoicing.Rechnung",
    "angebote.Angebot",
    "auftraege.Auftragsbestaetigung",
    "artikel.Artikel",
    "zahlungen.Zahlung",
    "zahlungen.Mahnung",
    "zahlungen.Mahnstufe",
    "zahlungen.Basiszins",
    "core.Firmendaten",
    "konten.Benutzer",
    "archive.Altbeleg",
    "eingang.Eingangsrechnung",
    "auswertungen.Datev",
    "wiedervorlagen.Wiedervorlage",
    "historie.Vorgang",
    "historie.Datei",
    "benachrichtigungen.Einstellung",
    "dokumentation.Angaben",
    "dokumentation.Fassung",
]
# Stehen nie im Klartext im Protokoll.
VERDECKT = {"password", "mail_passwort", "bot_schluessel"}
# Ändert sich bei jeder Anmeldung, gehört nicht zu den Geschäftsdaten.
OHNE = {"last_login"}


def _felder(modell):
    """Felder, die der Nutzer sieht; ohne technische (nicht editierbar) und JSON."""
    return [
        f
        for f in modell._meta.concrete_fields
        if f.editable
        and not f.primary_key
        and f.name not in OHNE
        and not isinstance(f, models.JSONField)
    ]


def _name(feld_oder_meta):
    """Bezeichnung als fertiger Text; verbose_name ist oft ein übersetzbarer Platzhalter."""
    return str(capfirst(feld_oder_meta.verbose_name))


def _roh(objekt, feld):
    wert = feld.value_from_object(objekt)
    return bytes(wert) if isinstance(feld, models.BinaryField) else wert


def _wert(objekt, feld):
    """Wert als Text, wie ihn der Nutzer kennt."""
    wert = _roh(objekt, feld)
    if wert in (None, "", b""):
        return ""
    if feld.name in VERDECKT:
        return "•••"
    if isinstance(feld, models.BinaryField):
        return "Bild"
    if feld.choices:
        return str(getattr(objekt, f"get_{feld.name}_display")())
    if feld.is_relation:
        return str(getattr(objekt, feld.name))
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, datetime):
        return f"{timezone.localtime(wert):%d.%m.%Y %H:%M}"
    if isinstance(wert, date):
        return f"{wert:%d.%m.%Y}"
    if isinstance(wert, Decimal):
        return zahl(wert, feld.decimal_places)
    return str(wert)


def eintragen(aktion, objekt=None, aenderungen=(), beschreibung=None):
    """Ohne Objekt nur mit Beschreibung, etwa für eine Entscheidung des Inhabers."""
    anfrage = ANFRAGE.get()
    benutzer = getattr(anfrage, "user", None)
    angemeldet = bool(benutzer and benutzer.is_authenticated)
    Eintrag.objects.create(
        aktion=aktion,
        benutzer_id=benutzer.pk if angemeldet else None,
        wer=str(benutzer) if angemeldet else "",
        art=_name(objekt._meta) if objekt else "",
        objekt_id=str(objekt.pk) if objekt else "",
        beschreibung=(str(objekt) if beschreibung is None else beschreibung)[:300],
        aenderungen=list(aenderungen),
    )


def schwaerzen(objekte, grund=GESCHWAERZT):
    """Einträge zu diesen Objekten schwärzen, auch zu schon gelöschten."""
    arten = {}
    for objekt in objekte:
        arten.setdefault(_name(objekt._meta), []).append(objekt.pk)
    for art, pks in arten.items():
        Eintrag.schwaerzen(art, pks, grund)


def anmeldung(aktion, wer, benutzer=None, grund=""):
    """Anmeldung oder Fehlversuch; `wer` ist bei Fehlversuchen die eingegebene Adresse."""
    Eintrag.objects.create(
        aktion=aktion,
        benutzer_id=benutzer.pk if benutzer else None,
        wer=wer[:254],
        beschreibung=grund,
    )


def positionen_text(positionen):
    return "\n".join(
        " ".join(
            t
            for t in (f"{p.nr}.", zahl(p.menge), p.einheit, p.bezeichnung)
            + ("à", euro(p.preis))
            if t
        )
        for p in positionen
    )


def positionen_geaendert(beleg, vorher):
    """Nach dem Speichern im Editor: Eintrag, wenn sich die Positionen geändert haben."""
    nachher = positionen_text(beleg.positionen.all())
    if nachher != vorher:
        eintragen(Eintrag.Aktion.GEAENDERT, beleg, [["Positionen", vorher, nachher]])


# ---------- Signale ----------


def vorher(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding:
        return
    instance._protokoll_vorher = sender._default_manager.filter(pk=instance.pk).first()


def gespeichert(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    felder = _felder(sender)
    if created:
        aenderungen = [[_name(f), "", w] for f in felder if (w := _wert(instance, f))]
        eintragen(Eintrag.Aktion.ANGELEGT, instance, aenderungen)
        return
    alt = instance.__dict__.pop("_protokoll_vorher", None)
    if alt is None:
        return
    if update_fields:
        felder = [f for f in felder if f.name in update_fields]
    aenderungen = [
        [_name(f), _wert(alt, f), _wert(instance, f)]
        for f in felder
        if _roh(alt, f) != _roh(instance, f)
    ]
    if aenderungen:
        eintragen(Eintrag.Aktion.GEAENDERT, instance, aenderungen)


def geloescht(sender, instance, **kwargs):
    eintragen(Eintrag.Aktion.GELOESCHT, instance)
