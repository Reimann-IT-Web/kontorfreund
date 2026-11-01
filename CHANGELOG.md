# Änderungen

## 0.3.1 – 01.11.2026

Ergebnisse einer Sicherheitsprüfung des gesamten Codes:

- Anhänge aus empfangenen E-Rechnungen bekommen beim Herunterladen die Endung ihres Dateityps, nicht die des Absenders. Ein präparierter Anhang „Rechnung.pdf.exe“ wird so zu „Rechnung.pdf.bin“ und startet nicht per Doppelklick.
- Exporte als Excel und CSV: Text, der mit „=“, „+“, „-“ oder „@“ beginnt, etwa ein Name aus einer fremden E-Rechnung, wird nicht mehr als Formel ausgeführt.
- E-Rechnungen mit einer Dokumenttyp-Definition werden jetzt in jeder Zeichenkodierung abgelehnt, nicht nur in UTF-8.
- Unter macOS und Linux ist der Datenordner nur noch für den eigenen Benutzer lesbar.
- Neuer Befehl `Kontorfreund entsperren` für den Notfall, etwa wenn der Inhaber das Telefon für die Zwei-Faktor-Anmeldung verloren hat.

## 0.3.0 – 01.11.2026

- DATEV-Export unter „Auswertungen“: alle Rechnungen, Stornos und Korrekturen eines Jahres, Quartals oder Monats als Buchungsstapel im DATEV-Format für den Steuerberater, auf Wunsch zusammen mit den Rechnungs-PDFs als ZIP. Kontenrahmen SKR 03 oder SKR 04, ein Debitorenkonto je Kunde oder ein Sammelkonto, Erlöskonten je Umsatzsteuer einstellbar. Vor dem Herunterladen zeigt eine Vorschau jede Buchung.
- Installationsprogramm und Hilfe nennen den Urheber Reimann IT & Web und die Lizenz AGPL-3.0; der Lizenztext liegt im Programmordner.

## 0.2.0 – 01.11.2026

- Rechnungsausgangsbuch unter „Auswertungen“: alle Rechnungen, Stornos und Korrekturen eines Jahres, Quartals oder Monats mit Kunde, Netto, Umsatzsteuer, Brutto, bezahltem und offenem Betrag. Die aus dem bisherigen Programm übernommenen Belege stehen mit dem gedruckten Betrag dabei.
- Export des Rechnungsausgangsbuchs als CSV, Excel (XLSX) und LibreOffice (ODS), mit echten Zahlen und Daten zum Weiterrechnen.

## 0.1.0 – 01.11.2026

Die erste Version zum Installieren.

**Installation**

- Windows: Installationsprogramm `Kontorfreund-Setup-0.1.0.exe`, ohne Administratorrechte. Kontorfreund startet aus dem Startmenü oder vom Desktop und öffnet sich im Browser.
- macOS und Linux: Programmordner als Archiv, gestartet mit `Kontorfreund`.
- Die Daten liegen getrennt vom Programm im Benutzerordner (Windows: `%LOCALAPPDATA%\Kontorfreund`). Ein Update bringt die Datenbank selbst auf den neuen Stand und sichert sie vorher, wenn die Datensicherung eingerichtet ist. Beim Deinstallieren bleiben die Daten erhalten.

**Funktionen**

- Adressen für Kunden, Interessenten und Lieferanten mit Dublettenprüfung und Archiv.
- Artikel und Leistungen mit Preisen, einzufügen in Angebote und Rechnungen.
- Angebote mit Gültigkeit und Antwort des Kunden; aus dem angenommenen Angebot wird mit einem Klick die Rechnung.
- Rechnungen als PDF/A-3 mit ZUGFeRD, auf Wunsch als XRechnung, mit GiroCode und Versand per E-Mail. Festgeschriebene Rechnungen sind unveränderbar; korrigiert wird per Stornorechnung oder Rechnungskorrektur.
- Kleinunternehmer nach § 19 UStG, Regelbesteuerung mit 19 % und Steuerschuldnerschaft nach § 13b UStG. Warnung vor den Umsatzgrenzen der Kleinunternehmer.
- Skonto und der Hinweis nach § 286 Abs. 3 BGB für Verbraucher.
- Offene Posten mit Zahlungen, Teilzahlungen, Skonto und Ausbuchen; Mahnwesen in drei Stufen mit Verzugszinsen nach § 288 BGB.
- Eingangsrechnungen: XRechnung und ZUGFeRD hochladen, lesbar anzeigen, dem Lieferanten zuordnen und unverändert aufbewahren.
- Ablage der aus dem bisherigen Programm übernommenen Belege.
- Anmeldung mit Kennwort und auf Wunsch Zwei-Faktor-Anmeldung, Konten für Mitarbeiter.
- Änderungsprotokoll: wer wann was geändert hat.
- Verschlüsselte Datensicherung, täglich und vor jedem Update, mit zweitem Speicherort und Wiederherstellung.
