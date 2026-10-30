# Kontorfreund (Kleinunternehmen)

Open-Source-CRM und Rechnungsprogramm für Kleinunternehmer und kleine Büros in Deutschland: Kontakte, Wiedervorlagen, Angebote und Rechnungen mit E-Rechnung (XRechnung, ZUGFeRD), offene Posten, Mahnwesen und DATEV-Export.

- Bedienung im Browser – läuft auf Linux, macOS und Windows, ohne Microsoft Office
- Ihre Daten bleiben bei Ihnen: keine Werbung, kein Tracking, keine externen Dienste
- Datenschutz (DSGVO) und GoBD von Anfang an eingebaut

**Status:** frühe Entwicklung. Im Einsatz sind Adressen, Artikel, Angebote und Rechnungen mit ZUGFeRD und XRechnung, Stornorechnung und Rechnungskorrektur, die Ablage übernommener Altbelege, Anmeldung und verschlüsselte Datensicherung. Was noch entsteht, beschreibt die [Spezifikation](docs/spec/README.md).

## Entwicklung

Voraussetzung: [uv](https://docs.astral.sh/uv/). Python 3.12 lädt uv bei Bedarf selbst.

```sh
uv sync
uv run python manage.py migrate
APP_DEBUG=1 uv run python manage.py runserver
```

Danach läuft das Programm unter http://localhost:8000.

```sh
uv run pytest                     # Tests
uv run ruff check . && uv run ruff format .
```

## Lizenz

[AGPL-3.0-only](LICENSE). Eine kommerzielle Lizenz ohne AGPL-Pflichten ist geplant.

Sicherheitslücken bitte vertraulich melden, siehe [SECURITY.md](SECURITY.md).
