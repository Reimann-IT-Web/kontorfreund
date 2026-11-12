# 04 Geld (Phase 3)

Entwurf – wird vor Beginn von Phase 3 verfeinert und erneut freigegeben.

## M-1 Offene Posten

- Jede festgeschriebene Rechnung ist ein offener Posten, bis sie vollständig bezahlt ist.
- Fälligkeit = Rechnungsdatum + Zahlungsziel, danach Status „überfällig“.
- Übersicht nach Fälligkeit, Kunde und Betrag mit Summen offener und überfälliger Beträge; Kontoauszug je Kunde.

## M-2 Zahlungen

- Zahlung erfassen: Datum, Betrag, Art (Überweisung, bar, Lastschrift, sonstige), Notiz.
- Teilzahlungen; Skonto innerhalb der Frist wird automatisch berechnet; Restbeträge mit Grund ausbuchen.
- GiroCode (EPC-QR nach EPC069-12) auf jeder Rechnung, mit Betrag und Rechnungsnummer als Verwendungszweck.

## M-3 Mahnwesen

- Stufen: Zahlungserinnerung, 1. Mahnung, 2. Mahnung. Abstände und Texte einstellbar.
- Vorschlagsliste fälliger Mahnungen. Mahnung als PDF und per E-Mail, mit Eintrag in der Kontakthistorie.
- Sind Benachrichtigungen über Telegram eingerichtet, nennt die Tagesübersicht jede Rechnung, für die eine Stufe fällig geworden ist, einmal je Stufe: Rechnungsnummer, offener Betrag und Stufe, ohne Namen des Kunden. Erstellt und verschickt wird das Schreiben nicht von selbst, sondern erst, wenn der Nutzer den Zahlungseingang geprüft hat.
- Verzugszinsen nach § 288 BGB: gegenüber Verbrauchern 5, gegenüber Unternehmen 9 Prozentpunkte über dem Basiszinssatz; bei Unternehmen zusätzlich 40 € Pauschale (§ 288 Abs. 5 BGB). Je Stufe einstellbar, ob die Pauschale bei Unternehmen vorgeschlagen wird; im einzelnen Schreiben lässt sie sich abwählen, Verbrauchern wird sie nie berechnet. Der Basiszinssatz wird mit Gültigkeitsdatum gepflegt.
- Mahngebühren sind einstellbar. Das Programm weist darauf hin, dass nur tatsächliche Kosten ersatzfähig sind und die Mahnung, die den Verzug erst auslöst, nichts kosten darf.
- Rechnungen an Verbraucher enthalten auf Wunsch den Hinweis nach § 286 Abs. 3 BGB (Verzug 30 Tage nach Zugang).

## M-4 DATEV-Export

- Export eines Zeitraums im DATEV-Format (Buchungsstapel, CSV) nach der öffentlichen Formatbeschreibung von DATEV.
- Kontenrahmen SKR03 oder SKR04. Erlöskonten je Steuerfall einstellbar; die Vorbelegung bestätigt ein Steuerberater. Steuerfreie Leistungen (B-4) sind mit „Steuerfreie Umsätze § 4 Nr. 8 ff. UStG“ vorbelegt, SKR03 8100 und SKR04 4100.
- Debitorenkonto je Kunde oder ein Sammelkonto.
- Optional die Rechnungs-PDFs als ZIP dazu.

## M-5 Auswertungen und Exporte

- Rechnungsausgangsbuch je Zeitraum.
- Kontakte, offene Posten und Rechnungsausgangsbuch als CSV, XLSX und ODS.

## M-6 Import

- Kontakte und Artikel aus CSV, XLSX und ODS.
- Vorschau, Feldzuordnung per Auswahl, Dublettenprüfung und ein Probelauf mit Bericht vor dem eigentlichen Import.
- Gespeicherte Zuordnungen, darunter Vorlagen für die Exporte verbreiteter Altprogramme.

## M-7 E-Rechnungen empfangen

- XRechnung (UBL und CII) und ZUGFeRD/Factur-X hochladen.
- Lesbare Darstellung im Programm, Zuordnung zum Lieferanten.
- Die Originaldatei wird unverändert mit Prüfsumme aufbewahrt (GoBD).

## Abnahme Phase 3

- Ein Steuerberater liest den DATEV-Export einer Testperiode fehlerfrei ein.
- Ein echter Excel-Export aus einem Altprogramm wird vollständig importiert; der Bericht zeigt keine Fehler.
- Die Beispielrechnungen aus der offiziellen XRechnung-Testsuite werden korrekt angezeigt.
