# Änderungen

## 0.34.0 – 07.11.2026

- Den Speicherort des Programms können Sie jetzt auf der ersten Seite des Installationsprogramms ändern. Vorgegeben bleibt `C:\Program Files\Kontorfreund`. Ihre Daten liegen davon unabhängig weiter im Benutzerordner.

## 0.33.0 – 07.11.2026

- Das Installationsprogramm sieht jetzt aus wie Kontorfreund selbst: links die Seitenleiste mit den Schritten, rechts der Inhalt, in den Farben und der Schrift des Programms, hell oder dunkel wie Ihr Windows. Statt mehrerer Seiten gibt es eine Startseite mit den Hinweisen zu Urheber und Lizenz und der Frage nach dem Desktop-Symbol, ein Klick auf „Installieren“ genügt. Die Adressen von Quellcode und Internetauftritt lassen sich anklicken.

## 0.32.0 – 07.11.2026

- Unter Einstellungen gibt es bei „Kontakt und Bank“ das neue Feld „Internetadresse“. Ist es ausgefüllt, steht die Adresse in der Fußzeile von Rechnungen, Angeboten, Auftragsbestätigungen und Mahnungen unter Telefon und E-Mail, auch im Auskunftsbrief nach der DSGVO. Schon festgeschriebene Belege bleiben unverändert.

## 0.31.5 – 07.11.2026

- Das Installationsprogramm nennt unter dem Link zum Quellcode jetzt auch die Internetadresse https://it-lsg-reimann.de.

## 0.31.4 – 07.11.2026

- Positionen reißen auf Rechnungen, Angeboten und Auftragsbestätigungen nicht mehr mitten im Text über zwei Seiten. Passt eine Position nicht mehr auf die Seite, steht sie ganz auf der nächsten. Ist sie höher als 6 cm, trennt die Seite nur zwischen zwei Zeilen der Beschreibung. Schon festgeschriebene Belege bleiben unverändert.

## 0.31.3 – 07.11.2026

- Der Abstand zwischen Gruß und Unterschrift ist kleiner und entspricht jetzt dem üblichen Absatzabstand im Beleg. Schon festgeschriebene Belege bleiben unverändert.

## 0.31.2 – 07.11.2026

- Steht Ihr Name im Text unter der Unterschrift, stand er am Ende von Rechnungen, Angeboten, Auftragsbestätigungen und Mahnungen zweimal. Jetzt fällt die Zeile im Gruß weg, auch bei schon gespeicherten Entwürfen. Schon festgeschriebene Belege bleiben unverändert.

## 0.31.1 – 07.11.2026

- Auf Rechnungen, Angeboten, Auftragsbestätigungen und Mahnungen berührte die Linie über dem Gesamtbetrag die Schrift. Jetzt steht ein kleiner Abstand dazwischen. Schon festgeschriebene Belege bleiben unverändert.

## 0.31.0 – 06.11.2026

- Unterschrift: Die Einstellungen haben den neuen Abschnitt „Unterschrift“. Dort laden Sie ein Bild Ihrer Unterschrift hoch (PNG, JPG oder SVG bis 1 MB) und tragen auf Wunsch einen Text darunter ein, etwa Ihren Namen und Ihre Funktion. Beides steht ab jetzt am Ende von Rechnungen, Angeboten, Auftragsbestätigungen und Mahnungen, nach Ihrem Schlusstext und auch schon in der Vorschau. Reicht der Platz auf der Seite nicht, rücken Schlusstext und Unterschrift gemeinsam auf die nächste Seite. Schon festgeschriebene Belege bleiben unverändert.

## 0.30.0 – 06.11.2026

- Entwürfe auf der Übersicht: Rechts steht jetzt der Abschnitt „Entwürfe“ mit allen noch nicht festgeschriebenen Rechnungen und allen noch nicht fertiggestellten Angeboten und Auftragsbestätigungen. Sie sehen Kunde, Belegart und wann Sie zuletzt daran gearbeitet haben, die zuletzt geänderten stehen oben, ein Klick öffnet den Entwurf. Gibt es keine Entwürfe, fehlt der Abschnitt.

## 0.29.0 – 06.11.2026

- Unter Windows installiert sich Kontorfreund jetzt nach `C:\Program Files\Kontorfreund` statt in den Benutzerordner. Dort sind die Programmdateien vor Veränderungen geschützt, und jedes Windows-Konto auf dem Rechner kann das Programm starten, jedes mit eigenen Daten.
- Installation und Updates brauchen dafür Administratorrechte: Windows fragt jedes Mal nach Ihrer Bestätigung. Kontorfreund selbst läuft weiter ohne diese Rechte.
- Ihre Daten bleiben unverändert in `%LOCALAPPDATA%\Kontorfreund`. Eine Installation im alten Ordner deinstallieren Sie vor dem Update; die Daten bleiben dabei erhalten.

## 0.28.1 – 06.11.2026

- Mehr Platz für die Leistung auf Rechnungen, Angeboten und Auftragsbestätigungen: Die Spalten Menge, Einzelpreis und Gesamt sind jetzt nur noch so breit, wie ihr Inhalt es braucht. Bei üblichen Beträgen wächst die Spalte „Leistung“ von 7 auf rund 9,5 cm, lange Beschreibungen brechen seltener um und der Beleg wird kürzer. Große Beträge bleiben in einer Zeile; die Leistung wird dann entsprechend schmaler. Schon festgeschriebene Belege bleiben unverändert.

## 0.28.0 – 03.11.2026

- Hilfe: Der Bereich „Hilfe“ in der Seitenleiste hat jetzt eine kurze Anleitung zu jedem Bereich, von den ersten Schritten über Adressen, Rechnungen, Angebote, Zahlungen und Mahnungen bis zu Datensicherung, Einstellungen und den Pflichten gegenüber Finanzamt und Datenschutz. Jede Anleitung erklärt Schritt für Schritt, welcher Knopf was tut, und verweist auf die passenden Seiten im Programm.
- Häufige Fragen auf der Seite „Hilfe“ zum Aufklappen, etwa wie Sie Kontorfreund beenden, wo Ihre Daten liegen, was bei einem Fehler in einer festgeschriebenen Rechnung zu tun ist, wie die Rechnungsnummer entsteht und was bei einem vergessenen Kennwort hilft.
- Die Suche oben (Strg K) findet auch die Anleitungen: Tippen Sie etwa „storn“ oder „Mahnung“.

## 0.27.1 – 03.11.2026

- Der Selbsttest des Installationspakets prüft jetzt auch die Datensicherung: Er legt in einem Wegwerf-Ordner eine eigene Datenbank mit einer Adresse und einem Beleg an, sichert sie verschlüsselt, löscht beides und stellt es wieder her. Das läuft bei jeder neuen Version auf frischen Rechnern mit Windows, macOS und Linux. Ihre Daten und Ihre Sicherungen fasst der Selbsttest nicht an.

## 0.27.0 – 03.11.2026

- Mehrere Anschriften je Adresse: Unter der Anschrift im Formular der Adresse fügen Sie mit „Weitere Anschrift“ beliebig viele hinzu, jede mit der Art Rechnung, Lieferung oder Sonstige und auf Wunsch einer Zusatzzeile wie „Buchhaltung“ oder „Lager Nord“. Den Ort trägt Kontorfreund auch dort zur PLZ ein. Die Anschrift oben bleibt die Standardanschrift.
- Neue Rechnungen gehen an die Rechnungsanschrift, wenn es eine gibt; Angebote und Auftragsbestätigungen an die Standardanschrift. Gibt es eine Lieferanschrift, ist sie auf allen dreien vorgewählt und steht im PDF unter dem Betreff, in der E-Rechnung als Lieferanschrift. Beides wählen Sie im Beleg unter „Anschrift“ und „Lieferanschrift“ um. Die Zusatzzeile steht im Anschriftfeld anstelle des Ansprechpartners.
- Aus einem Angebot oder einer Auftragsbestätigung übernimmt die Rechnung die Lieferanschrift. Stornorechnung, Rechnungskorrektur und Mahnung gehen an dieselbe Anschrift wie die Rechnung.
- Eine Anschrift, die auf einem festgeschriebenen oder fertigen Beleg steht, lässt sich nicht entfernen, nur ändern. Entfernen Sie eine, die nur ein Entwurf nutzt, nimmt er wieder die Standardanschrift.
- Weitere Anschriften stehen im Verlauf und in der Adressliste, im Export der Liste, in der Auskunft nach der DSGVO und im Gesamtexport (`anschriften.csv`). Das Änderungsprotokoll verzeichnet jede Änderung mit altem und neuem Stand.

## 0.26.0 – 03.11.2026

- Die Kundennummer lässt sich ändern, solange es zu der Adresse noch keinen Beleg gibt: im Formular der Adresse unter „Kundennummer“, als „K-0012“ oder einfach „12“. Bei einer neuen Adresse können Sie sie gleich selbst wählen; leer gelassen vergibt Kontorfreund wie bisher die nächste Nummer. Jede Nummer gibt es nur einmal.
- Gibt es schon eine Rechnung, ein Angebot, eine Auftragsbestätigung, eine Mahnung, einen Altbeleg oder eine Eingangsrechnung zu der Adresse, bleibt die Nummer fest: Sie steht auf diesen Belegen, und beim DATEV-Export mit eigenem Konto je Kunde ergibt sie das Debitorenkonto. Entwürfe zählen nicht.
- Das Änderungsprotokoll verzeichnet jede geänderte Kundennummer mit alter und neuer Nummer. Dateien, die schon an der Adresse liegen, bleiben im Ordner der alten Nummer und werden weiter gefunden. Die Verfahrensdokumentation sagt das; beim nächsten Herunterladen entsteht eine neue Fassung.

## 0.25.0 – 03.11.2026

- Spalten wählen: Mit „Spalten“ rechts über der Adressliste legen Sie fest, was die Liste neben Nummer und Name zeigt: Straße, PLZ, Ort, Land, Kategorien, Telefon, E-Mail, Website und USt-IdNr. „Wie vorgegeben“ stellt Ort, Kategorien und Telefon wieder her. Die Wahl gilt für Ihr Benutzerkonto, auf jedem Gerät. Nach der PLZ lässt sich wie nach dem Ort sortieren.
- Auf schmaleren Bildschirmen wie einem Tablet bleiben die gewählten Spalten stehen, auch das Telefon; ist die Tabelle zu breit, schieben Sie sie seitlich. Auf dem Handy zeigt die Liste wie bisher Nummer, Name und Kategorien.
- Behoben: War eine Tabelle breiter als der Bildschirm, ließ sich die ganze Seite seitlich verschieben statt nur die Tabelle.

## 0.24.0 – 03.11.2026

- Die Adressliste lässt sich sortieren: Ein Klick auf „Nr.“, „Name“ oder „Ort“ sortiert danach, ein zweiter dreht die Reihenfolge um; ein Pfeil am Spaltenkopf zeigt die Richtung. Umlaute stehen beim Grundbuchstaben, „Ärztehaus“ also bei A und nicht mehr hinter Z, und Groß- und Kleinschreibung zählen nicht. Adressen ohne Ort stehen am Ende. Der Export der Liste übernimmt die Reihenfolge.
- Neben der Kategorie filtert die Liste jetzt nach dem Ort („Alle Orte“). Verschiedene Schreibweisen wie „Überlingen“ und „überlingen“ gelten als ein Ort. Suche, Kategorie und Ort lassen sich kombinieren.
- Behoben: Der Export nach Excel und LibreOffice brach ab, wenn der Name der gewählten Kategorie oder des Orts einen Schrägstrich oder ein anderes in Blattnamen verbotenes Zeichen enthielt, etwa „Frankfurt/Main“.
- Behoben: Auf dem Handy hatten Adressen ohne Kategorie in der Liste unten eine leere Zeile.

## 0.23.0 – 03.11.2026

- Eigene Kategorien: Neben Kunde, Interessent und Lieferant legen Sie eigene an, etwa „Wartungsvertrag“ oder „Webdesign“, und eine Adresse kann mehrere davon haben. Sie wählen sie beim Bearbeiten der Adresse; eine neue tragen Sie dort direkt unter „Neue Kategorie“ ein. Jede Adresse behält ihre bisherige Kategorie.
- Auf der neuen Seite Adressen › Kategorien benennen Sie Kategorien um, löschen eigene und sehen, wie viele Adressen jede hat. Kunde, Interessent und Lieferant lassen sich umbenennen, aber nicht löschen.
- Die Adressliste filtert nach jeder Kategorie und zeigt alle Kategorien einer Adresse, auf dem Handy unter dem Namen.
- Der Import liest mehrere Kategorien je Zeile, getrennt durch Komma oder Semikolon, und legt unbekannte neu an; der Probelauf nennt sie vorher. Steht in der Datei keine, gilt die gewählte Kategorie oder „keine“.
- Export der Liste, Auskunft nach Art. 15 DSGVO, Gesamtexport (neue Tabelle `kategorien.csv`) und Datenpaket für die Betriebsprüfung enthalten alle Kategorien, und das Änderungsprotokoll verzeichnet Änderungen daran.

## 0.22.0 – 03.11.2026

- Mehrere Telefonnummern und E-Mail-Adressen je Adresse: Unter Telefon und E-Mail fügen Sie mit „Weitere Telefonnummer“ und „Weitere E-Mail-Adresse“ weitere hinzu, jeweils mit einer Bezeichnung wie „Mobil“, „Fax“ oder „Buchhaltung“, bis zu 20 je Adresse. Sie stehen in der Adressliste, auf der Seite der Adresse und im Export der Liste. Für Rechnungen und die XRechnung gilt weiter die Adresse im Feld „E-Mail“.
- Position: Bei Personen und beim Ansprechpartner einer Firma lässt sich die Position eintragen, etwa „Geschäftsführerin“. Bei einem Ansprechpartner steht dann „Geschäftsführerin bei …“ statt „Ansprechpartner bei …“, und die Firma nennt sie in ihrer Liste der Ansprechpartner.
- Die Suche in der Adressliste findet auch die weiteren E-Mail-Adressen, und die Warnung vor Dubletten beim Anlegen vergleicht sie mit. Hat eine Adresse nur eine weitere Telefonnummer, zeigt die Liste diese in der Spalte „Telefon“.
- Der Import erkennt Spalten wie „Mobil“, „Handy“, „Fax“ und „Position“ und übernimmt die weiteren Nummern und Adressen aus dem eigenen Export der Adressliste.
- Die Auskunft nach Art. 15 DSGVO und der Gesamtexport (neue Tabelle `telefon-email.csv`) enthalten die weiteren Nummern und Adressen, das Änderungsprotokoll verzeichnet Änderungen daran. Das Verzeichnis von Verarbeitungstätigkeiten nennt die Position; beim nächsten Herunterladen entsteht eine neue Fassung.

## 0.21.0 – 03.11.2026

- Ansprechpartner: Eine Person lässt sich einer Firma zuordnen (im Formular der Person unter „Ansprechpartner bei“). Die Firma zeigt ihre Ansprechpartner rechts auf ihrer Seite, mit Telefon und E-Mail; dort legen Sie mit „Ansprechpartner anlegen“ gleich einen neuen an. Bei der Person steht, zu welcher Firma sie gehört, in der Adressliste ebenso.
- Im Verlauf einer Firma stehen auch die Anrufe, Notizen und übrigen Einträge ihrer Ansprechpartner, jeweils mit deren Namen. Mit der Auswahl „ohne Ansprechpartner“ blenden Sie sie aus. „Nachfassen“ legt die Wiedervorlage bei der Person an, zu der der Eintrag gehört.
- Ansprechpartner ohne eigene Anschrift gelten in der Liste nicht mehr als „Anschrift unvollständig“.
- Die Auskunft nach Art. 15 DSGVO nennt bei einer Person die Firma, der Gesamtexport hat dafür die Spalte „Kundennummer der Firma“.

## 0.20.0 – 02.11.2026

- Adressen und Artikel lassen sich aus Excel (.xlsx), LibreOffice (.ods) oder einer CSV-Datei übernehmen: in der Liste der Adressen bzw. Artikel unter „Importieren“. Die Spalten erkennt Kontorfreund selbst bei seinen eigenen Exporten, bei Lexware Office und Google Kontakte und bei üblichen Namen wie „PLZ“ oder „E-Mail“; alles andere ordnen Sie per Auswahl zu.
- Vor der Übernahme zeigt ein Probelauf, was angelegt wird, welche Zeilen Fehler haben und welche Einträge es vermutlich schon gibt (gleiche E-Mail-Adresse oder gleicher Name am selben Ort, bei Artikeln gleiche Bezeichnung). Mögliche Dubletten überspringt Kontorfreund, wenn Sie nichts anderes wählen.
- Eine Zuordnung lässt sich unter einem Namen speichern; Dateien mit denselben Spalten erkennt Kontorfreund dann beim nächsten Mal selbst.
- Kunden- und Artikelnummern aus der Datei bleiben erhalten, wenn sie noch frei sind. Typische Eigenheiten von Excel gleicht der Import aus, etwa eine deutsche PLZ ohne die Null vorn, „Stk“ oder „h“ als Einheit und Preise wie „1.234,50 €“.
- Jede übernommene Adresse und jeder Artikel steht wie eine Eingabe von Hand im Änderungsprotokoll. Die Verfahrensdokumentation beschreibt den Import; beim nächsten Herunterladen entsteht eine neue Fassung.
- Der Quellcode liegt jetzt in der Organisation „Reimann IT & Web“ unter github.com/Reimann-IT-Web/kontorfreund; der Link in der Hilfe und im Installationsprogramm zeigt dorthin.

## 0.19.0 – 02.11.2026

- Sicherheitsprüfung nach OWASP ASVS 5.0, Stufe 2: Alle 253 Anforderungen sind durchgegangen und in `docs/sicherheit.md` festgehalten, mit Begründung, wo Kontorfreund bewusst abweicht. Daraus die folgenden Änderungen.
- Kennwörter: Kontorfreund lehnt jetzt auch Kennwörter ab, die aus Datenlecks bekannt sind (eine Liste mit 36 701 Einträgen im Programm, ohne Abfrage im Internet), und solche, die fast nur aus dem eigenen Namen, dem Firmennamen oder „Kontorfreund“ bestehen. Ihr bisheriges Kennwort bleibt gültig.
- Wer ein Konto vom Inhaber bekommt oder dessen Kennwort der Inhaber neu setzt, wählt bei der nächsten Anmeldung ein eigenes. Das gilt auch für den Prüfer.
- Unter „Mein Konto“ stehen die angemeldeten Geräte mit Browser und Uhrzeit; alle anderen lassen sich nach Eingabe des Kennworts abmelden. Der Inhaber kann einen Benutzer auf allen Geräten abmelden.
- Spätestens 12 Stunden nach der Anmeldung meldet Kontorfreund ab, auch wenn ständig gearbeitet wird; wie bisher auch nach 8 Stunden ohne Eingabe.
- Ein neues Kennwort oder eine geänderte Zwei-Faktor-Anmeldung meldet alle anderen Geräte ab. Die Zwei-Faktor-Anmeldung einzuschalten verlangt jetzt das Kennwort.
- Fünf falsche Kennwörter beim Bestätigen (Kennwort ändern, Zwei-Faktor-Anmeldung ausschalten, Geräte abmelden) sperren das Konto 15 Minuten, wie bei der Anmeldung.
- Das Protokoll verzeichnet jetzt auch Abmeldungen mit Grund, verweigerte Zugriffe, abgelehnte Formulare und das Ein- und Ausschalten der Zwei-Faktor-Anmeldung. Das Fehlerprotokoll schreibt zu jedem Eintrag Datum und Uhrzeit.
- Seiten und Belege bleiben nicht mehr im Zwischenspeicher des Browsers. Ein angehängtes Bild oder PDF zeigt Kontorfreund nur dann im Browser an, wenn der Inhalt zur Dateiendung passt, sonst gibt es die Datei als Download.
- Kleinere Härtungen: Anfragearten außer GET und POST lehnt das Programm ab, Telegram folgt keiner Umleitung, der Code zum Verbinden mit Telegram ist länger. Jedes Release enthält eine Stückliste aller Bibliotheken (SBOM).
- Die Verfahrensdokumentation beschreibt die neuen Regeln; beim nächsten Herunterladen entsteht eine neue Fassung.

## 0.18.0 – 02.11.2026

- Zugang für den Betriebsprüfer: Verlangt das Finanzamt bei einer Betriebsprüfung Zugriff auf Ihre Daten (§ 147 Abs. 6 AO), legen Sie unter Einstellungen › Benutzer › „Zugang für einen Betriebsprüfer“ ein Konto an, mit den Jahren der Prüfung und einem letzten Tag, höchstens ein Jahr voraus. Der Prüfer sieht nach der Anmeldung nur einen eigenen Bereich: Rechnungsausgangsbuch, Rechnungen mit Positionen, Zahlungen, Mahnungen, Eingangsrechnungen, Belege aus dem früheren Programm, die zugehörigen Adressen, das Änderungsprotokoll und die Verfahrensdokumentation, nur für diese Jahre. Er kann jede Tabelle durchsuchen und sortieren und die Belege öffnen, aber nichts ändern, nichts anlegen und keine anderen Bereiche aufrufen. Nach dem letzten Tag ist keine Anmeldung mehr möglich, auch eine offene Sitzung endet. Verlängern oder vorzeitig sperren können Sie den Zugang jederzeit; „So sieht es der Prüfer“ zeigt Ihnen vorher seine Ansicht.
- Die Verfahrensdokumentation beschreibt den Zugang für den Prüfer.

## 0.17.0 – 02.11.2026

- Dokumentation: Unter Einstellungen › Dokumentation erstellt Kontorfreund die Verfahrensdokumentation nach den GoBD, nach der das Finanzamt bei einer Betriebsprüfung fragt, und das Verzeichnis von Verarbeitungstätigkeiten nach Art. 30 DSGVO mit den technischen und organisatorischen Maßnahmen (Art. 32 DSGVO), beide als PDF. Was das Programm betrifft, schreibt Kontorfreund selbst und aus Ihren Einstellungen: wie Rechnungen entstehen, festgeschrieben, abgelegt, geprüft und gesichert werden, wer Zugang hat, welche Daten über Personen wofür gespeichert und wann sie gelöscht werden. Sie ergänzen ein paar Sätze zu Ihrem Betrieb, etwa wie Sie Kontoauszüge und Papierbelege aufbewahren, und kreuzen an, wie Rechner und Akten geschützt sind. Was noch fehlt, steht im Dokument als „Noch offen“.
- Jede Änderung ergibt beim Herunterladen eine neue Fassung mit Datum, Programmversion und den geänderten Abschnitten. Alle Fassungen bleiben in der Ablage, werden täglich mitgeprüft und gesichert und stehen im Gesamtexport.

## 0.16.0 – 02.11.2026

- Gesamtexport: Unter Datensicherung lädt „Gesamtexport herunterladen“ alle Daten und Belege in einer ZIP-Datei herunter, die sich ohne Kontorfreund öffnen lässt: je Tabelle eine CSV-Datei für Excel oder LibreOffice (Adressen, Artikel, Angebote, Auftragsbestätigungen und Rechnungen samt Positionen, Zahlungen, Mahnungen, Eingangsrechnungen, Altbelege, Verlauf, Dateien, Wiedervorlagen, Änderungsprotokoll und die eigenen Firmendaten), alle Belege und Dateien im Original und eine LIESMICH.txt, die erklärt, wie alles zusammenhängt. So bleiben Ihre Daten lesbar, auch wenn Sie einmal das Programm wechseln. Der Export ist nicht verschlüsselt; zum Wiederherstellen dient weiter die Datensicherung.

## 0.15.0 – 01.11.2026

- Aufbewahrungsfristen: Einmal im Jahr zeigt die Übersicht dem Inhaber, für wie viele Belege die Aufbewahrungsfrist abgelaufen ist (Rechnungen 8 Jahre, Angebote, Mahnungen und andere Geschäftsbriefe 6 Jahre, jeweils ab Ende des Jahres). Die neue Seite „Aufbewahrungsfristen“ unter Ablage listet sie nach Jahren; Sie wählen aus, was gelöscht wird, oder behalten alles. Gelöscht werden die Belege mit ihren Dateien und Zahlungen; im Änderungsprotokoll bleibt nur, wann wer etwas getan hat. Belege, auf die noch ein aufzubewahrender Beleg verweist, etwa eine spätere Mahnung oder Stornorechnung, bleiben. Gesperrte Adressen, deren Frist abgelaufen ist, lassen sich dort ebenfalls endgültig löschen. Ihre Entscheidung steht im Protokoll und gilt bis zum Jahresende.

## 0.14.0 – 01.11.2026

- Datenschutz: Jede Adresse hat für den Inhaber den neuen Knopf „Datenschutz“. Verlangt jemand Auskunft über seine Daten (Art. 15 DSGVO), lädt „Auskunft herunterladen“ eine ZIP-Datei herunter: ein Brief mit allen gespeicherten Angaben, Belegen, Zahlungen, Einträgen im Verlauf, Dateien, Wiedervorlagen und früheren Angaben samt den Informationen, die die DSGVO verlangt, dazu dieselben Daten maschinenlesbar (auskunft.json) und Kopien der Belege und Dateien.
- Verlangt jemand die Löschung (Art. 17 DSGVO) und gibt es zu ihm keine Belege, die noch aufbewahrt werden müssen, löscht „Endgültig löschen“ die Adresse mit Verlauf, Dateien, Wiedervorlagen und Entwürfen, auch Belege, deren Aufbewahrungsfrist abgelaufen ist. Im Änderungsprotokoll bleibt nur, wann wer etwas getan hat; Namen und Werte werden geschwärzt.
- Müssen Belege noch aufbewahrt werden (Rechnungen 8 Jahre, Angebote und Mahnungen 6 Jahre, jeweils ab Ende des Jahres), sperrt „Adresse sperren“ sie bis dahin (Art. 18 DSGVO): Sie erscheint in keiner Liste und Suche mehr, niemand kann sie ändern, und nur der Inhaber sieht sie unter Adressen bei „gesperrt“. Die Seite zeigt, welcher Beleg bis wann aufbewahrt werden muss.

## 0.13.0 – 01.11.2026

- Betriebsprüfung: Unter Auswertungen gibt es für den Inhaber den neuen Reiter „Betriebsprüfung“. Er erstellt das Datenpaket, das ein Prüfer des Finanzamts nach § 147 Abs. 6 AO verlangen kann: eine ZIP-Datei nach dem „Beschreibungsstandard für die Datenträgerüberlassung“ der Finanzverwaltung. Darin stehen die Beschreibung index.xml mit der zugehörigen Datei gdpdu-01-08-2002.dtd, Tabellen zu Rechnungsausgang, Rechnungspositionen, Zahlungen, Mahnungen, Eingangsrechnungen, Altbelegen und den beteiligten Adressen sowie alle Belege des Zeitraums als PDF und XML mit ihren Prüfsummen. Die Prüfsoftware der Finanzverwaltung liest das Paket ohne weitere Erklärung ein. Wählen Sie Jahr, Quartal oder Monat; für eine Prüfung über mehrere Jahre laden Sie je Jahr ein Paket herunter.

## 0.12.1 – 01.11.2026

- Behoben: Die tägliche Prüfung der Ablage konnte mit „database is locked“ scheitern, wenn Sie gerade arbeiteten. Sie hielt die Datenbank gesperrt, während sie die Prüfsummen aller Belege rechnete; schrieb in dieser Zeit eine Seite etwas, ließ sich das Ergebnis der Prüfung nicht speichern. Jetzt sperrt sie nur noch für das Speichern. Außerdem warten gleichzeitige Schreibzugriffe bis zu 20 Sekunden aufeinander, statt abzubrechen. Ihre Daten waren davon nicht betroffen; es fehlte nur das Ergebnis der betroffenen Prüfung.

## 0.12.0 – 01.11.2026

- Dateien an Adressen und Einträgen: Auf der Seite einer Adresse (Verlauf und Notizen) gibt es den Bereich „Dateien“. Verträge, Fotos, PDFs oder andere Dateien wählen Sie dort aus oder ziehen sie einfach hinein, auch mehrere auf einmal. An einen Anruf, eine E-Mail, eine Notiz oder einen Termin hängen Sie Dateien gleich beim Eintragen oder später auf der Seite des Eintrags. PDF und Bilder öffnen sich im Browser, alle anderen Dateien werden heruntergeladen; eine HTML-Datei wird nie im Browser ausgeführt. Höchstens 50 MB je Datei.
- Gelöschte Dateien holen Sie mit „Rückgängig“ sofort zurück. Endgültig entfernt werden sie nach 30 Tagen. Hochladen, Löschen und Zurückholen stehen im Protokoll.
- Die Dateien liegen im Datenordner unter „archiv/dateien“, je Adresse ein Ordner mit der Kundennummer, und sind damit in jeder Datensicherung enthalten.

## 0.11.0 – 01.11.2026

- Adressen und offene Posten herunterladen: Unter beiden Listen steht „Herunterladen als Excel, LibreOffice oder CSV“. Heruntergeladen wird genau die Liste, die Sie gerade sehen, also mit Suche, Kategorie, Archiv, Ansicht (offen, überfällig, bezahlt, alle) und Kunde. Die Adressen enthalten alle Felder bis zur Notiz, die offenen Posten Fälligkeit, Betrag, Bezahltes, Offenes, Stand und die letzte Mahnung.
- In CSV-Dateien bleiben Telefonnummern wie „+49 6131 12345“ unverändert. Bisher setzte Kontorfreund jedem Text, der mit Plus oder Minus beginnt, ein Hochkomma voran, damit Excel ihn nicht als Formel ausführt. Das gilt jetzt nur noch für Text, der mehr als Ziffern und Rechenzeichen enthält.

## 0.10.0 – 01.11.2026

- Artikel beim Tippen auswählen: In Rechnungen, Angeboten und Auftragsbestätigungen bietet das Feld Bezeichnung jeder Position Ihre Artikel mit Preis und Einheit an, sobald Sie zu tippen beginnen. Wählen Sie einen aus, übernimmt die Position Beschreibung, Einheit und Preis. Ein Preis, den Sie danach von Hand ändern, bleibt stehen. Das Menü „Artikel einfügen“ gibt es weiterhin.

## 0.9.0 – 01.11.2026

- Originale zurückholen: Findet die Prüfung der Ablage eine fehlende oder veränderte Datei, holt „Originale zurückholen“ (Ablage, nur für den Inhaber) das Original aus den Datensicherungen zurück, ohne die übrigen Daten anzufassen. Kontorfreund nimmt eine Datei nur, wenn ihre Prüfsumme stimmt, beginnt bei der neuesten Sicherung und legt eine veränderte Fassung in den Ordner „abweichungen“, statt sie zu löschen. Jede zurückgeholte Datei steht im Protokoll.
- Ort zur Postleitzahl: In Adressen und Firmendaten trägt Kontorfreund nach einer deutschen PLZ den Ort ein, solange Sie ihn nicht von Hand geändert haben. Teilen sich mehrere Gemeinden eine PLZ, stehen sie im Feld Ort zur Auswahl. Die Daten (aus OpenStreetMap) sind im Programm enthalten; es geht nichts ins Internet.

## 0.8.0 – 01.11.2026

- Tägliche Prüfung der Ablage: Einmal am Tag vergleicht Kontorfreund jede abgelegte Datei – Rechnungen samt XML, Angebote, Auftragsbestätigungen, Mahnungen, Eingangsrechnungen und die Belege aus dem bisherigen Programm – mit der Prüfsumme, die beim Ablegen gespeichert wurde. Fehlt eine Datei oder wurde sie außerhalb des Programms verändert, steht das auf der Übersicht, an der Ablage in der Seitenleiste und auf der Seite Ablage mit dem Hinweis, wie Sie das Original zurückbekommen. Jede neue Abweichung kommt ins Protokoll und, wenn eingerichtet, per Telegram. Unter Ablage lässt sich auch sofort prüfen.
- Die Prüfung läuft nach dem ersten Seitenaufruf des Tages im Hintergrund und, wenn Kontorfreund mit eingeschalteten Benachrichtigungen nur im Hintergrund läuft, auch ohne dass jemand eine Seite öffnet.

## 0.7.0 – 01.11.2026

- Auftragsbestätigungen: Sagt ein Kunde zu, machen Sie aus dem Angebot mit „Auftrag bestätigen“ eine Auftragsbestätigung mit denselben Positionen, oder Sie schreiben sie ohne Angebot neu (Angebote & Rechnungen → Auftragsbestätigungen). Auf Wunsch mit dem Zeitraum der Ausführung. Beim Fertigstellen bekommt sie eine Nummer aus einem eigenen Nummernkreis und wird als PDF abgelegt; danach lässt sie sich per E-Mail senden, kopieren und mit einem Klick in einen Rechnungsentwurf übernehmen, der Ausführung als Leistungszeitraum mitnimmt. Jeder Schritt lässt sich weiterhin überspringen.
- Auftragsbestätigungen stehen im Verlauf der Adresse und im Änderungsprotokoll.

## 0.6.0 – 01.11.2026

- Benachrichtigungen kommen jetzt kostenlos über Telegram statt per SMS. Unter Einstellungen → Benachrichtigungen legen Sie in drei Schritten einen eigenen Telegram-Bot an und verbinden ihn per QR-Code. Inhalt und Zeitpunkte wie bisher; Namen von Kunden und Lieferanten gehen nicht an Telegram, nur Titel der Wiedervorlagen, Rechnungsnummern und Beträge.
- Die SMS über seven.io sind entfernt: Kontorfreund unterstützt keine Dienste, die Geld kosten.

## 0.5.0 – 01.11.2026

- Mehrere Firmen: Unter Einstellungen → Firmen legen Sie eine weitere Firma an und wechseln zwischen ihnen, auch schon auf der Anmeldeseite. Jede Firma hat eigene Adressen, Rechnungen, Nummernkreise, Benutzer und Datensicherung in einem eigenen Ordner; die erste bleibt, wo sie ist. Beim Wechseln startet Kontorfreund in wenigen Sekunden neu, angemeldet bleibt man in jeder Firma. Sicherungen weiterer Firmen tragen die Firma im Dateinamen, damit sich an einem gemeinsamen Speicherort nichts verwechselt.
- Benachrichtigungen per SMS (Einstellungen → Benachrichtigungen, über seven.io): morgens eine Übersicht mit den Wiedervorlagen des Tages, nicht bezahlten Rechnungen und bald fälligen Eingangsrechnungen, vor Terminen eine Erinnerung. Mit Testnachricht. Steht nichts an, kommt keine SMS.
- Auf Wunsch startet Kontorfreund beim Anmelden an Windows im Hintergrund, damit SMS und die tägliche Sicherung auch ohne Doppelklick kommen.

## 0.4.0 – 01.11.2026

- Wiedervorlagen: Erinnerungen mit Fälligkeit und auf Wunsch Uhrzeit, zu einer Adresse, einem Angebot oder einer Rechnung, mit zuständigem Mitarbeiter. Die Übersicht zeigt fällige und die der nächsten sieben Tage, die Seitenleiste zählt die fälligen. Direkt aus jeder Liste auf morgen, um eine Woche oder einen Monat verschieben oder erledigen; erledigt mit einer Notiz zum Ergebnis.
- Verlauf je Adresse („Verlauf und Notizen“ in der Adressliste): Anrufe, E-Mails, Termine und Notizen in Sekunden eintragen; dazu stehen Angebote, Rechnungen, Zahlungen, Mahnungen, erledigte Wiedervorlagen, Eingangsrechnungen und die Belege aus dem bisherigen Programm von selbst in der Zeitleiste, filterbar nach Art. Aus jedem Eintrag lässt sich mit „Nachfassen“ eine Wiedervorlage anlegen.
- Auf den Seiten von Angeboten und Rechnungen gibt es einen Knopf „Wiedervorlage“.

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
