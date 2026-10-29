from datetime import date, timedelta

from django.shortcuts import render

from contacts.models import Kontakt
from core.models import Firmendaten

EINHEITEN = ["Stück", "Std.", "Tag", "Monat", "Pauschale"]


def neu(request):
    firma = Firmendaten.laden()
    empfaenger = request.GET.get("empfaenger", "")
    heute = date.today()
    return render(
        request,
        "invoicing/rechnung.html",
        {
            "bereich": "rechnungen",
            "kontakte": Kontakt.objects.filter(archiviert=False),
            "empfaenger": int(empfaenger) if empfaenger.isdigit() else None,
            "datum": heute,
            "faellig": heute + timedelta(days=14),
            # Nummernkreis kommt mit Phase 2; bis dahin die erste Nummer des Jahres.
            "naechste_nummer": f"RE-{heute.year}-0001",
            "einheiten": EINHEITEN,
            "steuerfall": "kleinunternehmer" if firma.kleinunternehmer else "regel",
        },
    )
