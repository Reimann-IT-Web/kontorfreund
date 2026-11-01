"""Fällige Benachrichtigungen senden; das Startprogramm ruft das alle fünf Minuten auf.

Kontorfreund erinnern

Vorher die tägliche Prüfung der Ablage, wenn sie fällig ist: So läuft sie auch, wenn
Kontorfreund nur im Hintergrund läuft und niemand eine Seite öffnet.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from archive import pruefung
from benachrichtigungen.nachrichten import erinnern


class Command(BaseCommand):
    help = "Prüft die Ablage, wenn es heute noch nicht geschehen ist, und sendet fällige Benachrichtigungen über Telegram."

    def handle(self, **optionen):
        # Eine Firma, die nach einem Update noch nicht offen war, ist noch nicht auf dem
        # neuesten Stand; das holt der Start nach, mit Sicherung vorher.
        stand = MigrationExecutor(connection)
        if not stand.migration_plan(stand.loader.graph.leaf_nodes()):
            if pruefung.faellig():
                pruefung.pruefen()
            erinnern()
