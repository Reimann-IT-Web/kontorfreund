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
- `core/` – Übersicht, Einstellungen mit `Firmendaten` (genau ein Datensatz, `Firmendaten.laden()`), Seitenleiste (`core/navigation.py`), Kontextprozessoren (Navigation, Suchindex für Strg+K, Firmendaten auf jeder Seite), Template-Tags `kf` (`{% icon %}`, `|euro`, `|zahl`, `|relativ`) und der Formularfeld-Baustein `core/feld.html`.
- `contacts/` – Adressen (`Kontakt`: Firma oder Person, Nummer K-0001 fortlaufend, Dublettenprüfung, Archiv statt Löschen).
- `invoicing/` – Rechnungen: Entwurf (frei änderbar) → Festschreiben (`beleg.festschreiben`): vergibt die Nummer (`Rechnung.naechste_nummer`, Jahr zweistellig + vierstelliger Zähler, lückenlos nach den Altbelegen), friert alle Angaben in `Rechnung.beleg` (JSON) ein und legt das PDF unter `<DATA_DIR>/archiv/rechnungen/<jahr>/` ab. PDF/A-3 per Typst (`invoicing/typst/rechnung.typ`, Schriften aus `invoicing/schrift/`, Systemschriften ignoriert), ZUGFeRD-XML (EN 16931) mit drafthorse, GiroCode mit segno, Logo aus `Firmendaten.logo` (Bytes in der DB, nicht eingefroren – das abgelegte PDF ist maßgeblich). Vorschau und Ansicht zeigen die PDF-Seiten als PNG (pypdfium2, `beleg.seitenbilder`), nie per iframe: der PDF-Betrachter mancher Browser bleibt dort schwarz. Danach sperren `save()`/`delete()` jede Änderung außer den Versandfeldern. Korrektur nur per Stornorechnung (`beleg.stornieren`): eine eigene, sofort festgeschriebene Rechnung mit `storno_zu` aufs Original, negativen Mengen (EN 16931 verbietet negative Einzelpreise) und BT-25/26 im XML; „storniert“ wird aus dieser Verknüpfung abgeleitet, das Original bleibt unberührt. `Rechnung.kopieren()` legt einen neuen Entwurf mit denselben Angaben an. Versand per SMTP mit den Zugangsdaten aus `Firmendaten` (`versand.py`). Live-Rechnen und Pflichtangaben-Anzeige laufen zusätzlich in `static/js/app.js`; maßgeblich ist die Prüfung auf dem Server (`Rechnung.fehlende_angaben`).
- `archive/` – Ablage der aus dem Altprogramm übernommenen Belege (`Altbeleg`, Original-PDFs unverändert unter `<DATA_DIR>/archiv/altbelege/`). Übernahme nur aus den vom Altprogramm erzeugten PDFs, nie aus dessen Datenbank: `uv run python manage.py altdaten_importieren <ordner>` zeigt einen Probelauf, `--ausfuehren` übernimmt. Bereits übernommene Dateien (gleiche SHA-256) werden übersprungen. Adressen werden über Kundennummer und Namen zugeordnet: Das Altprogramm hat Kunden teils neu nummeriert, gleicher Name ergibt deshalb eine Adresse mit der jüngsten Nummer.
- Jeder weitere Fachbereich bekommt eine eigene App (z. B. `payments`, `exports`).
- Oberfläche: Django-Templates (`templates/base.html` + App-Templates, Django-6-Partials), eigenes CSS in `static/css/app.css` mit Design-Tokens, kein JS-Framework. Gestaltungsregeln: `PRODUCT.md`, `.impeccable/surfaces/`.

## Regeln

- Clean Room: keinen Code, keine Texte, Screenshots, Vorlagen oder Datenbankstrukturen aus anderer Software übernehmen. Installationen, Programmdateien und Datenbanken anderer CRM- oder Rechnungsprogramme auf diesem Rechner weder öffnen noch analysieren.
- Nicht an Microsoft gebunden: keine Windows-only-Abhängigkeiten, kein Office, Access oder Outlook. Bibliotheken müssen per `uv sync` auf allen drei Systemen ohne Systempakete laufen. Deshalb PDFs mit Typst, nicht WeasyPrint (braucht Pango).
- Datenschutz: keine Telemetrie, keine externen CDNs, Schriften oder Skripte – alles wird selbst ausgeliefert.
- Keine Beispieldaten in App oder Datenbank; alle Inhalte gibt der Nutzer selbst ein. Testdaten nur in Tests oder in einer Wegwerf-Datenbank (`APP_DATA_DIR` auf einen Temp-Ordner).
- Geldbeträge immer `Decimal`, nie `float`.
- Festgeschriebene Belege sind unveränderbar (GoBD); Korrektur nur per Stornorechnung.
- Oberflächentexte auf Deutsch, Anrede „Sie“.
- Neue Abhängigkeiten nur mit AGPL-3.0-verträglicher Lizenz.
