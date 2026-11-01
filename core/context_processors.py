from django.conf import settings
from django.urls import reverse

from artikel.models import Artikel
from contacts.models import Kontakt

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
    if not request.user.is_authenticated:
        return {"firma": Firmendaten.laden()}
    kontakte = Kontakt.objects.filter(archiviert=False)
    anzahl = kontakte.count()
    eintraege = [
        dict(e, zahl=str(anzahl)) if e["key"] == "adressen" and anzahl else e
        for e in NAVIGATION
    ]
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
        {"titel": "Neue Adresse", "info": "Adressen", "url": reverse("contacts:neu")},
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
                "titel": "Datensicherung",
                "info": "Sichern und wiederherstellen",
                "url": reverse("backups:uebersicht"),
            },
            {
                "titel": "Protokoll",
                "info": "Wer wann was geändert hat",
                "url": reverse("protokoll:liste"),
            },
        ]
    suchindex += [
        {
            "titel": k.anzeigename,
            "info": " · ".join(t for t in [k.kundennummer, k.ort] if t),
            "url": f"{liste}?q={k.kundennummer}&offen={k.pk}",
        }
        for k in kontakte[:500]
    ]
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
    }
