"""Zeitleiste einer Adresse (Spezifikation K-2): alles, was zu ihr geschah, neueste zuerst.

Von Hand erfasste Vorgänge kommen aus `Vorgang`, abgelegte Dateien aus `Datei` (an
einem Vorgang stehen sie bei ihm, sonst als eigener Punkt); Angebote,
Auftragsbestätigungen, Rechnungen, Zahlungen, Mahnungen, erledigte Wiedervorlagen,
Altbelege und Eingangsrechnungen werden aus ihren eigenen Daten gelesen, damit nichts
doppelt gespeichert ist.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone

from angebote.models import Angebot
from auftraege.models import Auftragsbestaetigung
from invoicing.models import Rechnung
from zahlungen.models import Mahnung, Zahlung

from .models import Datei, Vorgang

ICONS = {
    Vorgang.Art.NOTIZ: "pencil",
    Vorgang.Art.ANRUF: "phone",
    Vorgang.Art.EMAIL: "mail",
    Vorgang.Art.TERMIN: "calendar",
    "wiedervorlage": "check",
    "beleg": "file",
    "zahlung": "banknote",
    "dokument": "paperclip",
}
ARTEN = [
    ("", "Alles"),
    *Vorgang.Art.choices,
    ("wiedervorlage", "Wiedervorlagen"),
    ("beleg", "Belege"),
    ("zahlung", "Zahlungen und Mahnungen"),
    ("dokument", "Dokumente"),
]


@dataclass
class Punkt:
    tag: date
    uhrzeit: time | None
    art: str
    titel: str
    text: str = ""
    url: str = ""
    betrag: Decimal | None = None
    benutzer: str = ""
    vorgang: Vorgang | None = None
    neues_fenster: bool = False
    # Vorbelegung für „Wiedervorlage“ aus diesem Eintrag, als Teil einer Adresse.
    nachfassen: str = ""
    dateien: list = field(default_factory=list)

    @property
    def icon(self):
        return ICONS[self.art]


def _lokal(zeitpunkt):
    zeitpunkt = timezone.localtime(zeitpunkt)
    return zeitpunkt.date(), zeitpunkt.time().replace(second=0, microsecond=0)


def punkte(kontakt):
    ergebnis = []
    vorhanden = Datei.objects.filter(geloescht_am__isnull=True)
    for v in kontakt.vorgaenge.select_related("benutzer").prefetch_related(
        Prefetch("dateien", queryset=vorhanden)
    ):
        ergebnis.append(
            Punkt(
                *_lokal(v.zeitpunkt),
                art=v.art,
                titel=v.betreff or v.get_art_display(),
                text=v.text,
                benutzer=str(v.benutzer or ""),
                vorgang=v,
                dateien=list(v.dateien.all()),
                nachfassen=urlencode(
                    {"titel": f"Nachfassen: {v.betreff or v.get_art_display()}"}
                ),
            )
        )
    for d in vorhanden.filter(kontakt=kontakt, vorgang=None).select_related("benutzer"):
        ergebnis.append(
            Punkt(
                *_lokal(d.erstellt),
                art="dokument",
                titel=d.name,
                url=reverse("historie:datei", args=[d.pk]),
                benutzer=str(d.benutzer or ""),
                neues_fenster=d.vorschau,
            )
        )
    for w in kontakt.wiedervorlagen.filter(erledigt_am__isnull=False).select_related(
        "erledigt_von"
    ):
        ergebnis.append(
            Punkt(
                *_lokal(w.erledigt_am),
                art="wiedervorlage",
                titel=f"Erledigt: {w.titel}",
                text=w.ergebnis,
                url=reverse("wiedervorlagen:bearbeiten", args=[w.pk]),
                benutzer=str(w.erledigt_von or ""),
            )
        )
    for a in kontakt.angebote.filter(status=Angebot.Status.FERTIG):
        antwort = (
            f"{a.get_antwort_display()} am {a.antwort_am:%d.%m.%Y}" if a.antwort else ""
        )
        ergebnis.append(
            Punkt(
                a.datum,
                None,
                art="beleg",
                titel=f"Angebot {a.nummer}",
                text=" · ".join(t for t in (a.betreff, antwort) if t),
                url=reverse("angebote:bearbeiten", args=[a.pk]),
                betrag=a.brutto,
                nachfassen=urlencode(
                    {"titel": f"Angebot {a.nummer} nachfassen", "angebot": a.pk}
                ),
            )
        )
    for a in kontakt.auftraege.filter(status=Auftragsbestaetigung.Status.FERTIG):
        ergebnis.append(
            Punkt(
                a.datum,
                None,
                art="beleg",
                titel=f"Auftragsbestätigung {a.nummer}",
                text=a.betreff,
                url=reverse("auftraege:bearbeiten", args=[a.pk]),
                betrag=a.brutto,
            )
        )
    rechnungen = kontakt.rechnungen.filter(status=Rechnung.Status.FESTGESCHRIEBEN)
    for r in rechnungen:
        ergebnis.append(
            Punkt(
                r.datum,
                None,
                art="beleg",
                titel=f"{r.bezeichnung} {r.nummer}",
                text=r.betreff,
                url=reverse("invoicing:bearbeiten", args=[r.pk]),
                betrag=r.brutto,
                nachfassen=urlencode(
                    {"titel": f"Rechnung {r.nummer}: Zahlung prüfen", "rechnung": r.pk}
                ),
            )
        )
    for z in Zahlung.objects.filter(rechnung__in=rechnungen).select_related("rechnung"):
        ergebnis.append(
            Punkt(
                z.datum,
                None,
                art="zahlung",
                titel=f"{z.get_art_display()} zu Rechnung {z.rechnung.nummer}",
                text=z.notiz,
                url=reverse("invoicing:bearbeiten", args=[z.rechnung_id])
                + "#zahlungen",
                betrag=z.betrag,
            )
        )
    for m in Mahnung.objects.filter(rechnung__in=rechnungen).select_related("rechnung"):
        ergebnis.append(
            Punkt(
                m.datum,
                None,
                art="zahlung",
                titel=str(m),
                text=f"Zahlen bis {m.frist:%d.%m.%Y}",
                url=reverse("zahlungen:mahnung", args=[m.pk]),
                betrag=m.gesamt,
            )
        )
    for b in kontakt.altbelege.all():
        ergebnis.append(
            Punkt(
                b.datum,
                None,
                art="beleg",
                titel=f"{b.get_art_display()} {b.nummer}",
                text="aus dem bisherigen Programm",
                url=reverse("archive:datei", args=[b.pk]),
                betrag=b.betrag,
                neues_fenster=True,
            )
        )
    for e in kontakt.eingangsrechnungen.all():
        ergebnis.append(
            Punkt(
                e.datum,
                None,
                art="beleg",
                titel=f"Eingangsrechnung {e.nummer}",
                url=reverse("eingang:anzeigen", args=[e.pk]),
                betrag=e.brutto,
            )
        )
    # Ohne Uhrzeit (Belege, Zahlungen) steht ein Eintrag am Ende seines Tages.
    return sorted(
        ergebnis,
        key=lambda p: datetime.combine(p.tag, p.uhrzeit or time.min),
        reverse=True,
    )
