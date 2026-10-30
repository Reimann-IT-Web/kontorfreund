"""Amtliche Basiszinssätze nach § 247 BGB seit 2023 (Deutsche Bundesbank).

Spätere Sätze trägt der Inhaber in den Einstellungen zum Mahnwesen ein.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

SAETZE = [
    (date(2023, 1, 1), "1.62"),
    (date(2023, 7, 1), "3.12"),
    (date(2024, 1, 1), "3.62"),
    (date(2024, 7, 1), "3.37"),
    (date(2025, 1, 1), "2.27"),
    (date(2025, 7, 1), "1.27"),
    (date(2026, 1, 1), "1.27"),
    (date(2026, 7, 1), "1.52"),
]


def eintragen(apps, schema_editor):
    Basiszins = apps.get_model("zahlungen", "Basiszins")
    for tag, satz in SAETZE:
        Basiszins.objects.get_or_create(gueltig_ab=tag, defaults={"satz": Decimal(satz)})


def entfernen(apps, schema_editor):
    Basiszins = apps.get_model("zahlungen", "Basiszins")
    Basiszins.objects.filter(gueltig_ab__in=[tag for tag, _ in SAETZE]).delete()


class Migration(migrations.Migration):
    dependencies = [("zahlungen", "0001_zahlungen")]

    operations = [migrations.RunPython(eintragen, entfernen)]
