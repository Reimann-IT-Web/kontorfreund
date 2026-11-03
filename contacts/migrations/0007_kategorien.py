"""Kategorien frei anlegen, mehrere je Adresse (Spezifikation K-1).

Kunde, Interessent und Lieferant werden Kategorien mit Kennung; jede Adresse
behält ihre bisherige.
"""

from django.db import migrations, models

VORGABEN = [
    ("kunde", "Kunde"),
    ("interessent", "Interessent"),
    ("lieferant", "Lieferant"),
]


def umstellen(apps, schema_editor):
    Kategorie = apps.get_model("contacts", "Kategorie")
    Kontakt = apps.get_model("contacts", "Kontakt")
    neu = {
        kennung: Kategorie.objects.create(kennung=kennung, name=name)
        for kennung, name in VORGABEN
    }
    Zuordnung = Kontakt.kategorien.through
    Zuordnung.objects.bulk_create(
        Zuordnung(kontakt_id=pk, kategorie_id=neu[alt].pk)
        for pk, alt in Kontakt.objects.values_list("pk", "kategorie")
        if alt in neu
    )


def zurueck(apps, schema_editor):
    """Die erste vorgegebene Kategorie der Adresse, sonst Kunde."""
    Kontakt = apps.get_model("contacts", "Kontakt")
    for kontakt in Kontakt.objects.prefetch_related("kategorien"):
        kennungen = [k.kennung for k in kontakt.kategorien.all() if k.kennung]
        kontakt.kategorie = kennungen[0] if kennungen else "kunde"
        kontakt.save(update_fields=["kategorie"])


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0006_kontaktwege_position"),
    ]

    operations = [
        migrations.CreateModel(
            name="Kategorie",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=50, unique=True, verbose_name="Name"),
                ),
                (
                    "kennung",
                    models.CharField(
                        choices=[
                            ("kunde", "Kunde"),
                            ("interessent", "Interessent"),
                            ("lieferant", "Lieferant"),
                        ],
                        blank=True,
                        editable=False,
                        max_length=12,
                    ),
                ),
            ],
            options={
                "verbose_name": "Kategorie",
                "verbose_name_plural": "Kategorien",
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("kennung", ""), _negated=True),
                        fields=("kennung",),
                        name="kategorie_kennung_eindeutig",
                    )
                ],
            },
        ),
        migrations.AddField(
            model_name="kontakt",
            name="kategorien",
            field=models.ManyToManyField(
                blank=True,
                related_name="kontakte",
                to="contacts.kategorie",
                verbose_name="Kategorien",
            ),
        ),
        migrations.RunPython(umstellen, zurueck),
        migrations.RemoveField(
            model_name="kontakt",
            name="kategorie",
        ),
    ]
