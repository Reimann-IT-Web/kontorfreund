"""Die Kategorie für Adressen ohne eigene ist jetzt eine der Kategorien (K-1)."""

import django.db.models.deletion
from django.db import migrations, models


def umstellen(apps, schema_editor):
    Kategorie = apps.get_model("contacts", "Kategorie")
    Import = apps.get_model("importe", "Import")
    for kategorie in Kategorie.objects.exclude(kennung=""):
        Import.objects.filter(kategorie=kategorie.kennung).update(
            vorgabe=kategorie
        )


def zurueck(apps, schema_editor):
    Import = apps.get_model("importe", "Import")
    for imp in Import.objects.select_related("vorgabe"):
        imp.kategorie = getattr(imp.vorgabe, "kennung", None) or "kunde"
        imp.save(update_fields=["kategorie"])


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0007_kategorien"),
        ("importe", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="import",
            name="vorgabe",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="contacts.kategorie",
            ),
        ),
        migrations.RunPython(umstellen, zurueck),
        migrations.RemoveField(
            model_name="import",
            name="kategorie",
        ),
        migrations.RenameField(
            model_name="import",
            old_name="vorgabe",
            new_name="kategorie",
        ),
    ]
