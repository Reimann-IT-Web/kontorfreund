# Kontorfreund (Kleinunternehmen)

Open-Source-CRM und Rechnungsprogramm für Kleinunternehmer und kleine Büros in Deutschland: Kontakte, Wiedervorlagen, Angebote und Rechnungen mit E-Rechnung (XRechnung, ZUGFeRD), offene Posten, Mahnwesen und DATEV-Export.

- Bedienung im Browser – läuft auf Linux, macOS und Windows, ohne Microsoft Office
- Ihre Daten bleiben bei Ihnen: keine Werbung, kein Tracking, keine externen Dienste
- Datenschutz (DSGVO) und GoBD von Anfang an eingebaut

**Status:** frühe Entwicklung, Version 0.1.0. Im Einsatz sind Adressen, Artikel, Angebote und Rechnungen mit ZUGFeRD und XRechnung, Stornorechnung und Rechnungskorrektur, offene Posten mit Zahlungen und Mahnungen samt Verzugszinsen, Eingangsrechnungen, die Ablage übernommener Altbelege, Anmeldung und verschlüsselte Datensicherung. Was sich geändert hat, steht in [CHANGELOG.md](CHANGELOG.md), was noch entsteht, in der [Spezifikation](docs/spec/README.md).

## Installation

Die Pakete hängen am jeweiligen [Release](../../releases).

- **Windows:** `Kontorfreund-Setup-<Version>.exe` ausführen. Es braucht keine Administratorrechte. Weil das Programm noch nicht signiert ist, warnt Windows beim ersten Mal („Der Computer wurde durch Windows geschützt“): „Weitere Informationen“ und dann „Trotzdem ausführen“ wählen.
- **macOS und Linux:** Archiv entpacken und `Kontorfreund/Kontorfreund` starten.

Kontorfreund öffnet sich im Browser unter http://127.0.0.1:8765/. Das kleine Fenster dazu bleibt offen, solange Sie arbeiten; schließen beendet das Programm. Ihre Daten liegen getrennt vom Programm:

| System | Ordner |
|---|---|
| Windows | `%LOCALAPPDATA%\Kontorfreund` |
| macOS | `~/Library/Application Support/Kontorfreund` |
| Linux | `~/.local/share/Kontorfreund` bzw. `$XDG_DATA_HOME/Kontorfreund` |

Für ein Update installieren Sie die neue Version einfach darüber. Die Datenbank wird beim nächsten Start angepasst, vorher entsteht eine Sicherung. Beim Deinstallieren bleiben die Daten erhalten.

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

Installationspaket bauen (auf dem jeweiligen System):

```sh
uv sync --group paket
uv run pyinstaller packaging/kontorfreund.spec --noconfirm
dist/Kontorfreund/Kontorfreund selbsttest
```

Ein Tag `v<Version>` baut über `.github/workflows/paket.yml` die Pakete für alle drei Systeme und legt das Release an.

## Lizenz

[AGPL-3.0-only](LICENSE). Eine kommerzielle Lizenz ohne AGPL-Pflichten ist geplant.

Sicherheitslücken bitte vertraulich melden, siehe [SECURITY.md](SECURITY.md).
