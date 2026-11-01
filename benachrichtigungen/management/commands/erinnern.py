"""Fällige Benachrichtigungen senden; das Startprogramm ruft das alle fünf Minuten auf.

Kontorfreund erinnern
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from benachrichtigungen.nachrichten import erinnern


class Command(BaseCommand):
    help = "Sendet fällige Benachrichtigungen über Telegram."

    def handle(self, **optionen):
        # Eine Firma, die nach einem Update noch nicht offen war, ist noch nicht auf dem
        # neuesten Stand; das holt der Start nach, mit Sicherung vorher.
        stand = MigrationExecutor(connection)
        if not stand.migration_plan(stand.loader.graph.leaf_nodes()):
            erinnern()
