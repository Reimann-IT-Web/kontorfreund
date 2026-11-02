"""Format des Fehlerprotokolls; ohne Modelle, weil Django es vor den Apps lädt."""

import logging
from datetime import datetime


class MitZeitzone(logging.Formatter):
    """Zeitpunkt mit Abstand zu UTC, z. B. 2026-11-02T03:04:05+01:00 (ASVS 16.2.2)."""

    def formatTime(self, record, datefmt=None):
        return (
            datetime.fromtimestamp(record.created)
            .astimezone()
            .isoformat(timespec="seconds")
        )
