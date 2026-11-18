# 03 Belege (Phase 2)

Entwurf – wird vor Beginn von Phase 2 verfeinert und erneut freigegeben.

## B-1 Artikel und Leistungen

- Felder: Nummer, Bezeichnung, Beschreibung, Einheit, Nettopreis, Steuersatz, aktiv/inaktiv.
- Einheiten mit Code nach UN/ECE-Empfehlung 20 (z. B. Stück `H87`, Stunde `HUR`, Tag `DAY`, Pauschale `LS`) – nötig für die E-Rechnung.
- In Rechnung, Angebot, Auftragsbestätigung und Vertrag (B-10) lassen sich aktive Artikel als Position einfügen. Die Position übernimmt Bezeichnung, Beschreibung, Einheit, Preis und Steuersatz als Kopie; spätere Änderungen am Artikel berühren sie nicht.
- Den Steuersatz (B-4) zeigt das Formular, wenn die Firmendaten „Umsatzsteuer ausweisen“ wählen oder der Artikel schon 7 % hat.
- Positionen lassen sich auch ohne Artikel frei erfassen.

## B-2 Belegarten und Ablauf

- Angebot → Auftragsbestätigung → Rechnung. Jeder Schritt übernimmt Positionen und Texte; Schritte lassen sich überspringen.
- Eine Rechnung wird nur per **Stornorechnung** (vollständig) oder **Rechnungskorrektur** (Teilbetrag) korrigiert, jeweils mit Bezug auf das Original. Die Bezeichnung ist nie „Gutschrift“ – das ist im Umsatzsteuerrecht die Abrechnung durch den Leistungsempfänger (§ 14 Abs. 2 S. 2 UStG).
- Status: Rechnungen Entwurf, festgeschrieben, bezahlt, teilbezahlt, überfällig, storniert. Angebote Entwurf, versendet, angenommen, abgelehnt, abgelaufen.
- Kopf- und Fußtexte als Textbausteine. Zahlungsbedingungen: Zahlungsziel in Tagen, optional Skonto (Prozent und Frist).
- Rabatt in Prozent auf die Summe aller Positionen, optional, für Rechnung, Angebot und Auftragsbestätigung (unter 100 %). Der Beleg zeigt Zwischensumme und Rabatt über Netto bzw. Gesamtbetrag; in der E-Rechnung ist er ein Abschlag auf Belegebene (BG-20) mit der Steuerkategorie der Positionen. Angebot, Auftragsbestätigung und Rechnung reichen ihn weiter; Stornorechnung und Rechnungskorrektur übernehmen ihn vom Original, dort ist er nicht änderbar.
- Belege kopieren, z. B. für die gleiche Rechnung wie im Vormonat.

## B-3 Nummernkreise

- Ein Nummernkreis je Belegart, Format mit Jahr und Zähler einstellbar, z. B. `RE-2026-0001`.
- Rechnungsnummern sind fortlaufend und einmalig (§ 14 Abs. 4 S. 1 Nr. 4 UStG). Die Nummer wird erst beim Festschreiben vergeben, damit verworfene Entwürfe keine Lücken erzeugen.

## B-4 Steuer

| Steuerfall | Ausweis | Pflichthinweis auf dem Beleg |
|---|---|---|
| Regelbesteuerung | 19 % oder 7 % je Position, Entgelt und Steuer je Steuersatz | – |
| Kleinunternehmer (§ 19 UStG) | keine Umsatzsteuer | Hinweis auf die Steuerbefreiung nach § 19 UStG |
| Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG) | keine Umsatzsteuer, USt-IdNr. des Kunden nötig | „Steuerschuldnerschaft des Leistungsempfängers“ (§ 14a Abs. 5 UStG) |
| Steuerfreie Leistung (§ 4 UStG, etwa Nr. 14 Heilbehandlung oder Nr. 21 Unterricht und Bildung) | keine Umsatzsteuer | Hinweis auf die Steuerbefreiung (§ 14 Abs. 4 S. 1 Nr. 8 UStG), Wortlaut aus den Firmendaten |

- Der Steuerfall wird aus den Firmendaten vorbelegt und ist je Beleg änderbar: „steuerfrei“, wenn dort „Meine Leistungen sind in der Regel steuerfrei“ angekreuzt ist, sonst nach Kleinunternehmer ja/nein.
- Steuerfreie Leistungen: Den Hinweis tragen Sie einmal in den Firmendaten ein, z. B. „Umsatzsteuerfrei nach § 4 Nr. 21 UStG“. Welche Befreiung gilt, entscheidet der Nutzer, das Programm prüft sie nicht. Ohne Hinweis lässt sich ein steuerfreier Beleg nicht festschreiben oder fertigstellen (B-5 Nr. 8). Der Wortlaut wird beim Festschreiben eingefroren; Stornorechnung und Rechnungskorrektur übernehmen ihn vom Original. Gilt für Rechnung, Angebot und Auftragsbestätigung.
- E-Rechnung bei steuerfreien Leistungen: Umsatzsteuer-Kategorie E (befreit), Satz 0 %, der Hinweis als Befreiungsgrund (BT-120). Einen Befreiungscode (BT-121) setzt das Programm nicht, weil es die Rechtsgrundlage nicht kennt.
- Steuersatz je Position: 19 % oder 7 % (§ 12 Abs. 2 UStG), vorbelegt mit 19 % bzw. dem Satz des Artikels. Der Editor zeigt die Auswahl nur bei Regelbesteuerung; bei den anderen Steuerfällen bleibt der Satz gespeichert, wirkt aber nicht. Rechnung, Angebot, Auftragsbestätigung und Vertrag haben ihn, jeder Übergang, jede Kopie, Stornorechnung und Rechnungskorrektur übernimmt ihn.
- Mit mehreren Sätzen nennt jede Position auf dem Beleg ihren Satz (Spalte „USt“), und über dem Gesamtbetrag stehen Nettobetrag und Umsatzsteuer je Satz (§ 14 Abs. 4 S. 1 Nr. 7 und 8 UStG). Ein Rabatt (B-2) gilt je Satz auf die Summe seiner Positionen; der Beleg zeigt ihn weiter als einen Betrag.
- E-Rechnung: Jede Position trägt ihren Satz (BT-152), die Aufschlüsselung (BG-23) und der Rabatt als Abschlag (BG-20) stehen je Satz (BR-S-08, BR-S-09).
- Ein Steuerfall gilt für den ganzen Beleg. Belege mit steuerfreien und steuerpflichtigen Positionen zugleich sowie der Nullsatz (§ 12 Abs. 3 UStG, Kategorie Z) kommen später.
- Belege, die vor den Steuersätzen je Position festgeschrieben wurden, gelten mit 19 % bzw. ohne Umsatzsteuer, wie sie gedruckt sind.
- Umsatzgrenzen nach § 19 UStG (seit 2025): Vorjahr höchstens 25.000 €, laufendes Jahr höchstens 100.000 €. Das Programm zeigt den Jahresumsatz und warnt ab 80 % jeder Grenze. Würde eine Rechnung die 100.000-€-Grenze überschreiten, weist es vor dem Festschreiben darauf hin, dass bereits dieser Umsatz der Regelbesteuerung unterliegt.
- Steuerfreie Rechnungen zählen nicht zu diesem Umsatz: § 19 Abs. 2 Nr. 1 UStG zieht die Umsätze nach § 4 Nr. 8 Buchst. i, Nr. 9 Buchst. b und Nr. 11 bis 29 vom Gesamtumsatz ab. Die Hilfe nennt die Ausnahme: Umsätze nach § 4 Nr. 8 Buchst. a bis h, Nr. 9 Buchst. a und Nr. 10 zählen mit, wenn sie keine Hilfsumsätze sind; diese rechnet der Nutzer selbst hinzu.
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
- Briefpapier: Briefkopf, Absenderzeile, Fußzeile (Bank, Steuernummer, Kontakt, auf Wunsch Internetadresse), Anschriftfeld nach DIN 5008.
- Briefkopf auf Seite 1, einstellbar auf einer eigenen Seite mit Vorschau (nur Inhaber), gleich für Rechnung, Angebot, Auftragsbestätigung, Mahnung und die Auskunft nach Art. 15 DSGVO:
  - Aufbau „Logo und Angaben“: Logo (SVG, PNG oder JPG bis 1 MB) 6 bis 20 mm hoch, links, in der Mitte oder rechts; ein sehr breites Logo wird schmaler gesetzt, damit die Angaben daneben Platz behalten. Firmenname mit Marke oder Zusatz und Anschrift mit Telefon und E-Mail lassen sich einzeln ausblenden; Absenderzeile und Fußzeile bleiben. Auf Wunsch schneidet der Druck weiße oder durchsichtige Ränder eines PNG oder JPG ab, die gespeicherte Datei bleibt unverändert.
  - Aufbau „Eigenes Kopfbild“: ein selbst gestaltetes Bild ersetzt Logo und Angaben, so breit wie der Text oder über die ganze Seitenbreite bis an den Blattrand.
  - Akzentfarbe für Firmenname und Linie unter dem Kopf; die Linie lässt sich abschalten.
  - Kein Kopf reicht in Infoblock oder Anschriftfeld: Ein Kopfbild endet spätestens 44 mm unter der Blattkante, die Linie 2 mm darunter; ein höheres Kopfbild wird kleiner gesetzt. Das Logo ist höchstens 20 mm hoch. Der Text beginnt nie früher als 94 mm unter der Blattkante.
  - Die Vorgaben ergeben den bisherigen Kopf (Logo 12 mm links, Name, Anschrift, Linie in Petrol). Änderungen gelten für neue Belege; festgeschriebene bleiben, wie sie abgelegt sind.
- Unterschrift: Bild und Text aus den Firmendaten am Ende von Rechnung, Angebot, Auftragsbestätigung und Mahnung, mit dem Schlusstext auf einer Seite. Steht der Name im Text unter der Unterschrift, entfällt beim Drucken die gleiche Zeile am Ende des Schlusstexts.
- Seitenwechsel: Eine Position bleibt auf einer Seite. Ist sie höher als 60 mm, trennt die Seite nur zwischen zwei Zeilen der Beschreibung, und die Bezeichnung bleibt bei der ersten Zeile. Nur eine Zeile, die selbst höher als 60 mm ist, darf reißen.
- Schluss: Schlusstext und Unterschrift bleiben bis 60 mm Höhe auf einer Seite, und der Zahlungshinweis wechselt mit ihnen die Seite, damit Gruß und Name nie allein auf der letzten Seite stehen. Ein längerer Schluss trennt nur zwischen zwei Zeilen; die letzten beiden Zeilen mit Text (Gruß und Name) bleiben beisammen und bei der Unterschrift.
- Zahlungshinweis: Ohne eigenen Text druckt die Rechnung Zahlungsziel, Bankverbindung und Verwendungszweck im festen Wortlaut. Ein eigener Text in den Firmendaten ersetzt diese Zeilen, mit den Platzhaltern {betrag}, {nummer}, {datum}, {faellig}, {iban} und {bank}; unbekannte Platzhalter lehnt das Formular ab. Skonto und Verzugshinweis stehen weiter darunter. Der Text wird beim Festschreiben eingefroren. Stornorechnung, Rechnungskorrektur und Mahnung behalten ihren eigenen Text.
- Menge: Die Einheit steht hinter der Zahl. Eine Position oder ein Artikel „ohne Einheit“ zeigt nur die Zahl; die E-Rechnung nimmt dann den Code C62 (Einheit).

## B-7 E-Rechnung erzeugen

- **ZUGFeRD** ist das Standardformat für jede Rechnung: jeweils aktuelle Version 2.x (technisch identisch mit Factur-X), Profil EN 16931, als PDF/A-3 mit eingebetteter XML. Der Kunde bekommt ein normales PDF, seine Software liest die XML.
- Zusätzlich XRechnung (Syntax CII) für Behörden und für Kunden, die sie verlangen.
- Die Profile MINIMUM und BASIC WL werden nicht angeboten, weil sie nicht als E-Rechnung gelten.
- Käuferreferenz (BT-10) je Kontakt hinterlegbar, bei Behörden die Leitweg-ID.
- Vor dem Festschreiben prüft das Programm die wichtigsten Geschäftsregeln selbst und meldet Fehler im Klartext. In der CI wird jede Testrechnung zusätzlich mit dem offiziellen KoSIT-Validator geprüft.
- Kleinunternehmer müssen keine E-Rechnungen ausstellen (§ 34a UStDV), andere Unternehmen spätestens ab 2027 bzw. 2028 (Übergangsregeln § 27 Abs. 38 UStG). Das Programm bietet E-Rechnungen trotzdem allen an, weil Kunden sie verlangen.

## B-8 Festschreiben und Versand

- „Festschreiben“ vergibt die Nummer, erzeugt PDF und XML, speichert beide mit SHA-256-Prüfsumme und sperrt den Beleg dauerhaft.
- Ein Entwurf, der an einem späteren Tag wieder geöffnet wird, zeigt als Datum den heutigen Tag, damit er nicht mit dem Datum des Anlegens festgeschrieben wird; unter dem Feld steht das bisherige Datum. Übernommen wird es mit dem Speichern. Wer am selben Tag bewusst ein früheres Datum einträgt und speichert, behält es; ein Datum in der Zukunft bleibt. Gilt für Rechnung, Angebot und Auftragsbestätigung.
- Versand per E-Mail über den eigenen Mailserver (SMTP, Zugangsdaten verschlüsselt gespeichert), mit Eintrag in der Kontakthistorie. Eine Test-E-Mail an die eigene Adresse prüft die Zugangsdaten und nennt bei einem Fehler die Ursache.
- Alternativ Download zum Selbstversand oder Ausdrucken.

## B-9 Ablage und Aufbewahrung

- Beim Festschreiben legt das Programm PDF und XML im Datenverzeichnis ab (`belege/<Jahr>/<Belegnummer>.pdf` bzw. `.xml`) und speichert ihre SHA-256-Prüfsummen in der Datenbank.
- Bei E-Rechnungen ist die XML das maßgebliche Original und wird immer mit aufbewahrt.
- Aufbewahrungsfrist: 8 Jahre ab Ende des Ausstellungsjahres (§ 14b UStG, § 147 AO). Bis dahin ändert oder löscht das Programm diese Dateien nie, und sie müssen jederzeit lesbar und maschinell auswertbar sein (§ 147 Abs. 2 AO).
- Täglich vergleicht das Programm die Prüfsummen. Wurde eine Datei außerhalb des Programms verändert oder gelöscht, erfährt der Inhaber es sofort und der Vorfall wird protokolliert.
- Ablageort je Betriebsart: Einzelplatz auf dem eigenen Rechner, Netzwerk auf Server oder NAS, gehostet im Rechenzentrum in Deutschland. In jedem Fall gehören die Belege zur Datensicherung ([05-betrieb.md](05-betrieb.md), D-2).

## B-10 Wiederkehrende Rechnungen (Verträge)

- Ein Vertrag beschreibt eine Rechnung, die sich in festem Rhythmus wiederholt, etwa für eine Wartung: Empfänger, Bezeichnung (nur für den Nutzer), Betreff, Positionen, Rabatt in Prozent (B-2), Steuerfall, Zahlungsziel, Rhythmus (monatlich, vierteljährlich, halbjährlich, jährlich), Beginn des ersten Zeitraums und auf Wunsch ein Ende.
- Abgerechnet wird im Voraus: Am ersten Tag jedes Zeitraums legt das Programm einen Rechnungsentwurf an. Leistungszeitraum ist der ganze Zeitraum, Rechnungsdatum der Tag, an dem der Entwurf entsteht. Lief das Programm am Stichtag nicht, entsteht der Entwurf beim nächsten Lauf; je Zeitraum genau einer, auch wenn mehrere Zeiträume nachzuholen sind.
- Der Entwurf ist eine gewöhnliche Rechnung mit Verweis auf den Vertrag: Der Nutzer ergänzt etwa Zusatzstunden, prüft, schreibt fest und versendet. Festgeschrieben wird nie von selbst.
- Änderungen am Vertrag gelten für die folgenden Entwürfe; vorhandene Entwürfe und Rechnungen bleiben, wie sie sind. Ein beendeter Vertrag erzeugt keine Entwürfe mehr. Ein Vertrag lässt sich löschen; seine Rechnungen bleiben und verlieren nur den Verweis.
- Auf Wunsch (2, 4 oder 8 Wochen vorher, Vorgabe 4) legt das Programm vor jedem Zeitraum eine Wiedervorlage an der Adresse an: Fortsetzung und Preis mit dem Kunden klären. Einmal je Zeitraum; nicht, wenn der Vertrag erst nach diesem Tag angelegt wurde.
- Sind Benachrichtigungen über Telegram eingerichtet, nennt die Tagesübersicht jeden neuen Entwurf einmal mit Bezeichnung des Vertrags und Betrag. Mit eingerichtetem E-Mail-Versand kommt er als eigene Nachricht mit den Knöpfen „Festschreiben und senden“ (mit dem heutigen Datum und denselben Prüfungen wie im Editor, an die E-Mail-Adresse der Adresse) und „Später“ (M-3).
- Wird eine Adresse gesperrt (D-1), enden ihre Verträge. Die Auskunft nennt sie, die Löschung entfernt sie mit.

## B-11 Serienrechnungen aus einer Teilnehmerliste

Freigegeben am 18.11.2026. Anlass: Ein Anbieter von Webinaren führt je Termin eine Excel-Liste der Teilnehmer und schreibt jedem eine Rechnung. Entwickelt und getestet wird nur mit einer erfundenen Liste derselben Form; echte Listen kommen nicht ins Repository.

Ablauf:

1. **Liste hochladen** (XLSX oder ODS). Kontorfreund findet die Zeile mit den Überschriften und ordnet die Spalten wie beim Import (M-6) zu: Kd-Nr., Verein/Büro, Anrede, Titel, Vorname, Name, Adresse, PLZ, Ort, Telefon, Handy, Fax, E-Mail, „Sepa erteilt“, Termin, Thema, Link. Die Zuordnung lässt sich speichern. Andere Spalten (etwa Einloggzeit, Rg.nr., Versand) liest Kontorfreund nicht.
2. **Angaben zur Serie**: Termin, Thema und Link aus der ersten Teilnehmerzeile, änderbar; Leistungsdatum aus dem Termin („03.12.2026, 10-13 Uhr“ ergibt den 03.12.2026), Rechnungsdatum (heute), Preis je Teilnehmer, Zahlungsziel, bei Regelbesteuerung der Steuersatz. Der Preis steht nicht in der Liste; vorgeschlagen wird der der letzten Serie. Weichen Termin oder Thema zwischen den Zeilen ab, nennt die Vorschau die Zeilen.
3. **Vorschau**: je Teilnehmer eine Zeile mit Zeilennummer der Liste, Abschnitt, Kontakt (neu, vorhanden, vorhanden mit Abweichung), Zahlweg mit Grund (B-12), E-Mail und Hinweisen; darunter die übersprungenen Zeilen mit Grund. Jede Zeile lässt sich ab- und anwählen, der Zahlweg umstellen. Gespeichert wird noch nichts.
4. **Entwürfe anlegen**: Kontorfreund legt fehlende Kontakte an und je Teilnehmer einen Rechnungsentwurf, zusammengefasst als Serie. Die hochgeladene Datei bewahrt es danach nicht auf, übersprungene Zeilen speichert es nicht (Datenminimierung, Art. 5 Abs. 1 lit. c DSGVO; Storno-Notizen nennen mitunter Gründe wie eine Krankheit).
5. **Prüfen und festschreiben**: Die Seite der Serie zeigt alle Entwürfe; jeder lässt sich wie gewohnt öffnen, ändern oder löschen. „Alle festschreiben“ prüft jeden Entwurf (B-5) und vergibt die Nummern fortlaufend in der Reihenfolge der Liste (B-3). Ein Entwurf mit Fehlern bleibt Entwurf, die Seite nennt ihn und den Fehler.
6. **Senden**: „Alle per E-Mail senden“ nach einer Rückfrage mit der Anzahl. Jede Rechnung geht als eigene E-Mail an die Adresse ihrer Zeile (B-8), mit Beilage, auf Wunsch mit Kopie an die eigene Adresse, und bekommt einen Eintrag in der Kontakthistorie. Schlägt eine E-Mail fehl, laufen die anderen weiter; die Seite nennt Fehler und Ursache, erneut gesendet wird einzeln. Rechnungen ohne E-Mail-Adresse gibt es gesammelt als ein PDF zum Drucken.
7. **Übersicht** der Serie als XLSX: Zeile der Liste, Kd-Nr., Name, Rechnungsnummer, Betrag, Zahlweg, versendet am. Damit lassen sich Nummern und Versand in die eigene Liste übernehmen.
8. **Lastschriften eingezogen**: Nach dem Einzug bucht ein Knopf auf der Seite der Serie nach Rückfrage für jede festgeschriebene Lastschrift-Rechnung ohne Zahlung, deren Einzugstag erreicht ist, eine Zahlung der Art Lastschrift über den vollen Betrag zum Einzugsdatum (M-2). Eine Rücklastschrift macht der Nutzer an der Rechnung rückgängig.

Teilnehmer erkennen:

- Ein Teilnehmer ist eine Zeile mit Name und dazu Kd-Nr. oder Anschrift. Zeilen, in denen nur Termin, Thema oder Link vorausgefüllt sind, gelten als leer.
- Eine Zeile mit Text in nur einer Zelle und ohne Name ist eine Abschnittsüberschrift. Unter „Stornierung“ oder „Storno“ ist jede Zeile storniert. Steht Storno, storniert, Stornierung oder „storn.“ in einer Zelle einer Teilnehmerzeile (außer Termin, Thema und Link), ist auch sie storniert; ein Ort wie Storndorf zählt nicht. Stornierte Zeilen bekommen keine Rechnung.
- Steht in „Sepa erteilt“ etwas anderes als ein Datum, zeigt die Vorschau den Text als Hinweis und wählt die Zeile ab. Weicht das Datum von einem Mandat an der Adresse ab, nennt die Vorschau beide; es gilt das der Liste.
- Zeilenumbrüche in Termin und Thema (aus einer Excel-Zelle) werden zu Leerzeichen.
- Farben wie rote Schrift wertet Kontorfreund nicht aus. Werte außerhalb der Tabelle (Zeilen ohne Name) liest es nicht; die Vorschau nennt sie als übersprungen.
- Stehen über den Überschriften weitere Zeilen, etwa ein Titel, beginnt die Tabelle mit der ersten Zeile, die „Name“ und zwei weitere bekannte Überschriften enthält.
- Vierstellige PLZ bekommen die Null vorn zurück, wie beim Import (M-6).

Kontakte:

- Die Kd-Nr. der Liste wird die Nummer des Kontakts (9002 wird K-9002). Gibt es ihn schon, gilt er; weichen Name, Anschrift oder E-Mail ab, zeigt die Vorschau beides und übernimmt auf Wunsch die Liste (Vorgabe: die Liste, sie ist neuer). Ohne Kd-Nr. sucht Kontorfreund Dubletten wie beim Import; passt genau eine Adresse, gilt sie, sonst entsteht eine neue mit der nächsten Nummer.
- Heißt die Adresse mit dieser Kd-Nr. in Kontorfreund anders (Nachname einer Person, Firmenname einer Firma), ist es womöglich ein anderer Kunde: Die Vorschau nennt den Namen, wählt die Zeile ab und übernimmt nichts, bis der Nutzer sie wählt.
- Neue Adressen prüft Kontorfreund mit denselben Regeln wie das Formular, an vorhandenen die Felder, die die Liste ändert. Eine archivierte Adresse wird wieder aktiv, eine gesperrte (D-1) bekommt keine Rechnung; die Vorschau nennt sie als übersprungen.
- Mit einem Eintrag in „Verein/Büro“ wird der Kontakt eine Firma mit diesem Namen und dem Teilnehmer als Ansprechpartner, ohne Eintrag eine Person.
- Teilen sich mehrere Zeilen eine Kd-Nr. (Verein mit mehreren Teilnehmern) oder ohne Kd-Nr. dieselbe vorhandene Adresse bzw. denselben Namen mit derselben Anschrift, gibt es einen Kontakt und je Zeile eine Rechnung an ihn. Neue Adressen mit Kd-Nr. entstehen vor denen ohne, damit keine die Nummer einer späteren Zeile belegt. Anschrift und Briefanrede jeder Rechnung nennen den Teilnehmer ihrer Zeile, die E-Mail geht an seine Adresse. Stornorechnung, Rechnungskorrektur und Mahnung zu dieser Rechnung gehen ebenso an ihn; eine Kopie zum Korrigieren gehört zur selben Serie und zum selben Teilnehmer. Stornierte Rechnungen sendet und druckt die Seite der Serie nicht.
- Auskunft und Löschung (D-1) einer Adresse umfassen die Teilnehmer ihrer Rechnungen; deren Einträge im Protokoll werden mit geschwärzt, auch wenn die Aufbewahrungsfrist abläuft.
- Gibt es für denselben Teilnehmer (Kontakt und Name) schon eine Rechnung oder einen Entwurf mit gleichem Termin und Thema, warnt die Vorschau und wählt die Zeile ab. So erzeugt dieselbe Liste kein zweites Mal Rechnungen.

Texte und Beilage:

- Eine Vorlage, die für die nächste Serie gespeichert bleibt: Betreff, Bezeichnung der Position, Text vor und nach den Positionen, Betreff und Text der E-Mail. Platzhalter: {termin}, {thema}, {link}, {betrag} und {kundennummer}, in der E-Mail zusätzlich {nummer}, {datum} und {faellig}. Rechnungsdatum und Fälligkeit stehen nicht in den Texten der Rechnung, weil sie sich beim Festschreiben an einem späteren Tag ändern; die Fälligkeit druckt der Zahlungshinweis. Die Briefanrede des Teilnehmers setzt Kontorfreund vor den Text vor den Positionen und in die E-Mail, die Grußformel ans Ende. Vorgaben: Betreff „Rechnung für die Teilnahme am {termin}“, Position „Teilnahme an „{thema}“ am {termin}“ mit Menge 1 ohne Einheit. Die Platzhalter der Rechnung werden beim Anlegen der Entwürfe gefüllt; danach ist der Text im Entwurf frei änderbar. Unbekannte Platzhalter lehnt das Formular ab.
- Steuerfall aus den Firmendaten (B-4), bei steuerfreien Webinaren mit dem eingetragenen Hinweis. Den Zahlungshinweis bestimmt der Zahlweg (B-12).
- Beilage: eine PDF-Datei je Vorlage bis 5 MB (etwa Hinweise für Einsteiger), die mit der E-Mail als eigene Datei mitgeht und im PDF zum Drucken hinter der Rechnung steht. Die Rechnung selbst bleibt unverändert. Vorgabe: an alle, je Zeile abwählbar; die Vorschau kennzeichnet Teilnehmer, die zum ersten Mal eine Rechnung aus einer Serie bekommen.

Rechnungsnummern:

- Die Rg.nr. der Liste liest Kontorfreund nicht. Es vergibt die Nummern selbst beim Festschreiben, fortlaufend und ohne Lücken (B-3), damit keine Nummer doppelt vorkommt (§ 14 Abs. 4 S. 1 Nr. 4 UStG).

Offen (Rückfrage an die Firma):

1. Beilage an alle oder nur an neue Teilnehmer? Die Vorgabe „an alle, je Zeile abwählbar“ trägt beides.
2. Gläubiger-ID und Mandatsreferenzen. Ist die Kunden-Nr. die Mandatsreferenz? Ihr Lastschrift-Text („unter der Kunden-Nr. … eine Lastschriftermächtigung erteilt“) spricht dafür.
3. Format der Rechnungsnummer: Kontorfreund vergibt bisher fest Jahr und Zähler (260001), die Firma schreibt Zähler/Jahr (0901/26). Das einstellbare Format aus B-3 fehlt noch; soll ihr Format bleiben, kommt es vor der Serie.

Abnahme mit der erfundenen Beispielliste:

- 8 Teilnehmer erkannt; 2 stornierte Zeilen übersprungen und nicht gespeichert, auch die mit der Notiz in „Sepa erteilt“; 3 vorausgefüllte leere Zeilen übersprungen; die rote Nummer außerhalb der Tabelle nicht gelesen.
- Kd-Nr. 9002: ein Kontakt, zwei Rechnungen mit eigenem Ansprechpartner, eigener Briefanrede und eigener E-Mail-Adresse.
- PLZ 06108, 04109 und 01067 mit Null vorn; „Sehr geehrter Herr Dr. Wegener,“.
- Lastschrift bei Kd-Nr. 9003 und 9007, Überweisung bei den übrigen; 9004 mit dem Hinweis auf das Mandat von 2019 (B-12).
- Nummern lückenlos in der Reihenfolge der Liste, auch wenn vorher ein Entwurf der Serie gelöscht wurde.
- Dieselbe Liste ein zweites Mal: Die Vorschau warnt bei allen Zeilen und wählt sie ab.
- Ohne Verbindung zum Mailserver gilt keine Rechnung als versendet, und die Seite nennt die Ursache.

## B-12 SEPA-Lastschrift

Freigegeben am 18.11.2026.

- Zahlweg je Rechnung: Überweisung (wie bisher) oder SEPA-Lastschrift. Vorgabe aus dem Kontakt: Lastschrift, wenn er ein gültiges Mandat hat. Gilt für jede Rechnung, nicht nur für Serien (B-11).
- Mandat am Kontakt: Mandatsreferenz (höchstens 35 Zeichen, eindeutig über alle Kontakte), Datum der Unterschrift, zuletzt eingezogen am, freiwillig die IBAN des Kunden. Bei Serien ist das Datum aus „Sepa erteilt“ die Unterschrift, die Mandatsreferenz die Kd-Nr. (bis die Firma es anders sagt, B-11 Offen 2).
- Gläubiger-ID in den Firmendaten, geprüft auf Format und Prüfziffer. Ohne sie lässt sich keine Lastschrift wählen; die Vorschau und der Editor sagen, wo sie fehlt.
- Ein Mandat verfällt, wenn 36 Monate lang keine Lastschrift darauf eingezogen wurde (SEPA-Regelwerk für die Basislastschrift). „Zuletzt eingezogen“ setzt Kontorfreund beim Buchen einer Zahlung der Art Lastschrift, der Nutzer kann es auch eintragen. Liegen Unterschrift und letzter Einzug länger als 36 Monate zurück, schlägt Kontorfreund Überweisung vor und nennt den Grund; der Nutzer kann trotzdem Lastschrift wählen.
- Einzugsdatum ist die Fälligkeit: Rechnungsdatum plus Zahlungsziel. Die Rechnung dient als Vorabinformation; sie muss dem Kunden nach dem SEPA-Regelwerk 14 Kalendertage vor dem Einzug vorliegen, sofern nichts Kürzeres vereinbart ist. Bei weniger als 14 Tagen weist der Editor darauf hin. Skonto gibt es bei Lastschrift nicht, und der Hinweis auf Zahlungsverzug (§ 286 Abs. 3 BGB) entfällt.
- Zahlungshinweis: ein zweiter eigener Text in den Firmendaten für Lastschriften, neben dem für Überweisungen, mit den Platzhaltern aus B-6 und zusätzlich {mandat}, {glaeubiger} und {kundennummer}. Ohne eigenen Text gilt der feste Wortlaut „Der Betrag von {betrag} wird am {faellig} per SEPA-Lastschrift von Ihrem Konto eingezogen. Mandatsreferenz {mandat}, Gläubiger-ID {glaeubiger}.“ Eingefroren wird er beim Festschreiben wie der Hinweis für Überweisungen.
- Eine Lastschrift-Rechnung druckt weder GiroCode (M-2) noch die Bitte zu überweisen, damit niemand doppelt zahlt. Die Bankverbindung in der Fußzeile bleibt.
- E-Rechnung: Zahlart 59 (SEPA-Lastschrift) mit Mandatsreferenz (BT-89), Gläubiger-ID (BT-90) und, wenn hinterlegt, der IBAN des Kunden (BT-91). Die XRechnung verlangt bei Lastschrift die IBAN des Kunden; fehlt sie, nennt die Prüfung vor dem Festschreiben (B-5) den Fehler.
- Stornorechnung und Rechnungskorrektur behalten ihren eigenen Text (B-6); eine Erstattung läuft als Überweisung.
- Auskunft und Löschung (D-1) umfassen Mandat und IBAN. Export und Import der Adressen (M-5, M-6) haben Spalten dafür.
- Später, nicht Teil dieses Abschnitts: die Lastschriftdatei für die Bank (SEPA-XML), damit die Einzüge nicht von Hand ins Banking übertragen werden müssen.

Abnahme:

- KoSIT- und Mustang-Validator akzeptieren eine Lastschrift-Rechnung als ZUGFeRD ohne IBAN des Kunden und als XRechnung mit IBAN.
- Eine Lastschrift-Rechnung hat keinen GiroCode und keine Bitte zu überweisen.
- Ohne Gläubiger-ID lässt sich keine Lastschrift wählen.
- Ein Mandat, das älter als 36 Monate ist und keinen bekannten Einzug hat, führt zum Vorschlag Überweisung mit Grund. Nach dem Buchen einer Lastschrift-Zahlung gilt es wieder.

## Abnahme Phase 2

- Der KoSIT-Validator akzeptiert XRechnung und ZUGFeRD-XML für alle Testfälle: Regelbesteuerung, § 19, § 13b, Skonto, Rabatt, mehrere Steuersätze.
- Der Mustang-Validator akzeptiert jedes ZUGFeRD-PDF (prüft PDF/A-3 und eingebettete XML).
- Eine außerhalb des Programms veränderte Beleg-Datei wird bei der nächsten Prüfung gemeldet.
- Eine festgeschriebene Rechnung lässt sich weder über die Oberfläche noch über direkte Anfragen ändern.
- Auch bei gleichzeitigem Festschreiben durch zwei Benutzer entstehen keine doppelten Nummern und keine Lücken.
- Mit den Vorgaben des Briefkopfs ist ein Beleg pixelgleich mit dem vor Einführung der Einstellungen; ein Kopf ohne Logo und Angaben zieht den Text nicht ins Anschriftfeld.
