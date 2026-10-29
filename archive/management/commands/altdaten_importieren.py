from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from archive.importer import pruefen, uebernehmen
from core.templatetags.kf import euro


class Command(BaseCommand):
    help = (
        "Übernimmt Rechnungen, Stornos, Gutschriften und Angebote aus den PDF-Dateien "
        "des Altprogramms. Ohne --ausfuehren nur Probelauf mit Bericht."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "ordner", help="Ordner des Altprogramms, z. B. C:\\SUCCESSCONTROL"
        )
        parser.add_argument(
            "--ausfuehren", action="store_true", help="Belege wirklich übernehmen."
        )

    def handle(self, ordner, ausfuehren, **optionen):
        if not Path(ordner).is_dir():
            raise CommandError(f"Ordner nicht gefunden: {ordner}")
        bericht = pruefen(ordner)
        if ausfuehren:
            uebernehmen(bericht)

        aus = self.stdout.write
        aus(
            "ÜBERNAHME AUSGEFÜHRT"
            if ausfuehren
            else "PROBELAUF – es wurde nichts gespeichert"
        )
        aus("")
        aus("Übernehmbare Belege:")
        for (absender, art), anzahl in sorted(bericht.anzahl_je_art().items()):
            aus(f"  {absender or '(ohne Absender)'}: {anzahl} × {art}")
        aus("")
        aus("Umsatz je Jahr (Rechnungen abzüglich Stornos und Gutschriften):")
        for jahr, summe in bericht.umsatz_je_jahr().items():
            aus(f"  {jahr}: {euro(summe)}")
        aus("")
        if bericht.bereits_uebernommen:
            aus(f"Bereits übernommen (übersprungen): {bericht.bereits_uebernommen}")
        for grund, anzahl in sorted(bericht.uebersprungen.items()):
            aus(f"Nicht übernommen – {grund}: {anzahl}")
        if bericht.doppelt:
            aus(
                f"Neuausdrucke (gleiche Nummer, gleiches Datum, gleicher Betrag): "
                f"{len(bericht.doppelt)}"
            )
        if bericht.abweichend:
            aus(
                f"Gleiche Nummer in zwei Fassungen – übernommen wurde die jüngere, "
                f"bitte prüfen: {len(bericht.abweichend)}"
            )
            for aeltere, juengere in bericht.abweichend:
                aus(f"  {aeltere}  ↔  {juengere}")
        if bericht.unlesbar:
            aus(f"Nicht lesbar: {len(bericht.unlesbar)}")
            for name, grund in bericht.unlesbar:
                aus(f"  {name}: {grund}")
        if bericht.anschrift_unsicher:
            aus(f"Anschrift bitte prüfen: {len(bericht.anschrift_unsicher)} Belege")
            for name in bericht.anschrift_unsicher:
                aus(f"  {name}")
        if ausfuehren:
            aus("")
            aus(
                f"Adressen: {bericht.neue_kontakte} neu angelegt, "
                f"{bericht.vorhandene_kontakte} vorhandene zugeordnet."
            )
            if bericht.zusammengefuehrt:
                aus(
                    "Gleicher Name unter mehreren Kundennummern – zu einer Adresse "
                    "zusammengeführt, die jüngste Nummer gilt:"
                )
                for name, nummern in bericht.zusammengefuehrt:
                    aus(f"  {name}: {', '.join(map(str, nummern))}")
