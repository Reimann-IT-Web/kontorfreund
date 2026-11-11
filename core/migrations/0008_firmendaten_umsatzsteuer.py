"""Kleinunternehmer ja/nein wird zur Auswahl der Umsatzsteuer (Spezifikation B-4).

Wer Kleinunternehmer angekreuzt hatte, steht danach auf „Kleinunternehmer“,
alle anderen auf „Umsatzsteuer ausweisen“. Zurück geht es ebenso; „steuerfrei“
wird dabei zu „kein Kleinunternehmer“.
"""

from django.db import migrations, models


def vorwaerts(apps, schema_editor):
    Firmendaten = apps.get_model("core", "Firmendaten")
    Firmendaten.objects.filter(kleinunternehmer=False).update(umsatzsteuer="regel")


def rueckwaerts(apps, schema_editor):
    Firmendaten = apps.get_model("core", "Firmendaten")
    Firmendaten.objects.exclude(umsatzsteuer="kleinunternehmer").update(
        kleinunternehmer=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_firmendaten_zahlungstext"),
    ]

    operations = [
        migrations.AddField(
            model_name="firmendaten",
            name="umsatzsteuer",
            field=models.CharField(
                choices=[
                    ("kleinunternehmer", "Kleinunternehmer nach § 19 UStG"),
                    ("regel", "Umsatzsteuer ausweisen (19 %)"),
                    ("steuerfrei", "Steuerfreie Leistungen nach § 4 UStG"),
                ],
                default="kleinunternehmer",
                max_length=20,
                verbose_name="Umsatzsteuer",
            ),
        ),
        migrations.AddField(
            model_name="firmendaten",
            name="steuerfrei_hinweis",
            field=models.CharField(
                blank=True,
                max_length=200,
                verbose_name="Hinweis auf die Steuerbefreiung",
            ),
        ),
        migrations.RunPython(vorwaerts, rueckwaerts),
        migrations.RemoveField(
            model_name="firmendaten",
            name="kleinunternehmer",
        ),
    ]
