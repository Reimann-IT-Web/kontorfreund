from django.conf import settings
from django.urls import reverse

from contacts.models import Kontakt

from .models import Firmendaten
from .navigation import NAVIGATION


def product(request):
    return {"product_name": f"{settings.PRODUCT_NAME} ({settings.PRODUCT_EDITION})"}


def navigation(request):
    """Seitenleiste mit Zählern, Suchindex (Strg+K) und Firmendaten für jede Seite."""
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
        {"titel": "Neue Adresse", "info": "Adressen", "url": reverse("contacts:neu")},
        {
            "titel": "Einstellungen",
            "info": "Firmendaten",
            "url": reverse("core:einstellungen"),
        },
        {
            "titel": "Datensicherung",
            "info": "Sichern und wiederherstellen",
            "url": reverse("backups:uebersicht"),
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
    return {
        "navigation": eintraege,
        "suchindex": suchindex,
        "firma": Firmendaten.laden(),
    }
