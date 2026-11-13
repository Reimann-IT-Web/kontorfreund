# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Inhaber kleiner Unternehmen in Deutschland, meist Solo-Selbstständige, als Kleinunternehmer nach § 19 UStG oder mit 19 % Umsatzsteuer (z. B. IT-Service, Webagentur, Handwerk, Dienstleistung). Typische Szene: allein im Homeoffice am Schreibtisch-PC mit großem Bildschirm, oft abends oder zwischen Kundenterminen. Häufigste Aufgabe: Angebote und Rechnungen schreiben und versenden. Daneben Kontakte nachschlagen, Notizen erfassen, Wiedervorlagen abarbeiten, Zahlungseingänge prüfen. Teams mit bis zu 5 Personen sind möglich, aber nicht der Normalfall. Handy und Tablet sind Nebenschauplätze (nachschlagen, kurz notieren).

## Product Purpose

Kontorfreund (Edition Kleinunternehmen) ersetzt klassische, Access- bzw. Office-gebundene Desktop-Bürosoftware: Kunden verwalten und rechtssichere Rechnungen schreiben, an einem ruhigen Ort, im Browser, auf dem eigenen Rechner. Erfolg heißt: Der Inhaber sieht beim Öffnen sofort, was heute zu tun ist, schreibt eine korrekte Rechnung in Sekunden und muss über Finanzamt-Pflichten (Pflichtangaben, Umsatzsteuer oder § 19 UStG, E-Rechnung, Aufbewahrung) nicht nachdenken.

## Positioning

Quelloffen (AGPL-3.0), ohne Microsoft und ohne Cloud-Zwang: läuft lokal auf dem eigenen Rechner, die Daten bleiben beim Nutzer. Fachlich auf deutsche Selbstständige und Kleinunternehmer zugeschnitten: § 19 UStG, Umsatzsteuer mit 19 % samt § 13b, ZUGFeRD als Standardformat jeder Rechnung, GoBD-Festschreibung und Aufbewahrung sind eingebaut statt nachgerüstet. Ermäßigte 7 % und mehrere Steuersätze auf einer Rechnung fehlen noch. Ziel, noch nicht erreicht: das Programm existiert als Grundgerüst, die Funktionen entstehen ab Phase 1.

## Operating Context

- Schreibtisch-PC im Homeoffice, Browser, oft ein einzelner Nutzer.
- Belege: Rechnungen als ZUGFeRD-PDF (PDF/A-3 mit XML), Briefpapier nach DIN 5008, Versand per E-Mail.
- Umfeld: Steuerberater (DATEV-Export), Finanzamt (Betriebsprüfung, Aufbewahrung 8 Jahre), Bank (Zahlungseingänge, GiroCode).
- Herkunft vieler Nutzer: ältere Desktop-Bürosoftware mit vielen Reitern und kleinen Formularen, Excel-Listen, Papierordner.

## Capabilities and Constraints

- Funktionen und Phasen: `docs/spec/` (Kontakte, Historie, Wiedervorlagen, Benutzer in Phase 1; Belege, E-Rechnung, Festschreibung in Phase 2; Zahlungen, Mahnwesen, DATEV in Phase 3).
- Technik: Django-Templates, eigenes CSS, HTMX statt JS-Framework. Keine externen CDNs, Schriften oder Skripte (DSGVO); Schriften werden mit ausgeliefert. Content-Security-Policy ohne Inline-Skripte.
- Muss auf Linux, macOS und Windows im Browser laufen; keine Microsoft-Abhängigkeit.
- Begriffe: Kontakt, Wiedervorlage, Angebot, Auftragsbestätigung, Rechnung, Stornorechnung, Rechnungskorrektur (nie „Gutschrift“), Festschreiben, offene Posten, Mahnung.

## Brand Commitments

- Name: „Kontorfreund (Kleinunternehmen)“; Marke „Kontorfreund“, Edition als Zusatz.
- Sprache Deutsch, Anrede „Sie“, verständlich statt Fachjargon.
- Vertraut für Umsteiger von klassischer Desktop-Bürosoftware: Bereiche, Reihenfolge und Begriffe wie dort (Übersicht als Hauptauswahl, Adressen, Angebote & Rechnungen, Artikel, Offene Posten, Wiedervorlagen, Ablage, Auswertungen; Belege in Schritten „Empfänger & Bedingungen“, „Positionen“). Das Aussehen ist eigenständig; fremde Gestaltung (Farben, Symbole, Maskenaufbau, Texte) wird nicht übernommen.
- Darf sich nicht anfühlen wie: verspielt oder bunt; kalt wie Buchhaltungssoftware; zu leer (jede Info nur per Klick); zu voll (alles gleichzeitig, kleine Schrift, viele Reiter).
- Keine Werbung, kein Tracking.

## Evidence on Hand

Keine. Es gibt kein Logo, keine Kundenstimmen, keine echten Kundendaten, keine Screenshots, keine Preise. Demonstrationsdaten im Prototyp sind erfunden und müssen als Beispieldaten erkennbar sein.

## Product Principles

1. Heute zuerst: Die Startseite ist die Arbeitsliste des Tages, kein Menü und kein Diagramm-Dashboard.
2. Die Rechnung ist der Kern: jeder Weg führt in wenigen Schritten zu einer fertigen, korrekten Rechnung.
3. Pflichten erledigt das Programm: Steuer- und Aufbewahrungsregeln sind eingebaut und werden in Klartext erklärt, nicht als Formularfelder abgefragt.
4. Ruhig, aber vollständig: alles Wichtige sichtbar, nichts Überflüssiges.
5. Die Daten gehören dem Nutzer: lokal, offen, exportierbar.

## Accessibility & Inclusion

WCAG 2.2 Stufe AA. Vollständig per Tastatur bedienbar mit sichtbarem Fokus; globale Suche per Strg+K bzw. ⌘K. Zielgruppe umfasst ältere Inhaber, die von Desktop-Software umsteigen: gut lesbare Schriftgrößen, klare Beschriftungen statt reiner Symbole.
