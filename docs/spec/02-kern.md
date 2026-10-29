# 02 Kern (Phase 1)

## K-1 Kontakte

Ein Kontakt ist eine **Firma** oder eine **Person**. Personen können einer Firma als Ansprechpartner zugeordnet sein.

Felder:

- Firma: Firmenname, Namenszusatz. Person: Anrede, Titel, Vorname, Nachname, Position.
- Anschriften: mehrere, jeweils mit Art (Rechnung, Lieferung, Sonstige); eine ist Standard.
- E-Mail-Adressen und Telefonnummern: mehrere, jeweils mit Bezeichnung.
- Website, USt-IdNr.
- Kundennummer: automatisch aus einem Nummernkreis, änderbar, solange es keinen Beleg gibt.
- Kategorien: frei definierbar, mehrere je Kontakt (z. B. Kunde, Lieferant, Interessent).
- Notiz (Freitext).

Regeln:

- Pflicht ist nur der Name (Firmenname bzw. Nachname).
- Beim Anlegen warnt das Programm vor möglichen Dubletten (gleiche E-Mail-Adresse, ähnlicher Name am selben Ort) und bietet an, den vorhandenen Kontakt zu öffnen.
- Die USt-IdNr. wird auf gültiges Format geprüft.
- Kontakte mit Belegen werden archiviert statt gelöscht. Zur Löschung personenbezogener Daten siehe [05-betrieb.md](05-betrieb.md).

Abnahme:

- Kontakt nur mit Namen anlegen und später ergänzen.
- Liste nach Kategorie und Ort filtern, sortieren, Spalten wählen.
- Bei gleicher E-Mail-Adresse erscheint die Dublettenwarnung.
- Ansprechpartner erscheinen bei ihrer Firma, die Firma erscheint bei der Person.

## K-2 Kontakthistorie

Eine Zeitleiste je Kontakt mit allen Vorgängen.

- Eintragsarten: Notiz, Anruf, E-Mail, Termin, Dokument. Ab Phase 2 erscheinen Belege, ab Phase 3 Zahlungen und Mahnungen automatisch.
- Jeder Eintrag hat Datum und Uhrzeit, Art, Betreff, Text und Benutzer, optional eine Datei.
- Bei einer Firma erscheinen auch die Einträge ihrer Ansprechpartner (abschaltbar).
- Aus jedem Eintrag lässt sich mit einem Klick eine Wiedervorlage anlegen, z. B. „Nachfassen in 1 Woche“.

Abnahme:

- Ein Anruf mit Notiz ist per Schnellerfassung im Kontakt in unter 10 Sekunden erfasst.
- Die Zeitleiste lässt sich nach Art filtern.

## K-3 Dateiablage

- Dateien per Ziehen und Ablegen an einen Kontakt oder Historieneintrag hängen, auch mehrere auf einmal.
- Vorschau im Browser nur für PDF und Bilder, alle anderen Dateien nur als Download.
- Gespeichert im Datenverzeichnis des Programms.
- Dateinamen werden bereinigt, die Größe ist begrenzt (Standard 50 MB, einstellbar).

Abnahme:

- Hochladen, Vorschau, Herunterladen und Löschen (mit Rückgängig) funktionieren.
- Eine hochgeladene HTML-Datei wird nie im Browser ausgeführt.

## K-4 Wiedervorlagen

- Felder: Titel, fällig am (Datum, optional Uhrzeit), zuständiger Benutzer, Bezug (Kontakt; ab Phase 2 auch Beleg), Notiz, Status offen oder erledigt.
- Auf der Startseite: Überfällig, Heute, Demnächst.
- Schnell verschieben: morgen, nächste Woche, nächster Monat, Wunschdatum.
- Erledigen mit optionaler Notiz; der Vorgang erscheint in der Kontakthistorie.
- Erinnerung im Programm, per E-Mail ab Phase 2 (sobald der Mailversand eingerichtet ist).

Abnahme:

- Überfällige Wiedervorlagen stehen oben auf der Startseite.
- Eine erledigte Wiedervorlage erscheint in der Historie des Kontakts.

## K-5 Benutzer, Anmeldung, Rechte

- Erster Start: Einrichtungsassistent für Firmendaten und den ersten Benutzer (Rolle Inhaber). Es gibt keine voreingestellten Konten oder Kennwörter.
- Rollen:
  - **Inhaber:** alles, einschließlich Einstellungen, Benutzerverwaltung und Protokoll.
  - **Mitarbeiter:** Kontakte, Wiedervorlagen und Belege bearbeiten; keine Einstellungen, keine Benutzerverwaltung, kein Protokoll.
- Anmeldung mit E-Mail-Adresse und Kennwort. Das Kennwort hat mindestens 12 Zeichen, wird mit einer Liste häufiger Kennwörter abgeglichen und nur als Argon2-Hash gespeichert.
- Zwei-Faktor-Anmeldung per Authenticator-App (TOTP) für alle verfügbar; Pflicht für Inhaber, sobald das Programm im Netzwerk erreichbar ist.
- Nach 5 Fehlversuchen wird die Anmeldung für dieses Konto 15 Minuten gesperrt.
- Automatische Abmeldung nach 8 Stunden Inaktivität (einstellbar).
- Kennwort vergessen: Rücksetzlink per E-Mail ab Phase 2, bis dahin setzt der Inhaber es zurück.

Abnahme:

- Ein Mitarbeiter kann Einstellungen weder sehen noch über die direkte Adresse aufrufen.
- Das Kennwort „passwort1234“ wird abgelehnt.
- In der Datenbank stehen Kennwörter nur als Argon2-Hash.

## K-6 Änderungsprotokoll

- Jede Anlage, Änderung und Löschung von Geschäftsdaten wird protokolliert: wann, wer, was (Feld, alter Wert, neuer Wert).
- Anmeldungen und fehlgeschlagene Anmeldeversuche werden ebenfalls protokolliert.
- Das Protokoll ist nur lesbar, für niemanden änderbar und nur für Inhaber sichtbar.
- Aufbewahrung und Löschung: siehe [05-betrieb.md](05-betrieb.md).

Abnahme:

- Die Änderung einer Anschrift erzeugt einen Protokolleintrag mit altem und neuem Wert.

## Sicherheit Phase 1

- CSRF-Schutz auf allen Formularen; Content-Security-Policy ohne Inline-Skripte; sichere Cookies bei HTTPS.
- Rechteprüfung serverseitig für jede Ansicht, mit Tests für jede Rolle.
- Keine Abhängigkeit mit bekannter Sicherheitslücke (`pip-audit` in der CI).
