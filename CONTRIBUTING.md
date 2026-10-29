# Mitwirken

Fehlerberichte und Vorschläge sind als Issue willkommen.

## Code-Beiträge

Code von außen nehmen wir erst an, wenn die Contributor License Agreement (CLA) steht. Sie erlaubt, das Projekt neben der AGPL auch unter einer kommerziellen Lizenz anzubieten. Bis dahin bitte keine Pull Requests mit Code.

## Grundregeln

- Keine Inhalte aus anderer Software: kein Code, keine Texte, Screenshots, Vorlagen oder Datenbankstrukturen.
- Funktionen richten sich nach der Spezifikation in [`docs/spec/`](docs/spec/README.md).
- Commit-Nachrichten nach [Conventional Commits](https://www.conventionalcommits.org/de/), z. B. `feat(kontakte): Dublettenprüfung`.
- Die CI muss grün sein: Tests auf Linux, macOS und Windows, Ruff, Migrationsprüfung, Sicherheitsprüfung der Abhängigkeiten.
