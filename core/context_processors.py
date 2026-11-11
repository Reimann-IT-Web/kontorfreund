from datetime import date

from django.conf import settings
from django.urls import reverse

from angebote.models import Angebot
from archive.models import Pruefung
from artikel.models import Artikel
from auftraege.models import Auftragsbestaetigung
from contacts.models import Kontakt
from invoicing.models import Rechnung
from wiedervorlagen.models import Wiedervorlage

from . import firmen
from .hilfe import THEMEN
from .models import Firmendaten
from .navigation import NAVIGATION
from .templatetags.kf import euro


def product(request):
    return {
        "product_name": f"{settings.PRODUCT_NAME} ({settings.PRODUCT_EDITION})",
        "marke": settings.PRODUCT_NAME,
        "edition": settings.PRODUCT_EDITION,
        "version": settings.VERSION,
    }


def navigation(request):
    """Seitenleiste mit Zählern, Suchindex (Strg+K) und Firmendaten für jede Seite."""
    mehrere = firmen.mehrere(settings.HAUPTORDNER)
    if not request.user.is_authenticated:
        return {"firma": Firmendaten.laden(), "mehrere_firmen": mehrere}
    if request.user.ist_pruefer:
        # Kein Suchindex und keine Zähler: Prüfer sehen nur den Datenzugriff.
        return {"firma": Firmendaten.laden(), "mehrere_firmen": False}
    kontakte = Kontakt.objects.filter(archiviert=False)
    anzahl = kontakte.count()
    faellig = (
        Wiedervorlage.offen_fuer(request.user).filter(faellig__lte=date.today()).count()
    )
    pruefung = Pruefung.letzte()
    befunde = pruefung.befunde if pruefung else []
    zahlen = {
        "adressen": {"zahl": str(anzahl)} if anzahl else {},
        "ablage": {
            "zahl": str(len(befunde)),
            "warnung": "1 abgelegte Datei fehlt oder ist verändert"
            if len(befunde) == 1
            else f"{len(befunde)} abgelegte Dateien fehlen oder sind verändert",
        }
        if befunde
        else {},
        "wiedervorlagen": {
            "zahl": str(faellig),
            "warnung": f"{faellig} Wiedervorlage{'n' if faellig > 1 else ''} fällig",
        }
        if faellig
        else {},
    }
    eintraege = [dict(e, **zahlen.get(e["key"], {})) for e in NAVIGATION]
    liste = reverse("contacts:liste")
    suchindex = [
        {
            "titel": "Neue Rechnung",
            "info": "Angebote & Rechnungen",
            "url": reverse("invoicing:neu"),
        },
        {
            "titel": "Neues Angebot",
            "info": "Angebote & Rechnungen",
            "url": reverse("angebote:neu"),
        },
        {
            "titel": "Neue Auftragsbestätigung",
            "info": "Angebote & Rechnungen",
            "url": reverse("auftraege:neu"),
        },
        {"titel": "Neue Adresse", "info": "Adressen", "url": reverse("contacts:neu")},
        {
            "titel": "Neue Wiedervorlage",
            "info": "Wiedervorlagen",
            "url": reverse("wiedervorlagen:neu"),
        },
        {"titel": "Neuer Artikel", "info": "Artikel", "url": reverse("artikel:neu")},
        {
            "titel": "Rechnungsausgangsbuch",
            "info": "Auswertungen",
            "url": reverse("auswertungen:rechnungsausgangsbuch"),
        },
        {
            "titel": "DATEV-Export",
            "info": "Auswertungen",
            "url": reverse("auswertungen:datev"),
        },
        {
            "titel": "E-Rechnung hochladen",
            "info": "Eingangsrechnungen",
            "url": reverse("eingang:liste"),
        },
        {
            "titel": "Firmen",
            "info": "Firma wechseln"
            + (" oder anlegen" if request.user.ist_inhaber else ""),
            "url": reverse("core:firmen"),
        },
        {
            "titel": "Mein Konto",
            "info": "Kennwort und Zwei-Faktor-Anmeldung",
            "url": reverse("konten:konto"),
        },
    ]
    if request.user.ist_inhaber:
        suchindex += [
            {
                "titel": "Einstellungen",
                "info": "Firmendaten",
                "url": reverse("core:einstellungen"),
            },
            {
                "titel": "Benutzer",
                "info": "Konten für Mitarbeiter",
                "url": reverse("konten:benutzer"),
            },
            {
                "titel": "Benachrichtigungen",
                "info": "Telegram-Nachricht, wenn etwas ansteht",
                "url": reverse("benachrichtigungen:einstellungen"),
            },
            {
                "titel": "Datensicherung",
                "info": "Sichern und wiederherstellen",
                "url": reverse("backups:uebersicht"),
            },
            {
                "titel": "Updates",
                "info": f"Installiert: Version {settings.VERSION}",
                "url": reverse("core:updates"),
            },
            {
                "titel": "Protokoll",
                "info": "Wer wann was geändert hat",
                "url": reverse("protokoll:liste"),
            },
        ]
    suchindex += [
        {
            "titel": f"Hilfe: {t['titel']}",
            "info": t["kurz"],
            "url": reverse("core:hilfe_thema", args=[t["slug"]]),
        }
        for t in THEMEN
    ]
    # Bei Firmen gehört der Ansprechpartner dazu: Heißen viele Firmen gleich
    # (etwa „Betreuung“), findet man die Adresse nur über ihn oder die Straße.
    suchindex += [
        {
            "titel": k.anzeigename,
            "info": " · ".join(
                t for t in [k.kundennummer, k.ansprechpartner, k.strasse, k.ort] if t
            ),
            "url": f"{liste}?q={k.kundennummer}&offen={k.pk}",
        }
        for k in kontakte[:500]
    ]
    suchindex += _belege()
    suchindex += [
        {
            "titel": a.bezeichnung,
            "info": f"{a.artikelnummer} · {euro(a.preis)} / {a.einheit}",
            "url": reverse("artikel:bearbeiten", args=[a.pk]),
        }
        for a in Artikel.objects.filter(aktiv=True)[:500]
    ]
    return {
        "navigation": eintraege,
        "suchindex": suchindex,
        "firma": Firmendaten.laden(),
        "mehrere_firmen": mehrere,
        "ablage_befunde": befunde,
    }


# Je Belegart die neuesten; ältere stehen im Verlauf der Adresse.
BELEGE_IM_INDEX = 200


def _belege():
    """Rechnungen, Angebote und Auftragsbestätigungen für die Suche (Spezifikation G-2).

    Gefunden werden sie über Nummer, Empfänger, Ansprechpartner, Ort und Datum.
    Belege gesperrter Adressen fehlen wie die Adressen selbst.
    """
    eintraege = []
    for modell, art, url in [
        (Rechnung, None, "invoicing:bearbeiten"),
        (Angebot, "Angebot", "angebote:bearbeiten"),
        (Auftragsbestaetigung, "Auftragsbestätigung", "auftraege:bearbeiten"),
    ]:
        belege = (
            modell.objects.select_related("kontakt")
            .exclude(kontakt__gesperrt_am__isnull=False)
            .order_by("-datum", "-pk")[:BELEGE_IM_INDEX]
        )
        for b in belege:
            name = art or b.bezeichnung
            k = b.kontakt
            empfaenger = [k.anzeigename, k.ansprechpartner, k.ort] if k else []
            eintraege.append(
                {
                    "titel": f"{name} {b.nummer}" if b.nummer else f"{name} (Entwurf)",
                    "info": " · ".join(
                        t for t in [*empfaenger, f"{b.datum:%d.%m.%Y}"] if t
                    ),
                    "url": reverse(url, args=[b.pk]),
                }
            )
    return eintraege
