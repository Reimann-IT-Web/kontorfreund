# 03 Belege (Phase 2)

Entwurf – wird vor Beginn von Phase 2 verfeinert und erneut freigegeben.

## B-1 Artikel und Leistungen

- Felder: Nummer, Bezeichnung, Beschreibung, Einheit, Nettopreis, Steuersatz, aktiv/inaktiv.
- Einheiten mit Code nach UN/ECE-Empfehlung 20 (z. B. Stück `H87`, Stunde `HUR`, Tag `DAY`, Pauschale `LS`) – nötig für die E-Rechnung.
- Positionen lassen sich auch ohne Artikel frei erfassen.

## B-2 Belegarten und Ablauf

- Angebot → Auftragsbestätigung → Rechnung. Jeder Schritt übernimmt Positionen und Texte; Schritte lassen sich überspringen.
- Eine Rechnung wird nur per **Stornorechnung** (vollständig) oder **Rechnungskorrektur** (Teilbetrag) korrigiert, jeweils mit Bezug auf das Original. Die Bezeichnung ist nie „Gutschrift“ – das ist im Umsatzsteuerrecht die Abrechnung durch den Leistungsempfänger (§ 14 Abs. 2 S. 2 UStG).
- Status: Rechnungen Entwurf, festgeschrieben, bezahlt, teilbezahlt, überfällig, storniert. Angebote Entwurf, versendet, angenommen, abgelehnt, abgelaufen.
- Kopf- und Fußtexte als Textbausteine. Zahlungsbedingungen: Zahlungsziel in Tagen, optional Skonto (Prozent und Frist).
- Belege kopieren, z. B. für die gleiche Rechnung wie im Vormonat.

## B-3 Nummernkreise

- Ein Nummernkreis je Belegart, Format mit Jahr und Zähler einstellbar, z. B. `RE-2026-0001`.
- Rechnungsnummern sind fortlaufend und einmalig (§ 14 Abs. 4 S. 1 Nr. 4 UStG). Die Nummer wird erst beim Festschreiben vergeben, damit verworfene Entwürfe keine Lücken erzeugen.

## B-4 Steuer

| Steuerfall | Ausweis | Pflichthinweis auf dem Beleg |
|---|---|---|
| Regelbesteuerung | 19 %, 7 % oder 0 % je Position, Summe je Steuersatz | – |
| Kleinunternehmer (§ 19 UStG) | keine Umsatzsteuer | Hinweis auf die Steuerbefreiung nach § 19 UStG |
| Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG) | keine Umsatzsteuer, USt-IdNr. des Kunden nötig | „Steuerschuldnerschaft des Leistungsempfängers“ (§ 14a Abs. 5 UStG) |

- Der Steuerfall wird aus den Firmendaten vorbelegt (Kleinunternehmer ja/nein) und ist je Beleg änderbar.
- Umsatzgrenzen nach § 19 UStG (seit 2025): Vorjahr höchstens 25.000 €, laufendes Jahr höchstens 100.000 €. Das Programm zeigt den Jahresumsatz und warnt ab 80 % jeder Grenze. Würde eine Rechnung die 100.000-€-Grenze überschreiten, weist es vor dem Festschreiben darauf hin, dass bereits dieser Umsatz der Regelbesteuerung unterliegt.
- Beträge werden mit `Decimal` berechnet: Positionsbeträge auf 2 Nachkommastellen, die Steuer je Steuersatz aus der Summe der Positionen (Rechenregeln nach EN 16931).
- Die vereinfachten Angaben für Kleinbetragsrechnungen und Kleinunternehmer (§§ 33, 34a UStDV) sind erlaubt, standardmäßig gibt das Programm aber alle Angaben aus.

## B-5 Prüfung vor dem Festschreiben

Das Programm prüft die Pflichtangaben nach § 14 Abs. 4 UStG und nennt fehlende Punkte im Klartext:

1. Name und Anschrift von Leistendem und Empfänger
2. Steuernummer oder USt-IdNr. des Leistenden
3. Ausstellungsdatum
4. Rechnungsnummer
5. Menge und Art der Lieferung bzw. Umfang und Art der Leistung
6. Zeitpunkt der Lieferung oder Leistung (Datum oder Zeitraum)
7. Entgelt aufgeschlüsselt nach Steuersätzen, im Voraus vereinbarte Minderungen (z. B. Skonto)
8. Steuersatz und Steuerbetrag oder Hinweis auf die Steuerbefreiung

## B-6 PDF

- Erzeugt mit Typst als PDF/A-3b.
- Briefpapier: Logo, Akzentfarbe, Absenderzeile, Fußzeile (Bank, Steuernummer, Kontakt), Anschriftfeld nach DIN 5008.
- Unterschrift: Bild und Text aus den Firmendaten am Ende von Rechnung, Angebot, Auftragsbestätigung und Mahnung, mit dem Schlusstext auf einer Seite.

## B-7 E-Rechnung erzeugen

- **ZUGFeRD** ist das Standardformat für jede Rechnung: jeweils aktuelle Version 2.x (technisch identisch mit Factur-X), Profil EN 16931, als PDF/A-3 mit eingebetteter XML. Der Kunde bekommt ein normales PDF, seine Software liest die XML.
- Zusätzlich XRechnung (Syntax CII) für Behörden und für Kunden, die sie verlangen.
- Die Profile MINIMUM und BASIC WL werden nicht angeboten, weil sie nicht als E-Rechnung gelten.
- Käuferreferenz (BT-10) je Kontakt hinterlegbar, bei Behörden die Leitweg-ID.
- Vor dem Festschreiben prüft das Programm die wichtigsten Geschäftsregeln selbst und meldet Fehler im Klartext. In der CI wird jede Testrechnung zusätzlich mit dem offiziellen KoSIT-Validator geprüft.
- Kleinunternehmer müssen keine E-Rechnungen ausstellen (§ 34a UStDV), andere Unternehmen spätestens ab 2027 bzw. 2028 (Übergangsregeln § 27 Abs. 38 UStG). Das Programm bietet E-Rechnungen trotzdem allen an, weil Kunden sie verlangen.

## B-8 Festschreiben und Versand

- „Festschreiben“ vergibt die Nummer, erzeugt PDF und XML, speichert beide mit SHA-256-Prüfsumme und sperrt den Beleg dauerhaft.
- Versand per E-Mail über den eigenen Mailserver (SMTP, Zugangsdaten verschlüsselt gespeichert), mit Eintrag in der Kontakthistorie.
- Alternativ Download zum Selbstversand oder Ausdrucken.

## B-9 Ablage und Aufbewahrung

- Beim Festschreiben legt das Programm PDF und XML im Datenverzeichnis ab (`belege/<Jahr>/<Belegnummer>.pdf` bzw. `.xml`) und speichert ihre SHA-256-Prüfsummen in der Datenbank.
- Bei E-Rechnungen ist die XML das maßgebliche Original und wird immer mit aufbewahrt.
- Aufbewahrungsfrist: 8 Jahre ab Ende des Ausstellungsjahres (§ 14b UStG, § 147 AO). Bis dahin ändert oder löscht das Programm diese Dateien nie, und sie müssen jederzeit lesbar und maschinell auswertbar sein (§ 147 Abs. 2 AO).
- Täglich vergleicht das Programm die Prüfsummen. Wurde eine Datei außerhalb des Programms verändert oder gelöscht, erfährt der Inhaber es sofort und der Vorfall wird protokolliert.
- Ablageort je Betriebsart: Einzelplatz auf dem eigenen Rechner, Netzwerk auf Server oder NAS, gehostet im Rechenzentrum in Deutschland. In jedem Fall gehören die Belege zur Datensicherung ([05-betrieb.md](05-betrieb.md), D-2).

## Abnahme Phase 2

- Der KoSIT-Validator akzeptiert XRechnung und ZUGFeRD-XML für alle Testfälle: Regelbesteuerung, § 19, § 13b, Skonto, mehrere Steuersätze.
- Der Mustang-Validator akzeptiert jedes ZUGFeRD-PDF (prüft PDF/A-3 und eingebettete XML).
- Eine außerhalb des Programms veränderte Beleg-Datei wird bei der nächsten Prüfung gemeldet.
- Eine festgeschriebene Rechnung lässt sich weder über die Oberfläche noch über direkte Anfragen ändern.
- Auch bei gleichzeitigem Festschreiben durch zwei Benutzer entstehen keine doppelten Nummern und keine Lücken.
