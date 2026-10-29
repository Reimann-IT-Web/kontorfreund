# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

Open-Source-CRM und Rechnungsprogramm für Kleinunternehmer in Deutschland. Django-Web-App, Bedienung im Browser, läuft auf Linux, macOS und Windows. Lizenz AGPL-3.0-only (Dual Licensing geplant).

Was gebaut wird, steht ausschließlich in `docs/spec/` (Clean-Room-Spezifikation, nach Phasen gegliedert). Neue Funktionen nur, wenn sie dort beschrieben und freigegeben sind.

Produkt: „Kontorfreund (Kleinunternehmen)“ – Marke `settings.PRODUCT_NAME` („Kontorfreund“, Markenprüfung beim DPMA steht noch aus) plus Edition `settings.PRODUCT_EDITION` („Kleinunternehmen“). Weitere Editionen sollen später auf derselben Codebasis entstehen, nicht als Kopie. Name und Edition im Code nie hart codieren; Templates nutzen `product_name` aus `core.context_processors`.

## Befehle

```sh
uv sync
uv run python manage.py migrate
APP_DEBUG=1 uv run python manage.py runserver
uv run pytest
uv run pytest tests/test_start.py::test_startseite        # einzelner Test
uv run ruff check . && uv run ruff format --check .
uv run python manage.py makemigrations --check --dry-run
```

Die CI (`.github/workflows/ci.yml`) führt genau diese Prüfungen aus, Tests auf allen drei Betriebssystemen, plus `pip-audit`.

## Architektur

- `config/` – Django-Projekt. Betriebswerte über Umgebungsvariablen `APP_*` (`APP_DEBUG`, `APP_SECRET_KEY`, `APP_ALLOWED_HOSTS`, `APP_DATA_DIR`).
- Datenverzeichnis (`APP_DATA_DIR`, Standard `./data`, nicht im Repo): SQLite-Datenbank, Dateiablage und der beim ersten Start erzeugte `secret_key`. Ohne Umgebungsvariablen läuft das Programm als Einzelplatz-Installation.
- `core/` – Startseite und Gemeinsames. Jeder Fachbereich bekommt eine eigene App (z. B. `contacts`, `invoicing`, `payments`, `exports`).
- Oberfläche: Django-Templates (`templates/base.html` + App-Templates), HTMX statt JS-Framework.

## Regeln

- Clean Room: keinen Code, keine Texte, Screenshots, Vorlagen oder Datenbankstrukturen aus anderer Software übernehmen. Installationen, Programmdateien und Datenbanken anderer CRM- oder Rechnungsprogramme auf diesem Rechner weder öffnen noch analysieren.
- Nicht an Microsoft gebunden: keine Windows-only-Abhängigkeiten, kein Office, Access oder Outlook. Bibliotheken müssen per `uv sync` auf allen drei Systemen ohne Systempakete laufen. Deshalb PDFs mit Typst, nicht WeasyPrint (braucht Pango).
- Datenschutz: keine Telemetrie, keine externen CDNs, Schriften oder Skripte – alles wird selbst ausgeliefert.
- Geldbeträge immer `Decimal`, nie `float`.
- Festgeschriebene Belege sind unveränderbar (GoBD); Korrektur nur per Stornorechnung.
- Oberflächentexte auf Deutsch, Anrede „Sie“.
- Neue Abhängigkeiten nur mit AGPL-3.0-verträglicher Lizenz.
