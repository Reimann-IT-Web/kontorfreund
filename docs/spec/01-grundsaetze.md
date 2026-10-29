# 01 Grundsätze

Gilt für alle Phasen. Ziel: spürbar einfacher zu bedienen und schöner als klassische Desktop-Bürosoftware – und unabhängig von Microsoft.

## Bedienung

| Nr. | Grundsatz | Abnahme |
|---|---|---|
| G-1 | Häufige Aufgaben brauchen wenige Schritte. | Vom Kontakt zum Rechnungsentwurf höchstens 3 Klicks. Beim neuen Kontakt ist nur der Name Pflicht. |
| G-2 | Eine Suche für alles: Kontakte, Belege, Artikel, Wiedervorlagen. | Öffnet mit Strg+K bzw. ⌘K und zeigt Treffer schon beim Tippen. |
| G-3 | Die Startseite ist eine Arbeitsliste, kein Menü. | Zeigt fällige Wiedervorlagen, überfällige Rechnungen und offene Angebote. |
| G-4 | Vollständig per Tastatur bedienbar. | Jede Funktion ohne Maus erreichbar, Fokus immer sichtbar. |
| G-5 | Nichts geht verloren. | Entwürfe speichern automatisch. Statt „Wirklich löschen?“ gibt es „Rückgängig“. Endgültige Schritte (Rechnung festschreiben, Daten endgültig löschen) erklären vorher genau, was passiert. |
| G-6 | Status auf einen Blick. | Belege zeigen ihren Status als Text und Farbe: Entwurf, Versendet, Bezahlt, Überfällig, Storniert. |
| G-7 | Leere Listen zeigen den nächsten Schritt. | Jede leere Liste hat einen erklärenden Satz und eine passende Schaltfläche, z. B. „Kontakt anlegen“ oder „Importieren“. |
| G-8 | Fehlermeldungen helfen weiter. | Die Meldung steht am betroffenen Feld und sagt, was zu tun ist. Keine Fehlercodes ohne Erklärung. |
| G-9 | Verständliche Sprache. | Deutsch, Anrede „Sie“. Fachbegriffe nur wo nötig und dann kurz erklärt. |
| G-10 | Passt sich dem Gerät an. | Volle Funktion ab 1280 px Breite, auf dem Tablet bedienbar. Auf dem Handy: suchen, ansehen, Notizen und Wiedervorlagen erfassen. |
| G-11 | Barrierefrei. | WCAG 2.2, Stufe AA. |
| G-12 | Schnell. | Listen und Suche antworten bei 10.000 Kontakten in unter 1 Sekunde. |

## Gestaltung

- Ruhige, helle Oberfläche mit viel Weißraum, einer Akzentfarbe und klarer Typografie; dazu ein Dunkelmodus.
- Einheitliche Bausteine (Schaltflächen, Formulare, Tabellen, Statusmarken) auf Basis von Design-Tokens für Farben, Abstände und Schrift.
- Schriften und Symbole werden mit dem Programm ausgeliefert und nicht von Google Fonts o. Ä. geladen (DSGVO; LG München I, 20.01.2022, 3 O 17493/20).
- Belege (PDF): eigenes Briefpapier mit Logo, Akzentfarbe und Fußzeile; Anschriftfeld nach DIN 5008 für Fensterumschläge.
- Zu Beginn von Phase 1 wird die Gestaltung als klickbarer Prototyp (Startseite, Kontaktliste, Rechnung) vorgelegt und erst nach Freigabe umgesetzt.

## Plattform – ohne Microsoft

- Bedienung im Browser: aktuelle Versionen von Firefox, Chrome, Safari und Edge.
- Läuft auf Linux, macOS und Windows, als Server auch auf einem NAS oder im Rechenzentrum.
- Keine Abhängigkeit von Microsoft Office, Access, Outlook oder Windows.
- Austausch über offene Formate: PDF/A, CSV, XLSX und ODS, vCard, iCalendar. E-Mail über SMTP und IMAP, Kalender- und Adressabgleich über CalDAV/CardDAV (ab v1.x).
- Nur Bibliotheken, die auf allen drei Systemen ohne Zusatzinstallation laufen.

## Datenschutz und Sicherheit

- Die Daten bleiben dort, wo das Programm installiert ist. Keine Telemetrie, keine Werbung, keine Verbindungen zu Dritten, die der Nutzer nicht selbst einrichtet (z. B. den eigenen Mailserver).
- Datenschutz durch Voreinstellung (Art. 25 DSGVO): nur nötige Pflichtfelder, sparsame Standardrechte.
- Sicherheitsniveau OWASP ASVS Level 2. Die konkreten Prüfungen stehen in den Abnahmekriterien der Phasen.
