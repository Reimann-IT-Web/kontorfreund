"""Adressen und Rechnungsentwürfe aus der Vorschau anlegen (Spezifikation B-11)."""

from datetime import timedelta

from django.db import transaction

from contacts.models import Anschrift, Kategorie, Kontakt, Kontaktweg
from core.templatetags.kf import euro
from invoicing.beleg import briefanrede, grussformel
from invoicing.models import Position, Rechnung

from . import texte
from .models import Serie, Teilnehmer


def anlegen(liste, auswertung, angaben, vorlage, firma, zuordnung):
    """Serie mit je gewähltem Teilnehmer einem Entwurf; die Liste wird gelöscht."""
    with transaction.atomic():
        serie = Serie.objects.create(
            termin=angaben["termin"],
            thema=angaben["thema"],
            link=angaben["link"],
            leistungsdatum=angaben["leistungsdatum"],
            datum=angaben["datum"],
            preis=angaben["preis"],
            zahlungsziel=angaben["zahlungsziel"],
        )
        kunde = Kategorie.vorgabe(Kategorie.Kennung.KUNDE)
        kontakte = {}
        for z in auswertung.teilnehmer:
            if not z.waehlen:
                continue
            kontakt = kontakte.get(z.schluessel)
            if kontakt is None:
                kontakt = _kontakt(z, kunde)
                kontakte[z.schluessel] = kontakt
            _mandat_merken(kontakt, z)
            _entwurf(serie, z, kontakt, angaben, vorlage, firma)
        vorlage.preis = angaben["preis"]
        vorlage.zahlungsziel = angaben["zahlungsziel"]
        vorlage.zuordnung = zuordnung
        vorlage.save()
        liste.delete()
    return serie


def _kontakt(z, kunde):
    """Vorhandene Adresse, auf Wunsch mit den Angaben der Liste, oder eine neue."""
    daten = z.daten
    kontakt = z.kontakt
    if kontakt is None:
        kontakt = Kontakt(nummer=z.kdnr, land="Deutschland", **daten)
        _pruefen(kontakt)
        kontakt.save()
        kontakt.kategorien.add(kunde)
        weitere = (
            [("Handy", z.werte.get("handy", ""))] if z.werte.get("telefon") else []
        )
        weitere.append(("Fax", z.werte.get("fax", "")))
        for bezeichnung, wert in weitere:
            if wert:
                Kontaktweg.objects.create(
                    kontakt=kontakt,
                    art=Kontaktweg.Art.TELEFON,
                    bezeichnung=bezeichnung,
                    wert=wert[:254],
                )
        return kontakt
    geaendert = set()
    if z.uebernehmen:
        for feld, _, wert, _ in z.abweichungen:
            setattr(kontakt, feld, wert)
            geaendert.add(feld)
    # Eine Firma ohne Ansprechpartner bekommt den ersten Teilnehmer.
    if kontakt.art == Kontakt.Art.FIRMA and not kontakt.nachname:
        for feld in ("anrede", "titel", "vorname", "nachname"):
            setattr(kontakt, feld, daten[feld])
            geaendert.add(feld)
    # Archiviert sind Adressen mit Belegen; für neue Rechnungen werden sie wieder aktiv.
    kontakt.archiviert = False
    _pruefen(kontakt, geaendert)
    kontakt.save()
    return kontakt


def _pruefen(kontakt, felder=None):
    """Dieselben Regeln wie im Formular (Länge, E-Mail, Pflichtfelder), vor dem Speichern.

    Bei einer vorhandenen Adresse nur die Felder, die die Liste ändert, damit ein
    älterer Fehler an anderer Stelle die Serie nicht aufhält. Nummer und Anzeigename
    setzt `Kontakt.save` selbst.
    """
    alle = {f.name for f in Kontakt._meta.concrete_fields}
    ohne = {"nummer", "anzeigename"} | (alle - felder if felder is not None else set())
    kontakt.full_clean(exclude=sorted(ohne), validate_unique=False)


def _mandat_merken(kontakt, z):
    """Das Datum aus „Sepa erteilt“ gilt, die Referenz bleibt, wenn es schon eine gibt."""
    if not (z.mandat_datum and z.mandat_referenz):
        return
    if kontakt.mandat_referenz and kontakt.mandat_datum == z.mandat_datum:
        return
    if not kontakt.mandat_referenz:
        if (
            Kontakt.objects.filter(mandat_referenz=z.mandat_referenz)
            .exclude(pk=kontakt.pk)
            .exists()
        ):
            return
        kontakt.mandat_referenz = z.mandat_referenz
    kontakt.mandat_datum = z.mandat_datum
    kontakt.save(update_fields=["mandat_referenz", "mandat_datum", "geaendert"])


def _entwurf(serie, z, kontakt, angaben, vorlage, firma):
    werte = {
        "termin": serie.termin,
        "thema": serie.thema,
        "link": serie.link,
        "datum": f"{serie.datum:%d.%m.%Y}",
        "faellig": f"{serie.datum + timedelta(days=serie.zahlungsziel):%d.%m.%Y}",
        "kundennummer": kontakt.kundennummer,
    }
    rechnung = Rechnung.objects.create(
        kontakt=kontakt,
        anschrift=kontakt.anschrift_fuer(Anschrift.Art.RECHNUNG),
        datum=serie.datum,
        leistung_von=serie.leistungsdatum,
        zahlungsziel=serie.zahlungsziel,
        zahlweg=z.zahlweg,
        steuerfall=firma.umsatzsteuer,
    )
    Position.objects.create(
        rechnung=rechnung,
        nr=1,
        bezeichnung=texte.fuellen(vorlage.position, werte)[:200],
        menge=1,
        einheit="",
        preis=serie.preis,
        steuersatz=angaben["steuersatz"],
    )
    werte["betrag"] = euro(rechnung.summen()[2])
    teilnehmer = Teilnehmer.objects.create(
        serie=serie,
        rechnung=rechnung,
        zeile=z.nr,
        anrede=z.daten["anrede"],
        titel=z.daten["titel"],
        vorname=z.daten["vorname"],
        nachname=z.daten["nachname"],
        email=z.email,
        beilage=z.beilage,
    )
    rechnung.betreff = texte.fuellen(vorlage.betreff, werte)[:200]
    rechnung.kopftext = "\n\n".join(
        t
        for t in (briefanrede(teilnehmer), texte.fuellen(vorlage.kopftext, werte))
        if t
    )
    rechnung.fusstext = "\n\n".join(
        t for t in (texte.fuellen(vorlage.fusstext, werte), grussformel(firma)) if t
    )
    rechnung.save()
    return rechnung
