# 05 Betrieb (Phase 4)

Entwurf – wird vor Beginn von Phase 4 verfeinert und erneut freigegeben.

## D-1 Datenschutz-Funktionen

- Auskunft (Art. 15 DSGVO): alle Daten zu einer Person als PDF und JSON exportieren.
- Berichtigung: normale Bearbeitung, protokolliert.
- Löschung (Art. 17 DSGVO): Ein Kontakt ohne Belege wird gelöscht. Mit Belegen wird er bis zum Ende der Aufbewahrungsfrist gesperrt (Art. 17 Abs. 3 lit. b, Art. 18 DSGVO): nicht mehr in Listen und Suche, nur für Inhaber einsehbar.
- Aufbewahrungsfristen: Rechnungen und andere Buchungsbelege 8 Jahre, Handels- und Geschäftsbriefe 6 Jahre (§ 147 AO, § 14b UStG), jeweils ab Ende des Kalenderjahres. Einmal im Jahr schlägt das Programm abgelaufene Daten zur Löschung vor, der Inhaber bestätigt.
- Datenübertragbarkeit (Art. 20 DSGVO) und Komplettexport aller Daten in offenen Formaten.

## D-2 Datensicherung

- Sicherung per Klick und automatisch täglich; die Zahl der aufbewahrten Sicherungen ist einstellbar.
- Sicherungen sind mit einem Kennwort verschlüsselt. Das Programm sagt deutlich, dass ohne dieses Kennwort keine Wiederherstellung möglich ist.
- Wiederherstellung mit Vorschau (Datum, Umfang); der aktuelle Stand wird vorher gesichert.
- Vor jedem Update entsteht automatisch eine Sicherung.
- Belege müssen 8 Jahre verfügbar bleiben. Deshalb fragt die Einrichtung nach einem zweiten Sicherungsziel an einem anderen Ort (NAS, USB-Platte, verschlüsselter Speicher in der EU), und das Programm warnt, wenn die letzte erfolgreiche Sicherung älter als 7 Tage ist.

## D-3 Installation

- Einzelplatz: Installationspaket für Windows, macOS und Linux. Startet lokal und öffnet den Browser. Datenbank SQLite.
- Netzwerk oder Server: Docker-Image mit PostgreSQL (Docker Compose), z. B. auf einem NAS. HTTPS über einen Reverse Proxy.
- Updates migrieren die Datenbank automatisch, mit Sicherung davor.

## D-4 Gehostete Version

- Eine eigene Instanz je Kunde, mit getrennter Datenbank und Dateiablage.
- Rechenzentren in Deutschland, AVV nach Art. 28 DSGVO, öffentliche Liste der Unterauftragsverarbeiter.
- Verschlüsselte, getrennt gelagerte Sicherungen.

## D-5 Vorlagen für Anwender

- Verfahrensdokumentation nach GoBD, der Teil zum Programm bereits ausgefüllt.
- Verzeichnis von Verarbeitungstätigkeiten (Art. 30 DSGVO) und technische und organisatorische Maßnahmen (Art. 32 DSGVO) als Vorlage.

## D-6 Betriebsprüfung und Programmwechsel

- Datenzugriff der Finanzverwaltung (§ 147 Abs. 6 AO):
  - Unmittelbarer Zugriff: Rolle **Prüfer** mit zeitlich begrenztem Nur-Lese-Zugriff auf Belege, Zahlungen, Auswertungen und Protokoll.
  - Datenträgerüberlassung: Export eines Zeitraums als CSV mit Beschreibungsdatei `index.xml` nach dem Beschreibungsstandard der Finanzverwaltung, dazu alle Beleg-PDFs und -XMLs.
- Archivexport: alle Belege und Daten in Formaten, die ohne das Programm lesbar bleiben (PDF/A, XML, CSV). So bleibt die Aufbewahrung auch nach einem Programmwechsel gesichert.

## D-7 Neue Versionen

- Kontorfreund sucht nur nach neuen Versionen, wenn der Inhaber zugestimmt hat (Grundsatz: keine Verbindungen zu Dritten, die der Nutzer nicht selbst einrichtet). Die Übersicht fragt ihn einmal danach. Unter Einstellungen › Updates lässt sich die Suche jederzeit ein- und ausschalten.
- Ist sie eingeschaltet, fragt Kontorfreund höchstens einmal am Tag bei GitHub nach der neuesten Version; dort liegen die Installationspakete. GitHub sieht dabei die IP-Adresse. Kontorfreund überträgt weder seine Version noch eine Kennung oder Daten.
- „Jetzt nach Updates suchen“ geht jederzeit, auch bei ausgeschalteter Suche, unter Einstellungen › Updates und als „Nach Updates suchen“ auf der Übersicht.
- Gibt es eine neuere Version, zeigt die Übersicht dem Inhaber einen Hinweis, und in der Kopfleiste jeder Seite steht „Update“ mit der neuen Versionsnummer als Link zu Einstellungen › Updates. Unter Einstellungen › Updates stehen die installierte Version, die Neuerungen aus dem Änderungsprotokoll und der Download des passenden Pakets (Windows-Installation, portable Fassung, macOS, Linux). Ohne passendes Paket, etwa aus dem Quellcode, verlinkt die Seite das Release.
- Kontorfreund lädt und installiert nichts von selbst. Installiert wird wie bisher von Hand (D-3); die Sicherung vor der Migration bleibt (D-2).
- Ohne Internet oder bei einem Fehler arbeitet das Programm normal weiter, die Seite Updates nennt den Fehler.

## Abnahme Phase 4

- Neuinstallation und Wiederherstellung einer Sicherung gelingen auf frischen Systemen mit Windows, macOS und Linux.
- Ein Prüfer-Konto kann nichts ändern.
- Die `index.xml` des Prüfer-Exports ist gültig nach der DTD des Beschreibungsstandards.
- Der Auskunftsexport enthält alle Daten einer Testperson.
- Die Checkliste nach OWASP ASVS Level 2 ist vollständig abgearbeitet.
