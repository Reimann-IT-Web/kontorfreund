# Sicherheit nach OWASP ASVS, Stufe 2

Kontorfreund soll Stufe 2 des Application Security Verification Standard erfüllen (Spezifikation 01, Abnahme Phase 4). Dieses Dokument enthält die Sicherheitsentscheidungen, die der Standard schriftlich verlangt, und die Prüfliste aller Anforderungen der Stufen 1 und 2.

- Grundlage: [OWASP ASVS 5.0.0](https://github.com/OWASP/ASVS/tree/v5.0.0_release/5.0) (Mai 2025), CC BY-SA 4.0. Die Anforderungen stehen hier nur mit Nummer und einem eigenen Stichwort, den Wortlaut enthält der Standard.
- Geprüft: Version 0.19.0 am 02.11.2026, der ganze Quellcode.
- Nach jeder größeren Änderung ist diese Liste nachzuführen. Für den Netzwerkbetrieb (Spezifikation D-3) wird sie vor der Freigabe erneut durchgegangen.

## Einsatz und Geltungsbereich

Kontorfreund läuft als Einzelplatz-Programm. Der Server hört nur auf `127.0.0.1` (`kontorfreund.py`), die Daten liegen im Benutzerordner des Anwenders.

Das Programm schützt vor:

- fremden Webseiten im selben Browser (CSRF, Einbetten, Skripte von außen),
- schädlichen Dateien (E-Rechnungen, Anhänge, Logos, Sicherungen),
- Benutzern mit weniger Rechten (Mitarbeiter, Prüfer),
- jemandem am Rechner, der das Kennwort nicht kennt,
- anderen Programmen auf dem Rechner, die nur über HTTP zugreifen.

Wer mit dem Windows-Konto des Anwenders arbeitet, kann den Datenordner lesen. Davor schützen nur die Anmeldung am Betriebssystem, die Bildschirmsperre und eine verschlüsselte Festplatte. Diese Maßnahmen fragt die Verfahrensdokumentation als TOM ab.

Ein Netzwerkbetrieb (D-3) ist noch nicht freigegeben. Punkte mit dem Ergebnis „D-3“ entfallen am Einzelplatz und sind vor der Freigabe des Netzwerkbetriebs zu erfüllen.

## Eingaben (2.1.1 bis 2.1.3)

Maßgeblich sind Modelle und Formulare: Typ, Höchstlänge, Pflichtfeld, erlaubte Werte, Formate wie E-Mail-Adresse, Datum, Betrag (`Decimal`) und Leitweg-ID. Die Bedeutung der Felder beschreibt `docs/spec/`. Parameter in Adressen gelten nur aus einer festen Auswahl, sonst die Vorgabe.

Zusammenhänge, die das Programm prüft:

- Eine Rechnung lässt sich erst festschreiben, wenn die Pflichtangaben der Firma vollständig sind (§ 14 Abs. 4 UStG).
- Festgeschriebene Belege ändert niemand mehr; geändert wird über Storno und Korrektur.
- Beim Prüfungszeitraum liegt das erste Jahr nicht nach dem letzten; der Zugang endet frühestens heute und spätestens in einem Jahr.
- Ein neues Kennwort unterscheidet sich vom bisherigen.
- Importierte Adressen und Artikel durchlaufen dieselben Formulare wie Eingaben von Hand.

Grenzen je Benutzer:

- 5 Fehlversuche, dann 15 Minuten Sperre,
- 5 Minuten zwischen Kennwort und Code,
- Prüfer-Zugang höchstens ein Jahr am Stück.

Grenzen für alle:

- Dateigrößen siehe „Dateien“,
- Import höchstens 10.000 Zeilen und 100 Spalten,
- höchstens 20 weitere Telefonnummern und E-Mail-Adressen je Adresse,
- höchstens 100 Kategorien,
- eine Sicherung zur Zeit,
- Warnung vor den Umsatzgrenzen nach § 19 UStG.

## Dateien (5.1.1)

| Funktion | Erlaubt | Größe | Prüfung | Ausgabe |
|---|---|---|---|---|
| Dateien an Adressen und Vorgängen | jede Art | 50 MB (`APP_DATEI_MB`) | Name bereinigt, Zufallsvorsatz; bei PDF und Bildern muss der Dateianfang zur Endung passen | PDF und Bilder im Browser, alles andere als Download mit `sandbox` |
| E-Rechnungen | XML (UBL, CII), PDF mit eingebetteter XML | 20 MB | ohne Dokumenttyp-Definition, bekanntes Wurzelelement, PDF mit pypdf | PDF im Browser, XML als Download |
| Tabellen importieren (Adressen, Artikel) | CSV, XLSX, ODS | 10 MB, entpackt 100 MB | ohne Dokumenttyp-Definition in jeder XML des Archivs, bekannter Inhalt (Excel oder LibreOffice), jede Zeile wie eine Eingabe im Formular | – |
| Logo | SVG, PNG, JPG | 1 MB | Dateianfang, Typst muss es lesen können | im PDF; in den Einstellungen als `<img>` |
| Sicherung einlesen | `.sicherung` | keine Grenze | Kennung, Entschlüsselung (AES-GCM), Prüfsummen, `PRAGMA integrity_check`, Pfade | – |

Eine schädliche oder unlesbare E-Rechnung lehnt das Programm mit einer Meldung ab und legt nichts ab. Anhänge öffnet es nie; es gibt sie nur zurück. Eine Tabelle zum Import legt es nicht ab: Ihre Zellen stehen bis zur Übernahme oder zum Abbruch in der Datenbank, sichtbar nur für den, der sie hochgeladen hat; was länger als einen Tag liegen bleibt, löscht das nächste Hochladen. Den Virenschutz übernimmt das Betriebssystem (Microsoft Defender unter Windows).

## Anmeldung (6.1.1 bis 6.1.3)

Es gibt zwei Wege:

1. **Im Browser:** E-Mail-Adresse und Kennwort, bei eingeschalteter Zwei-Faktor-Anmeldung danach ein Code aus einer Authenticator-App (TOTP nach RFC 6238), innerhalb von 5 Minuten.
2. **Befehle am Rechner:** `Kontorfreund changepassword <E-Mail>` setzt ein Kennwort, `Kontorfreund entsperren <E-Mail> [--ohne-zwei-faktor]` hebt eine Sperre und auf Wunsch die Zwei-Faktor-Anmeldung auf. Diese Befehle kann nur ausführen, wer mit dem Windows-Konto arbeitet und damit ohnehin an den Datenordner kommt.

Weitere Wege gibt es nicht: keine Schnittstelle, keinen Django-Admin und kein „Kennwort vergessen“ per E-Mail.

**Brute force:** Je Konto führen 5 Fehlversuche zu 15 Minuten Sperre. Das gilt für das Kennwort, für den Code und für jede Bestätigung mit dem Kennwort, etwa beim Ausschalten der Zwei-Faktor-Anmeldung. Wer beim Bestätigen gesperrt wird, ist abgemeldet.

Böswilliges Aussperren dauert höchstens 15 Minuten je fünf Versuche. Die Sperre hebt sich von selbst auf, der Inhaber kann sie unter Benutzer aufheben, für ihn selbst gibt es den Befehl `entsperren`. Unbekannte E-Mail-Adressen sperren nichts, stehen aber im Protokoll. Eine Sperre nach IP-Adresse gibt es nicht, am Einzelplatz ist sie immer `127.0.0.1`.

**Kennwortregeln** (`konten/kennwort.py`): mindestens 12 Zeichen, beliebige Zeichen, kein Ablauf. Abgelehnt werden:

- die 36 701 Kennwörter ab 12 Zeichen aus `konten/daten/kennwoerter.txt`; sie stammen aus Datenlecks, gesammelt von SecLists, MIT-Lizenz,
- Djangos 20 000 häufigste Kennwörter und eine deutsche Liste, auch mit Ziffern und Zeichen dazwischen oder mehrfach wiederholt,
- Kennwörter, die ohne die Kontextwörter weniger als vier Buchstaben behalten.

**Kontextwörter (6.1.2):**

- fest: kontorfreund, kontor, inhaber, mitarbeiter, pruefer, prüfer, betriebspruefung, betriebsprüfung, finanzamt, rechnung, rechnungen,
- dazu jedes Wort ab vier Buchstaben aus Firmenname, Marke und Inhaber (Firmendaten),
- dazu jedes Wort ab vier Buchstaben aus Name und E-Mail-Adresse des Benutzers.

**Erstes Kennwort:** Der Inhaber vergibt es beim Anlegen und beim Neusetzen. Bei der nächsten Anmeldung muss der Benutzer ein eigenes wählen (`konten.rechte.eigenes_kennwort`). Für Prüfer gilt das auch.

## Sitzungen (7.1.1 und 7.1.2)

- Ohne Anfrage endet eine Sitzung nach 8 Stunden (`APP_ABMELDEN_NACH_STUNDEN`).
- Spätestens 12 Stunden nach der Anmeldung endet sie immer (`konten.sitzungen.HOECHSTENS`).
- Ein neues Kennwort oder eine geänderte Zwei-Faktor-Anmeldung beendet alle übrigen Sitzungen des Benutzers.
- Sperrt der Inhaber den Zugang eines Kontos oder läuft ein Prüfer-Zugang ab, enden alle Sitzungen dieses Kontos.

**Abweichung von NIST SP 800-63B-4:** Mit zweitem Faktor (AAL2) sieht NIST eine erneute Anmeldung nach höchstens 24 Stunden und nach höchstens einer Stunde ohne Aktivität vor. Kontorfreund nimmt 12 Stunden und 8 Stunden ohne Anfrage.

Begründung: Das Programm läuft am eigenen Arbeitsplatz und soll einen Arbeitstag ohne neue Anmeldung erlauben. Den unbeaufsichtigten Rechner schützt die Bildschirmsperre des Betriebssystems, die die Verfahrensdokumentation als TOM abfragt. Ohne zweiten Faktor (AAL1, höchstens 30 Tage) liegen beide Werte innerhalb der Empfehlung. Im Netzwerkbetrieb sind kürzere Werte einzustellen (D-3).

**Gleichzeitige Sitzungen:** Ihre Zahl ist nicht begrenzt. Jede steht unter „Mein Konto › Angemeldete Geräte“ mit Browser, Beginn und letzter Aktivität. Dort beendet der Benutzer nach Eingabe seines Kennworts alle anderen. Der Inhaber beendet unter Benutzer alle Sitzungen eines Benutzers.

## Rechte (8.1.1 und 8.1.2)

| Wer | Darf |
|---|---|
| ohne Anmeldung | anmelden; das erste Konto einrichten, solange es keins gibt; die Namen der Firmen sehen und eine öffnen (im Netzwerk nur angemeldet) |
| Mitarbeiter | Adressen mit Verlauf und Dateien, Wiedervorlagen, Angebote, Auftragsbestätigungen, Rechnungen, offene Posten, Artikel, Import von Adressen und Artikeln, Eingangsrechnungen, Ablage und Auswertungen; das eigene Konto |
| Inhaber | alles; nur er: Einstellungen, Firmen anlegen und entfernen, Benutzer, Datensicherung und Gesamtexport, Datenschutz je Adresse, Aufbewahrungsfristen, DATEV-Einstellungen, Datenpaket für die Betriebsprüfung, Benachrichtigungen, Mahnwesen-Einstellungen, Protokoll, Dokumentation |
| Prüfer | nur `/datenzugriff/`, nur lesen, nur die Jahre der Prüfung, nur Belege aus diesen Tabellen, nur bis `zugang_bis`; das eigene Kennwort ändern |

Innerhalb einer Firma sehen alle Rollen außer Prüfern alle Geschäftsdaten. Das ist gewollt, weil in einem kleinen Betrieb jeder jeden Vorgang bearbeiten können soll.

Felder:

- Festgeschriebene Belege ändert niemand.
- Gesperrte Adressen (Art. 18 DSGVO) sieht nur der Inhaber, und auch er ändert sie nicht.
- Technische Felder lassen sich über kein Formular ändern: Nummern, Status, Prüfsummen, Zeitpunkte, Zwei-Faktor-Geheimnis, Sperren. Nur der Import übernimmt die Nummer einer neuen Adresse oder eines neuen Artikels aus der Datei, wenn sie frei ist.
- Die Rolle ändert nur der Inhaber, nicht am eigenen Konto und nie zum oder vom Prüfer.
- SMTP-Kennwort und Bot-Schlüssel schickt das Programm nie an den Browser zurück.

## Kryptografie (11.1.1 und 11.1.2)

| Zweck | Verfahren | Schlüssel und Werte | Ort |
|---|---|---|---|
| Kennwörter der Benutzer | Argon2id | 2 Durchläufe, 100 MiB, 8 Threads, Salz je Kennwort | Datenbank |
| Sitzungen, CSRF, Meldungen | HMAC-SHA256 (Django) | `SECRET_KEY`, 50 Zeichen aus `secrets` (rund 300 Bit), je Firma eigener | `<Daten>/secret_key`, nur für den eigenen Benutzer lesbar |
| Sicherungen | scrypt (N = 2^17, r = 8, p = 1), dann AES-256-GCM in Blöcken zu 1 MiB | Schlüssel aus dem Kennwort der Sicherung, Salz zufällig | abgeleiteter Schlüssel in `<Daten>/datensicherung.json`, nie in einer Sicherung |
| Zwei-Faktor-Anmeldung | TOTP, HMAC-SHA1 (RFC 6238) | 160-Bit-Geheimnis je Benutzer | Datenbank |
| Belege, Fassungen, Inhalt der Sicherung | SHA-256 | – | Datenbank, Inhaltsverzeichnis der Sicherung |
| Zufall | `secrets` (CSPRNG des Betriebssystems) | – | – |
| Verbindungen nach außen | TLS 1.2 oder neuer, Zertifikat geprüft | Zertifikate des Betriebssystems | Telegram, SMTP |

Umgang mit den Schlüsseln:

- **`SECRET_KEY`** entsteht beim ersten Start und steht nie in Repo oder Paket. Löscht man die Datei, entsteht beim nächsten Start ein neuer; dann sind alle abgemeldet.
- **Kennwort der Sicherung:** Der Inhaber wählt es und kann es ändern; neue Sicherungen nehmen dann das neue. Ohne Kennwort ist keine Wiederherstellung möglich, das sagt das Programm beim Einrichten.
- **Zwei-Faktor-Geheimnis:** Es entsteht beim Einrichten und erscheint dabei einmal als QR-Code. Beim Ausschalten oder Zurücksetzen wird es gelöscht.
- **Keine Weitergabe:** Kein Schlüssel verlässt den Rechner, außer in der verschlüsselten Sicherung.

## Verbindungen (13.1.1)

- Browser und Server: HTTP über `127.0.0.1:8765`, nur auf diesem Rechner.
- Telegram Bot API (`api.telegram.org`, HTTPS): nur wenn der Inhaber einen Bot einrichtet. Der Rechner steht fest im Code; Umleitungen gelten als Fehler.
- SMTP-Server: nur wenn der Inhaber einen einträgt, für den Versand von Rechnungen; nur mit STARTTLS oder SSL/TLS.
- Zweiter Speicherort für Sicherungen: ein Ordner, den der Inhaber wählt.
- Startprogramm und Server: Prozesse auf demselben Rechner, verbunden über Umgebungsvariablen und den Rückgabewert.

Es gibt keine Telemetrie und keine Update-Prüfung. Schriften, Skripte, Bilder und Postleitzahlen liegen im Programm.

## Schutzbedürftige Daten (14.1.1 und 14.1.2)

| Stufe | Daten | Anforderungen |
|---|---|---|
| Geheim | Kennwörter (nur als Hash), Zwei-Faktor-Geheimnisse, `SECRET_KEY`, Schlüssel der Sicherung, SMTP-Kennwort, Telegram-Bot-Schlüssel | nie im Protokoll, nie in Exporten, nie zurück an den Browser (das Zwei-Faktor-Geheimnis einmal beim Einrichten); Kennwörter nur als Argon2-Hash |
| Vertraulich | Adressen, Belege, Zahlungen, Notizen, Dateien, Wiedervorlagen, Protokoll | nur angemeldet und nach Rolle; nicht im Cache des Browsers; in Sicherungen verschlüsselt; Belege mit Prüfsumme und unveränderbar; Aufbewahrung nach § 147 AO, Löschen und Sperren nach DSGVO (D-1); Änderungen im Protokoll |
| Öffentlich | Programm, statische Dateien | – |

Die Datenbank selbst ist nicht verschlüsselt. Das ist begründet: Am Einzelplatz schützt die Festplattenverschlüsselung des Betriebssystems, etwa BitLocker. Die Verfahrensdokumentation fragt sie als TOM ab.

## Bibliotheken (15.1.1 und 15.1.2)

- **Bestand:** `uv.lock` nennt jede Bibliothek mit Version und Hash; jedes Release enthält zusätzlich eine SBOM im Format CycloneDX.
- **Bezugsquellen:** Bibliotheken nur von PyPI. GitHub Actions nur von GitHub und Astral, bewusst nach Version statt nach Hash.
- **Kritische oder hohe Lücke** (`pip-audit` hält bei jedem Push die CI an): neue Version innerhalb von 7 Tagen.
- **Mittlere oder niedrige Lücke:** mit der nächsten Version, spätestens nach 30 Tagen.
- **Ohne bekannte Lücke:** Updates mindestens jedes Vierteljahr prüfen (`uv lock --upgrade`, danach alle Tests und die CI).

## Aufwendige Funktionen (15.1.3)

Aufwendig sind:

- PDF setzen (Typst),
- Datenpaket für die Betriebsprüfung, Gesamtexport und Auskunft (große ZIP-Dateien),
- Datensicherung und Wiederherstellung (scrypt, Verschlüsselung),
- tägliche Prüfung der Ablage (alle Prüfsummen),
- E-Rechnungen lesen,
- Tabellen importieren (bis 10.000 Zeilen in einer Transaktion),
- Kennwörter prüfen (Argon2, 100 MiB).

So bleibt das Programm verfügbar:

- Exporte und Sicherungen startet nur der Inhaber.
- Es läuft höchstens eine Sicherung zur Zeit.
- Tägliche Aufgaben laufen einmal am Tag in einem eigenen Thread.
- Große Dateien werden blockweise statt im Speicher verarbeitet.
- Uploads sind in der Größe begrenzt.
- waitress bedient bis zu 8 Anfragen gleichzeitig.
- Ohne Proxy gibt es keine Zeitgrenze, an der eine lange Antwort abbräche.

## Protokolle (16.1.1)

**Protokoll** (Datenbank, `protokoll.Eintrag`):

- Inhalt: Änderungen an Geschäftsdaten mit altem und neuem Wert; Anmeldung, Abmeldung und Fehlversuch mit Grund; Zwei-Faktor-Anmeldung ein und aus; Zugriff verweigert mit Methode und Pfad; Formulare ohne gültigen Schlüssel; Abweichungen in der Ablage; Auskunft, Löschung und Fristen nach DSGVO.
- Je Eintrag: Zeit (UTC), Benutzer (Nummer und Name), Aktion, Objekt, Beschreibung.
- Schutz: Im Programm unveränderbar. Die einzige Ausnahme ist das Schwärzen nach Art. 17 DSGVO.
- Lesen: der Inhaber unter Protokoll, Prüfer für ihren Zeitraum. Es steht auch im Datenpaket und im Gesamtexport.
- Aufbewahrung: Es wird nicht automatisch gelöscht.

**Fehlerprotokoll** (`<Daten>/fehler.log`):

- Inhalt: Fehler der Stufe ERROR aus Anfragen und Hintergrund-Threads, auch ungültige Host-Kopfzeilen.
- Format: je Eintrag Zeit mit Abstand zu UTC, Stufe, Modul, Meldung und Traceback.
- Größe: höchstens drei Dateien zu 1 MB, dann wird das älteste überschrieben.
- Lesen: wer das Windows-Konto benutzt.

Nie protokolliert werden Kennwörter, Codes, Schlüssel, Sitzungskennungen und Dateiinhalte. Der Server schreibt kein Zugriffsprotokoll, und nichts geht an Dritte.

## Für den Netzwerkbetrieb (D-3)

Vor der Freigabe des Netzwerkbetriebs sind diese Punkte umzusetzen und hier nachzutragen:

- HTTPS über einen Reverse Proxy mit TLS 1.2 oder 1.3 und öffentlich vertrautem Zertifikat (12.1, 12.2), HSTS mit einem Jahr und Subdomains (3.4.1), Umleitung von HTTP nur für Seiten (4.1.2).
- Cookies mit `Secure` und Präfix `__Host-` (3.3.1, 3.3.3); `SECURE_PROXY_SSL_HEADER` nur, wenn der Proxy die Kopfzeile selbst setzt (4.1.3).
- Zwei-Faktor-Anmeldung Pflicht für alle Rollen außer Prüfern (6.3.3); kürzere Sitzungsdauer (7.1.1).
- IP-Adresse aus dem Proxy übernehmen und ins Protokoll schreiben, Sperre auch nach IP-Adresse (6.3.1, 15.3.4, 16.2.1).
- PostgreSQL mit eigenem Dienstkonto ohne Standard-Kennwort (13.2), Request Smuggling am Proxy prüfen (4.2.1).

## Prüfliste

Alle 253 Anforderungen der Stufen 1 und 2: 161 erfüllt, 12 mit Begründung abweichend, 6 erst im Netzwerkbetrieb zu erfüllen (D-3), 74 entfallen, weil es die Funktion nicht gibt.

### V1 Kodierung und Bereinigung

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 1.1.1 | 2 | erfüllt | Eingaben | Django dekodiert Adresse und Formulare genau einmal; das Programm dekodiert nichts ein zweites Mal. |
| 1.1.2 | 2 | erfüllt | Kodieren zuletzt | Django-Vorlagen kodieren beim Ausgeben; Typst bekommt die Daten als JSON (`sys.inputs`), XML entsteht mit drafthorse/lxml. |
| 1.2.1 | 1 | erfüllt | HTML | Automatisches Escaping in allen Vorlagen. Kein `|safe` und kein `mark_safe`; `format_html` nur für die festen Symbole (`core/templatetags/kf.py`). Dateinamen in `Content-Disposition` über Django (RFC 6266). |
| 1.2.2 | 1 | erfüllt | Adressen | Links entstehen mit `{% url %}`/`reverse`, Werte darin mit `urlencode`. Weiterleitungen nur auf eigene Adressen (`url_has_allowed_host_and_scheme`). Der einzige Link nach außen (Telegram) beginnt fest mit `https://t.me/`. |
| 1.2.3 | 1 | erfüllt | JavaScript | Keine Inline-Skripte (CSP). Daten kommen über `data-`-Attribute (escaped) oder `JsonResponse` ins Skript. |
| 1.2.4 | 1 | erfüllt | SQL | Nur das Django-ORM; kein `raw`, `extra` oder eigener Cursor. `PRAGMA integrity_check` beim Wiederherstellen ist ein fester Text. |
| 1.2.5 | 1 | erfüllt | Betriebssystem | `subprocess` nur mit Argumentliste und nur für das eigene Programm (`kontorfreund.py`), nie `shell=True`. |
| 1.2.6 | 2 | entfällt | LDAP | Kein LDAP. |
| 1.2.7 | 2 | erfüllt | XPath | Die E-Rechnung wird mit festen Pfaden im Code gelesen (`eingang/lesen.py`); Eingaben kommen nie in einen Pfad. |
| 1.2.8 | 2 | erfüllt | LaTeX | Kein LaTeX. Typst-Vorlagen liegen fest im Programm, Daten nur als JSON; Typst kann keine Befehle ausführen. |
| 1.2.9 | 2 | erfüllt | Reguläre Ausdrücke | Suchen vergleichen Text (`icontains`, `casefold`); Eingaben werden nie zu regulären Ausdrücken. |
| 1.3.1 | 1 | entfällt | HTML-Editoren | Kein Editor für HTML; alle Texte sind reiner Text. |
| 1.3.2 | 1 | erfüllt | eval | Kein `eval`, `exec` oder `new Function`; die CSP erlaubt kein `unsafe-eval`. |
| 1.3.3 | 2 | erfüllt | Gefährliche Ziele | Dateinamen für die Ablage werden bereinigt und gekürzt und bekommen einen Zufallsvorsatz (`historie/models.py`); alle Textfelder haben eine Höchstlänge. |
| 1.3.4 | 2 | erfüllt | SVG | Das SVG-Logo erscheint nur als `<img>` (Daten-URL) und im PDF über Typst, beides ohne Skripte. SVG-Dateien an Adressen gibt es nur als Download mit `Content-Security-Policy: sandbox`. |
| 1.3.5 | 2 | entfällt | Markdown, CSS, XSL | Benutzer liefern keine Vorlagen, Stile oder Markdown. |
| 1.3.6 | 2 | erfüllt | SSRF | Ausgehend nur Telegram mit festem Rechner im Code und der SMTP-Server, den der Inhaber selbst einträgt. Keine Adresse aus Eingaben anderer Benutzer. |
| 1.3.7 | 2 | erfüllt | Vorlagen | Vorlagen nur aus den Dateien des Programms, nie aus Daten. |
| 1.3.8 | 2 | entfällt | JNDI | Kein Java. |
| 1.3.9 | 2 | entfällt | memcache | Kein memcache. |
| 1.3.10 | 2 | erfüllt | Formatzeichen | Eingaben werden nie als Formatzeichenkette benutzt. Die Platzhalter der Mahntexte ersetzt `str.replace` mit festen Namen (`zahlungen/models.py`); `logging` mit Platzhaltern. |
| 1.3.11 | 2 | erfüllt | SMTP | Versand mit Djangos `EmailMessage`, das Zeilenumbrüche in Kopfzeilen ablehnt; Empfänger aus einem E-Mail-Feld. |
| 1.4.1 | 2 | erfüllt | Speicher | Python verwaltet den Speicher. Bibliotheken in C und Rust (lxml, Pillow, pypdfium2, typst) siehe V15.2.1. |
| 1.4.2 | 2 | erfüllt | Ganzzahlen | Python-Ganzzahlen laufen nicht über; Beträge als `Decimal`. |
| 1.4.3 | 2 | erfüllt | Freigeben | Python gibt Speicher selbst frei; Dateien werden mit `with` geschlossen. |
| 1.5.1 | 1 | erfüllt | XXE | Eine E-Rechnung mit Dokumenttyp-Definition wird abgelehnt, bevor ElementTree sie liest (`eingang/lesen.py`, Prüfung mit expat). Ebenso jede XML in einer Tabelle zum Import (XLSX, ODS), bevor openpyxl oder ElementTree sie liest (`importe/lesen.py`). Andere XML liest das Programm nicht. |
| 1.5.2 | 2 | erfüllt | Deserialisieren | Kein `pickle`. Sitzungen als JSON (Djangos Vorgabe). Sicherungen sind authentifiziert verschlüsselt; ihr Inhalt ist JSON und eine SQLite-Datei, die vor dem Einspielen geprüft wird. |

### V2 Prüfung von Eingaben und Geschäftslogik

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 2.1.1 | 1 | erfüllt | Regeln dokumentiert | Abschnitt „Eingaben“ unten; die Felder beschreibt `docs/spec/`. |
| 2.1.2 | 2 | erfüllt | Zusammenhänge dokumentiert | Abschnitt „Eingaben“. |
| 2.1.3 | 2 | erfüllt | Grenzen dokumentiert | Abschnitt „Eingaben“. |
| 2.2.1 | 1 | erfüllt | Positiv prüfen | Django-Formulare mit Typ, Länge und Auswahl. Parameter in Adressen (`jahr`, `art`, `seite`, `sortiert`) werden gegen erlaubte Werte geprüft, sonst gilt die Vorgabe. |
| 2.2.2 | 1 | erfüllt | Auf dem Server | Alle Prüfungen in Formularen und Modellen; JavaScript hilft nur beim Ausfüllen. |
| 2.2.3 | 2 | erfüllt | Kombinationen | `clean()` der Formulare, z. B. Prüfungszeitraum, Zugang des Prüfers, neues ungleich bisheriges Kennwort. |
| 2.3.1 | 1 | erfüllt | Reihenfolge | Belege: Entwurf → festgeschrieben → Storno oder Korrektur, im Modell erzwungen. Anmeldung: erst Kennwort, dann Code innerhalb von 5 Minuten. Wiederherstellen: erst Vorschau, dann Kennwort. |
| 2.3.2 | 2 | erfüllt | Grenzen umgesetzt | Wie im Abschnitt „Eingaben“. |
| 2.3.3 | 2 | erfüllt | Transaktionen | Festschreiben, Storno, Löschen nach DSGVO, Löschen nach Fristen, Fassungen der Dokumentation und Ablegen von Dateien laufen in `transaction.atomic`; schlägt etwas fehl, bleibt der vorige Stand. |
| 2.3.4 | 2 | erfüllt | Doppelt vergeben | Nummern entstehen in einer Transaktion, die die Datenbank sofort sperrt (SQLite `IMMEDIATE`); es gibt keine Nummer zweimal. Eine Sicherung zur Zeit (Sperre in `backups/sicherung.py`). |
| 2.4.1 | 2 | begründet | Automatisierte Zugriffe | Anmeldung: Sperre nach 5 Fehlversuchen. Exporte, Sicherung und Datenpaket nur für den Inhaber. Darüber hinaus keine Mengengrenze je Minute: Der Server ist nur vom eigenen Rechner aus erreichbar, wer ihn dort automatisiert, hat auch den Datenordner. |

### V3 Sicherheit im Browser

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 3.2.1 | 1 | erfüllt | Falscher Kontext | Hochgeladene Dateien gibt es als Download oder mit `Content-Security-Policy: sandbox`; im Browser angezeigt werden nur PDF und Bilder, deren Inhalt zur Endung passt; überall `X-Content-Type-Options: nosniff`. |
| 3.2.2 | 1 | erfüllt | Text als Text | `static/js/app.js` setzt Text nur mit `textContent` und `new Option`. |
| 3.3.1 | 1 | begründet | Secure-Cookies | Einzelplatz: HTTP nur über 127.0.0.1, nichts verlässt den Rechner. Nicht jeder Browser speichert Secure-Cookies von `http://127.0.0.1` (Safari nicht), dann ginge keine Anmeldung. Für den Netzwerkbetrieb Pflicht (D-3). |
| 3.3.2 | 2 | erfüllt | SameSite | `Lax` für Sitzung und CSRF-Schlüssel. Jede Änderung ist ein POST mit CSRF-Schlüssel; `Lax` lässt nur Links von außen mit Cookie zu. |
| 3.3.3 | 2 | begründet | __Host- | Setzt `Secure` voraus, siehe V3.3.1; im Netzwerkbetrieb Pflicht (D-3). |
| 3.3.4 | 2 | erfüllt | HttpOnly | Sitzung und CSRF-Schlüssel (`CSRF_COOKIE_HTTPONLY`) sind für Skripte nicht lesbar. |
| 3.4.1 | 1 | D-3 | HSTS | Ohne TLS entfällt HSTS; im Netzwerkbetrieb setzt es der Reverse Proxy. |
| 3.4.2 | 1 | erfüllt | CORS | Seiten senden keine CORS-Kopfzeilen. WhiteNoise sendet für statische Dateien (CSS, Skripte, Schriften, Symbole) `Access-Control-Allow-Origin: *`; darin steht nichts Schutzbedürftiges. |
| 3.4.3 | 2 | erfüllt | CSP | `default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`, keine Inline-Skripte oder -Stile. Ausnahme: PDF-Antworten ohne CSP, weil der PDF-Betrachter des Browsers sonst nicht lädt. |
| 3.4.4 | 2 | erfüllt | nosniff | `SecurityMiddleware` auf allen Antworten, auch auf den statischen Dateien. |
| 3.4.5 | 2 | erfüllt | Referrer-Policy | `same-origin`. |
| 3.4.6 | 2 | erfüllt | frame-ancestors | `frame-ancestors 'none'` auf allen Seiten. PDF-Antworten haben keine CSP (V3.4.3), aber `X-Frame-Options: DENY`; ein PDF führt im Betrachter des Browsers keinen Code im Ursprung des Programms aus. |
| 3.5.1 | 1 | erfüllt | CSRF | Djangos CSRF-Schutz für jedes POST, Schlüssel als Formularfeld, dazu Prüfung von `Origin`. |
| 3.5.2 | 1 | entfällt | CORS-Preflight | Der Schutz hängt nicht am Preflight, siehe V3.5.1. |
| 3.5.3 | 1 | erfüllt | Sichere Methoden | Änderungen nur per POST (`require_POST` oder Formular); GET ändert keine Daten. Andere Methoden als GET, HEAD und POST beantwortet das Programm mit 405. |
| 3.5.4 | 2 | begründet | Eigener Hostname | Ein Programm je Adresse. Mehrere Firmen teilen sich `127.0.0.1:8765`, getrennt durch eigene Datenbank, eigene Konten und eigenen Cookie-Namen je Firma; alle Firmen gehören demselben Anwender. |
| 3.5.5 | 2 | entfällt | postMessage | Wird nicht benutzt. |
| 3.7.1 | 2 | erfüllt | Veraltete Technik | Nur HTML, CSS und JavaScript, keine Plug-ins. |
| 3.7.2 | 2 | erfüllt | Weiterleiten nach außen | Automatische Weiterleitungen nur auf eigene Adressen (V1.2.2). |

### V4 Schnittstellen

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 4.1.1 | 1 | erfüllt | Content-Type | HTML und CSV mit `charset`, die XML der eigenen Rechnungen mit `charset=utf-8`, JSON ist UTF-8, PDF und ZIP binär. Eingegangene XML nur als Download; ihre Kodierung steht in der Datei. |
| 4.1.2 | 2 | D-3 | HTTP zu HTTPS | Einzelplatz ohne HTTPS; im Netzwerkbetrieb leitet nur der Proxy die Seiten um. |
| 4.1.3 | 2 | erfüllt | Kopfzeilen vom Vermittler | Das Programm wertet `X-Forwarded-*`, `X-Real-IP` und Ähnliches nicht aus. |
| 4.2.1 | 2 | erfüllt | Request Smuggling | Nur waitress, ohne Proxy davor; waitress 3 bestimmt das Ende einer Anfrage nach RFC 9112. Mit Proxy erneut prüfen (D-3). |
| 4.3.1 | 2 | entfällt | GraphQL | Kein GraphQL. |
| 4.3.2 | 2 | entfällt | GraphQL | Kein GraphQL. |
| 4.4.1 | 1 | entfällt | WebSocket | Keine WebSockets. |
| 4.4.2 | 2 | entfällt | WebSocket | Keine WebSockets. |
| 4.4.3 | 2 | entfällt | WebSocket | Keine WebSockets. |
| 4.4.4 | 2 | entfällt | WebSocket | Keine WebSockets. |

### V5 Dateien

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 5.1.1 | 2 | erfüllt | Dokumentiert | Abschnitt „Dateien“. |
| 5.2.1 | 1 | erfüllt | Größe | Dateien an Adressen bis 50 MB (`APP_DATEI_MB`), E-Rechnungen bis 20 MB, Tabellen zum Import bis 10 MB, Logo bis 1 MB. Sicherungen haben keine Grenze, weil eigene Sicherungen groß sind; nur der Inhaber spielt sie ein, verarbeitet wird blockweise. |
| 5.2.2 | 1 | begründet | Endung und Inhalt | Geprüft wird, was das Programm liest oder anzeigt: E-Rechnung (XML-Wurzel bzw. PDF mit eingebetteter XML), Tabelle zum Import (ZIP mit dem Inhalt einer Excel- oder LibreOffice-Datei, sonst Text), Logo (Dateianfang, Typst liest es), Sicherung (Kennung und Entschlüsselung), PDF und Bilder an Adressen (Dateianfang; passt er nicht, nur Download). Dateien an Adressen dürfen jede Art haben, z. B. Verträge als DOCX; sie werden nie geöffnet, nur abgelegt und als Download zurückgegeben. |
| 5.2.3 | 2 | begründet | Archive | Das Programm entpackt eigene Sicherungen und Tabellen zum Import (XLSX, ODS sind ZIP-Archive). Bei Tabellen prüft es vor dem Lesen die entpackte Größe (höchstens 100 MB) und schreibt nichts aus dem Archiv auf die Platte. Sie sind mit AES-GCM authentifiziert, ohne das Kennwort lässt sich keine gültige Sicherung bauen; jede Datei hat eine Prüfsumme, jeder Pfad muss im Zielordner bleiben. Eingebettete XML in PDF begrenzt pypdf auf 75 MB je Datenstrom. |
| 5.3.1 | 1 | erfüllt | Nicht ausführen | Die Ablage liegt außerhalb der statischen Dateien; ausgeliefert wird nur über Ansichten mit Rechteprüfung, ausgeführt wird nichts. |
| 5.3.2 | 1 | erfüllt | Pfade | Ablagepfade aus Kundennummer, Zufall und bereinigtem Namen. Beleg-Pfade im Datenzugriff nur aus den Tabellen des Prüfungszeitraums. Beim Wiederherstellen muss jeder Pfad im Zielordner bleiben. |
| 5.4.1 | 2 | erfüllt | Dateiname | Jeder Download hat `Content-Disposition` mit einem Namen vom Programm; der hochgeladene Name wird bereinigt gespeichert. |
| 5.4.2 | 2 | erfüllt | RFC 6266 | `content_disposition_header` von Django, mit `filename*=UTF-8''…` für Umlaute. |
| 5.4.3 | 2 | begründet | Virenscanner | Kein eigener Scanner. Das Programm öffnet Anhänge nie; unter Windows prüft Microsoft Defender jede gespeicherte Datei. Der Virenschutz des Rechners ist Sache des Anwenders. |

### V6 Anmeldung

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 6.1.1 | 1 | erfüllt | Dokumentiert | Abschnitt „Anmeldung“. |
| 6.1.2 | 2 | erfüllt | Kontextwörter | Abschnitt „Anmeldung“. |
| 6.1.3 | 2 | erfüllt | Wege dokumentiert | Abschnitt „Anmeldung“. |
| 6.2.1 | 1 | erfüllt | Länge | Mindestens 12 Zeichen (Spezifikation K-5). |
| 6.2.2 | 1 | erfüllt | Ändern | Unter „Mein Konto“; Prüfer über „Kennwort ändern“ im Datenzugriff. |
| 6.2.3 | 1 | erfüllt | Bisheriges und neues | Das bisherige Kennwort wird verlangt (`KennwortAendernForm`). |
| 6.2.4 | 1 | erfüllt | Häufige Kennwörter | 36 701 Kennwörter ab 12 Zeichen aus Datenlecks, dazu Djangos 20 000 häufigste und eine deutsche Liste (`konten/kennwort.py`). |
| 6.2.5 | 1 | erfüllt | Keine Zeichenregeln | Keine Vorgaben zu Groß-, Kleinbuchstaben, Ziffern oder Sonderzeichen. |
| 6.2.6 | 1 | erfüllt | Verdeckt | `type=password` in allen Kennwortfeldern. |
| 6.2.7 | 1 | erfüllt | Einfügen | Einfügen ist erlaubt; `autocomplete` hilft Passwortmanagern. |
| 6.2.8 | 1 | erfüllt | Unverändert | Kennwörter werden weder gekürzt noch umgewandelt (`strip=False`). |
| 6.2.9 | 2 | erfüllt | 64 Zeichen | Keine Höchstlänge. |
| 6.2.10 | 2 | erfüllt | Kein Ablauf | Kennwörter laufen nie ab. |
| 6.2.11 | 2 | erfüllt | Kontextwörter genutzt | Besteht ein Kennwort ohne die Kontextwörter aus weniger als vier Buchstaben, wird es abgelehnt. |
| 6.2.12 | 2 | erfüllt | Datenlecks | Liste in `konten/daten/kennwoerter.txt`; geprüft wird ohne Verbindung nach außen. |
| 6.3.1 | 1 | erfüllt | Brute force | Je Konto 5 Fehlversuche, dann 15 Minuten Sperre; das gilt für Kennwort, Code und jede Bestätigung mit dem Kennwort. |
| 6.3.2 | 1 | erfüllt | Standardkonten | Keine; das erste Konto legt der Anwender beim ersten Start an. |
| 6.3.3 | 2 | begründet | Mehrere Faktoren | Zwei-Faktor-Anmeldung (TOTP) für jedes Konto, im Netzwerk für Inhaber Pflicht. Am Einzelplatz freiwillig: Der Server ist nur vom eigenen Rechner aus erreichbar, davor steht die Anmeldung am Betriebssystem. Im Netzwerkbetrieb Pflicht für alle Rollen außer Prüfern (D-3). |
| 6.3.4 | 2 | erfüllt | Keine weiteren Wege | Nur die im Abschnitt „Anmeldung“ genannten. |
| 6.4.1 | 1 | erfüllt | Erstes Kennwort | Der Inhaber vergibt es, es folgt den Kennwortregeln und muss bei der ersten Anmeldung durch ein eigenes ersetzt werden; ebenso nach dem Neusetzen durch den Inhaber. |
| 6.4.2 | 1 | erfüllt | Keine Hinweise | Keine Kennworthinweise, keine Sicherheitsfragen. |
| 6.4.3 | 2 | erfüllt | Vergessen | Kein Link per E-Mail. Der Inhaber setzt ein neues erstes Kennwort, die Zwei-Faktor-Anmeldung bleibt. Für den Inhaber selbst `Kontorfreund changepassword` am Rechner. |
| 6.4.4 | 2 | erfüllt | Faktor verloren | Der Inhaber setzt die Zwei-Faktor-Anmeldung zurück; er hat das Konto angelegt und kennt die Person. Für den Inhaber selbst `Kontorfreund entsperren --ohne-zwei-faktor` am Rechner. |
| 6.5.1 | 2 | erfüllt | Einmal | Der zuletzt benutzte Zeitschritt wird gespeichert (`totp_schritt`); ein Code gilt nur einmal. |
| 6.5.2 | 2 | entfällt | Wiederherstellungscodes | Gibt es nicht. |
| 6.5.3 | 2 | erfüllt | Zufall | TOTP-Geheimnis aus `secrets.token_bytes(20)`, 160 Bit. |
| 6.5.4 | 2 | entfällt | Codes per Nachricht | Gibt es nicht. |
| 6.5.5 | 2 | begründet | Lebensdauer | Ein Code gilt 30 Sekunden; ein Zeitschritt davor und danach wird angenommen, damit abweichende Uhren nicht aussperren (RFC 6238, Abschnitt 5.2). Nach dem Kennwort bleiben 5 Minuten für den Code. |
| 6.6.1 | 2 | entfällt | SMS | Keine Anmeldung per SMS oder Telefon. |
| 6.6.2 | 2 | entfällt | Codes per Nachricht | Telegram meldet nur Termine, es meldet niemanden an. |
| 6.6.3 | 2 | entfällt | Codes per Nachricht | Wie V6.6.2. |
| 6.8.1 | 2 | entfällt | Identitätsanbieter | Keine fremden Anmeldedienste. |
| 6.8.2 | 2 | entfällt | Identitätsanbieter | Keine. |
| 6.8.3 | 2 | entfällt | SAML | Kein SAML. |
| 6.8.4 | 2 | entfällt | Identitätsanbieter | Keine. |

### V7 Sitzungen

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 7.1.1 | 2 | erfüllt | Dauer dokumentiert | Abschnitt „Sitzungen“, mit Begründung der Abweichung von NIST SP 800-63B-4. |
| 7.1.2 | 2 | erfüllt | Gleichzeitige Sitzungen | Abschnitt „Sitzungen“. |
| 7.1.3 | 2 | entfällt | Single Sign-on | Keins. |
| 7.2.1 | 1 | erfüllt | Auf dem Server | Djangos Sitzungen in der Datenbank. |
| 7.2.2 | 1 | erfüllt | Dynamisch | Für jede Anmeldung ein neuer Sitzungsschlüssel. |
| 7.2.3 | 1 | erfüllt | 128 Bit | 32 Zeichen aus Kleinbuchstaben und Ziffern von `secrets`, rund 165 Bit. |
| 7.2.4 | 1 | erfüllt | Neuer Schlüssel | `login()` vergibt einen neuen Schlüssel, auch nach dem Code. |
| 7.3.1 | 2 | erfüllt | Inaktivität | 8 Stunden ohne Anfrage (`APP_ABMELDEN_NACH_STUNDEN`). |
| 7.3.2 | 2 | erfüllt | Höchstdauer | Spätestens 12 Stunden nach der Anmeldung (`konten/sitzungen.py`). |
| 7.4.1 | 1 | erfüllt | Beenden | Beim Abmelden löscht `logout()` die Sitzung in der Datenbank. |
| 7.4.2 | 1 | erfüllt | Gesperrte Konten | Django nimmt Sitzungen gesperrter Konten nicht mehr an; Prüfer werden nach dem letzten Tag abgemeldet. |
| 7.4.3 | 2 | erfüllt | Nach Änderung eines Faktors | Kennwort und TOTP-Geheimnis gehen in die Kennung der Sitzung ein (`Benutzer._get_session_auth_hash`): Jede Änderung beendet alle übrigen Sitzungen, die eigene bleibt. |
| 7.4.4 | 2 | erfüllt | Abmelden sichtbar | In der Seitenleiste jeder Seite, im Kopf des Datenzugriffs und auf der Seite für das eigene Kennwort. |
| 7.4.5 | 2 | erfüllt | Durch den Inhaber | Unter Benutzer › Name › „Auf allen Geräten abmelden“, für jeden Benutzer einzeln. |
| 7.5.1 | 2 | erfüllt | Erneut bestätigen | Zwei-Faktor-Anmeldung ein- und ausschalten nur mit dem Kennwort, Kennwort ändern nur mit dem bisherigen. Die E-Mail-Adresse lässt sich nicht ändern. |
| 7.5.2 | 2 | erfüllt | Sitzungen ansehen | „Mein Konto › Angemeldete Geräte“ zeigt Browser, Beginn und letzte Aktivität; alle anderen beenden nach Eingabe des Kennworts. |
| 7.6.1 | 2 | entfällt | Identitätsanbieter | Keine. |
| 7.6.2 | 2 | erfüllt | Bewusst angemeldet | Eine Sitzung entsteht nur durch Anmelden. |

### V8 Rechte

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 8.1.1 | 1 | erfüllt | Dokumentiert | Abschnitt „Rechte“. |
| 8.1.2 | 2 | erfüllt | Felder dokumentiert | Abschnitt „Rechte“. |
| 8.2.1 | 1 | erfüllt | Funktionen | Alles verlangt eine Anmeldung (`LoginRequiredMiddleware`); Inhaber-Bereiche `nur_inhaber`, Prüfer `nur_lesen` (`konten/rechte.py`). |
| 8.2.2 | 1 | erfüllt | Daten | Innerhalb einer Firma sehen alle Rollen außer Prüfern alle Geschäftsdaten (gewollt, Abschnitt „Rechte“). Gesperrte Adressen nur der Inhaber (`contacts/datenschutz.zugriff`). Prüfer nur ihren Zeitraum und nur Belege aus dessen Tabellen. |
| 8.2.3 | 2 | erfüllt | Felder | Formulare mit fester Feldliste; technische Felder sind `editable=False`; festgeschriebene Belege ändert niemand. |
| 8.3.1 | 1 | erfüllt | Auf dem Server | Alle Rechte werden im Server geprüft. |
| 8.4.1 | 2 | erfüllt | Mandanten | Jede Firma hat eigenen Datenordner, eigene Datenbank, eigene Konten, eigenen `SECRET_KEY` und eigenen Cookie-Namen; der Server öffnet eine Firma zur Zeit. |

### V9 Selbsttragende Token

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 9.1.1 | 1 | entfällt | Token | Keine selbsttragenden Token zur Anmeldung. Django signiert nur Hinweismeldungen mit HMAC-SHA256 und eigenem Salz. |
| 9.1.2 | 1 | entfällt | Token | Wie V9.1.1. |
| 9.1.3 | 1 | entfällt | Token | Wie V9.1.1. |
| 9.2.1 | 1 | entfällt | Token | Wie V9.1.1. |
| 9.2.2 | 2 | entfällt | Token | Wie V9.1.1. |
| 9.2.3 | 2 | entfällt | Token | Wie V9.1.1. |
| 9.2.4 | 2 | entfällt | Token | Wie V9.1.1. |

### V10 OAuth und OpenID Connect

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 10.1.1 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.1.2 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.2.1 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.2.2 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.3.1 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.3.2 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.3.3 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.3.4 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.1 | 1 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.2 | 1 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.3 | 1 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.4 | 1 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.5 | 1 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.6 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.7 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.8 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.9 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.10 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.4.11 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.5.1 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.5.2 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.5.3 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.5.4 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.5.5 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.6.1 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.6.2 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.7.1 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.7.2 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |
| 10.7.3 | 2 | entfällt | OAuth/OIDC | Weder OAuth noch OpenID Connect. |

### V11 Kryptografie

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 11.1.1 | 2 | erfüllt | Schlüsselverwaltung | Abschnitt „Kryptografie“. |
| 11.1.2 | 2 | erfüllt | Bestand | Abschnitt „Kryptografie“. |
| 11.2.1 | 2 | erfüllt | Geprüfte Umsetzungen | `cryptography` (OpenSSL), `argon2-cffi`, `hashlib`, `hmac` und `secrets` von Python; nichts selbst gebaut außer TOTP nach RFC 6238 auf `hmac`. |
| 11.2.2 | 2 | erfüllt | Austauschbar | Kennwort-Hash über `PASSWORD_HASHERS` (Django rechnet beim Anmelden um). Sicherungen tragen Formatkennung und KDF-Parameter im Kopf; Kennwort und Schlüssel lassen sich ändern. |
| 11.2.3 | 2 | erfüllt | 128 Bit | AES-256, SHA-256, HMAC-SHA256, scrypt mit 256-Bit-Schlüssel; TOTP mit 160-Bit-Geheimnis. |
| 11.3.1 | 1 | erfüllt | Kein ECB | Nur AES-GCM. |
| 11.3.2 | 1 | erfüllt | AES-GCM | Sicherungen mit AES-256-GCM. |
| 11.3.3 | 2 | erfüllt | Authentifiziert | GCM erkennt jede Änderung; Blöcke sind nummeriert, der letzte gekennzeichnet. |
| 11.4.1 | 1 | erfüllt | Hashfunktionen | SHA-256, Argon2, scrypt, HMAC-SHA256. SHA-1 nur innerhalb von HMAC für TOTP, wie RFC 6238 und die Authenticator-Apps es verlangen; HMAC-SHA1 ist dafür weiter zugelassen. Kein MD5. |
| 11.4.2 | 2 | erfüllt | Kennwörter | Argon2id mit Djangos Werten: 2 Durchläufe, 100 MiB, 8 Threads. |
| 11.4.3 | 2 | erfüllt | Integrität | SHA-256 für Belege, Fassungen und Sicherungsinhalt. |
| 11.4.4 | 2 | erfüllt | Schlüssel aus Kennwort | scrypt mit N = 2^17, r = 8, p = 1 (128 MiB) für das Kennwort der Sicherung. |
| 11.5.1 | 2 | erfüllt | Zufall | Alles Geheime aus `secrets`: `SECRET_KEY` (rund 300 Bit), Sitzungen, TOTP (160 Bit), Telegram-Code (128 Bit), Salz und Nonces. Der Zufallsvorsatz von Dateinamen (48 Bit) soll nur Namen unterscheiden, geheim ist er nicht. |
| 11.6.1 | 2 | entfällt | Signaturen | Keine Schlüsselpaare, keine Signaturen. |

### V12 Verschlüsselte Verbindungen

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 12.1.1 | 1 | D-3 | TLS-Versionen | Einzelplatz ohne TLS; im Netzwerk am Proxy. Ausgehend nimmt Python mindestens TLS 1.2. |
| 12.1.2 | 2 | D-3 | Verfahren | Wie V12.1.1. |
| 12.1.3 | 2 | entfällt | mTLS | Keine Client-Zertifikate. |
| 12.2.1 | 1 | D-3 | TLS nach außen | Am Einzelplatz ist nichts von außen erreichbar (nur 127.0.0.1). |
| 12.2.2 | 1 | D-3 | Zertifikate | Wie V12.2.1. |
| 12.3.1 | 2 | erfüllt | Verbindungen verschlüsselt | Telegram nur über HTTPS; SMTP nur mit STARTTLS oder SSL/TLS, ohne Verschlüsselung lässt sich kein Server eintragen. Zum Browser siehe V12.2.1. |
| 12.3.2 | 2 | erfüllt | Zertifikate prüfen | `urllib` und Djangos SMTP-Versand prüfen Zertifikat und Namen (`ssl.create_default_context`). |
| 12.3.3 | 2 | entfällt | Interne Dienste | Ein Prozess mit SQLite-Datei, keine internen Dienste. |
| 12.3.4 | 2 | entfällt | Interne Zertifikate | Wie V12.3.3. |

### V13 Konfiguration

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 13.1.1 | 2 | erfüllt | Verbindungen dokumentiert | Abschnitt „Verbindungen“. |
| 13.2.1 | 2 | entfällt | Dienstkonten | Keine Dienste untereinander; SQLite ist eine Datei. |
| 13.2.2 | 2 | erfüllt | Wenig Rechte | Läuft als normaler Benutzer ohne Administratorrechte. Nur die Installation braucht sie; das Programm liegt in `C:\Program Files` und kann seine eigenen Dateien nicht ändern. |
| 13.2.3 | 2 | entfällt | Standard-Zugangsdaten | Keine Zugangsdaten zwischen Teilen des Programms. |
| 13.2.4 | 2 | erfüllt | Erlaubte Ziele | Ausgehend nur Telegram (fester Rechner) und der SMTP-Server des Inhabers. |
| 13.2.5 | 2 | erfüllt | Laden von außen | Das Programm lädt nichts nach; Dateien nur aus Programm- und Datenordner. |
| 13.3.1 | 2 | begründet | Geheimnisse | Nichts im Quellcode oder Paket. `SECRET_KEY` und Sicherungsschlüssel als Dateien im Datenordner (nur für den eigenen Benutzer lesbar), TOTP-Geheimnisse, Telegram-Bot-Schlüssel und SMTP-Kennwort in der Datenbank. Kein Schlüsseltresor: Am Einzelplatz schützt das Benutzerkonto des Betriebssystems, Sicherungen sind verschlüsselt. |
| 13.3.2 | 2 | erfüllt | Zugriff auf Geheimnisse | Nur der Inhaber erreicht die Einstellungen; Bot-Schlüssel und SMTP-Kennwort gehen nie zurück an den Browser und fehlen in Protokoll und Exporten. |
| 13.4.1 | 1 | erfüllt | Keine .git-Ordner | Das Paket enthält nur die Ordner aus `packaging/kontorfreund.spec`. |
| 13.4.2 | 2 | erfüllt | Kein Debug | `DEBUG` nur mit `APP_DEBUG=1`, im Paket aus. |
| 13.4.3 | 2 | erfüllt | Keine Verzeichnislisten | WhiteNoise und das Programm listen keine Ordner. |
| 13.4.4 | 2 | erfüllt | TRACE | Antwort 405 (`core/sicherheit.methoden`). |
| 13.4.5 | 2 | erfüllt | Keine Doku- oder Überwachungsseiten | Kein Django-Admin, keine API-Doku. `/firmen/offen/` nennt nur die Nummer der geöffneten Firma für die Seite beim Wechseln. |

### V14 Datenschutz

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 14.1.1 | 2 | erfüllt | Eingestuft | Abschnitt „Schutzbedürftige Daten“. |
| 14.1.2 | 2 | erfüllt | Anforderungen | Abschnitt „Schutzbedürftige Daten“. |
| 14.2.1 | 1 | erfüllt | Nicht in Adressen | Sitzung nur im Cookie, Kennwörter und Codes nur im POST. Adressen enthalten Nummern, Suchbegriffe und Beleg-Pfade. Der Telegram-Link enthält den Verbindungscode; so verlangt es Telegram, der Code gilt nur zum Verbinden. |
| 14.2.2 | 2 | erfüllt | Kein Cache im Server | Kein Proxy und kein Seiten-Cache. |
| 14.2.3 | 2 | erfüllt | Keine Dritten | Keine Telemetrie, keine fremden Skripte, Schriften oder Bilder (CSP `default-src 'self'`). |
| 14.2.4 | 2 | erfüllt | Umgesetzt | Wie im Abschnitt „Schutzbedürftige Daten“. |
| 14.3.1 | 1 | erfüllt | Nach dem Abmelden | Seiten werden nicht gespeichert (V14.3.2), die Sitzung wird gelöscht; im Browser liegt nur die Wahl hell/dunkel. |
| 14.3.2 | 2 | erfüllt | no-store | `Cache-Control: no-store` auf allen Seiten und Downloads (`core/sicherheit.nicht_speichern`); nur statische Dateien dürfen in den Cache. |
| 14.3.3 | 2 | erfüllt | Browser-Speicher | Nur `kf-theme` (hell, dunkel) in `localStorage`. |

### V15 Sicheres Programmieren und Aufbau

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 15.1.1 | 1 | erfüllt | Fristen | Abschnitt „Bibliotheken“. |
| 15.1.2 | 2 | erfüllt | Stückliste | `uv.lock` mit Hashes; jedes Release enthält eine SBOM im Format CycloneDX. Bezugsquelle nur PyPI. |
| 15.1.3 | 2 | erfüllt | Aufwendige Funktionen | Abschnitt „Aufwendige Funktionen“. |
| 15.2.1 | 1 | erfüllt | Aktuell | `pip-audit` prüft bei jedem Push alle Abhängigkeiten gegen bekannte Lücken und hält die CI an; zum Zeitpunkt dieser Prüfung keine bekannt. |
| 15.2.2 | 2 | erfüllt | Verfügbarkeit | Wie im Abschnitt „Aufwendige Funktionen“. |
| 15.2.3 | 2 | erfüllt | Nichts Überflüssiges | Tests, Werkzeuge und Dokumentation fehlen im Paket; kein Django-Admin; Debug aus. |
| 15.3.1 | 1 | erfüllt | Nur nötige Felder | Die einzige Antwort in JSON (Orte zur PLZ) enthält nur die Orte. |
| 15.3.2 | 2 | erfüllt | Keine Umleitungen | Telegram-Anfragen folgen keiner Umleitung (`benachrichtigungen/telegram.py`). |
| 15.3.3 | 2 | erfüllt | Mass Assignment | Jedes Formular nennt seine Felder; keins mit `__all__` oder `exclude`. |
| 15.3.4 | 2 | entfällt | IP-Adresse | Das Programm wertet die IP-Adresse nicht aus; am Einzelplatz ist sie immer 127.0.0.1. Für den Netzwerkbetrieb neu bewerten (D-3). |
| 15.3.5 | 2 | erfüllt | Typen | Formulare wandeln in feste Typen; Zahlen aus Adressen nur nach `isdigit()`; Geheimnisse mit `compare_digest`. |
| 15.3.6 | 2 | erfüllt | Prototype Pollution | `app.js` mischt keine Eingaben in Objekte. |
| 15.3.7 | 2 | erfüllt | Parameter doppelt | Django trennt GET, POST und Cookies; Änderungen lesen nur POST. |

### V16 Protokolle und Fehler

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 16.1.1 | 2 | erfüllt | Bestand | Abschnitt „Protokolle“. |
| 16.2.1 | 2 | erfüllt | Angaben | Protokoll: Zeit, Benutzer, Aktion, Objekt oder Methode und Pfad, Grund bzw. Feld alt/neu. Fehlerprotokoll: Zeit, Stufe, Modul, Meldung. |
| 16.2.2 | 2 | erfüllt | Zeit | Protokoll in UTC; Fehlerprotokoll mit Abstand zu UTC (`2026-11-02T03:04:05+01:00`). Uhr ist die Systemuhr. |
| 16.2.3 | 2 | erfüllt | Nur dokumentierte Ziele | Nur die zwei im Abschnitt „Protokolle“. |
| 16.2.4 | 2 | erfüllt | Lesbar | Protokoll als CSV im Datenpaket und Gesamtexport; Fehlerprotokoll als Textzeilen mit ISO-8601-Zeit. |
| 16.2.5 | 2 | erfüllt | Schutzbedürftiges | Kennwörter, Bot-Schlüssel und SMTP-Kennwort erscheinen als „•••“; TOTP-Geheimnis, Codes und Sitzungsschlüssel nie. |
| 16.3.1 | 2 | erfüllt | Anmeldungen | Anmeldung, Fehlversuch und Abmeldung mit Grund, Sperren, Kennwortänderung (als Änderung am Benutzer), Zwei-Faktor-Anmeldung ein, aus und zurückgesetzt. |
| 16.3.2 | 2 | erfüllt | Verweigert | Jede Antwort 403 steht im Protokoll („Zugriff verweigert“, mit Methode und Pfad). |
| 16.3.3 | 2 | erfüllt | Umgehungsversuche | Formulare ohne gültigen CSRF-Schlüssel, Fehlversuche, Sperren, Abweichungen in der Ablage; ungültige Host-Kopfzeilen im Fehlerprotokoll. |
| 16.3.4 | 2 | erfüllt | Unerwartete Fehler | Fehler aus Anfragen und Hintergrund-Threads im Fehlerprotokoll; Telegram- und SMTP-Fehler zusätzlich als Meldung für den Inhaber. |
| 16.4.1 | 2 | erfüllt | Log Injection | Das Protokoll speichert Felder einzeln und zeigt sie escaped; das Fehlerprotokoll schreibt keine ungeprüften Eingaben. |
| 16.4.2 | 2 | begründet | Geschützt | Im Programm lässt sich das Protokoll weder ändern noch löschen (einzige Ausnahme: Schwärzen nach Art. 17 DSGVO), sehen darf es nur der Inhaber. Wer das Windows-Konto benutzt, könnte die Datenbankdatei ändern; dagegen hilft nur der Schutz des Rechners. |
| 16.4.3 | 2 | begründet | Getrennt gespeichert | Kein Protokollserver am Einzelplatz. Das Protokoll ist in jeder verschlüsselten Sicherung, auf Wunsch auch am zweiten Speicherort. |
| 16.5.1 | 2 | erfüllt | Allgemeine Fehlerseite | Ohne Debug zeigt Django nur „Server Error (500)“; Einzelheiten nur im Fehlerprotokoll. |
| 16.5.2 | 2 | erfüllt | Ausfall nach außen | Ohne Telegram oder SMTP arbeitet das Programm weiter und meldet den Fehler; Orte zur PLZ liegen im Programm. |
| 16.5.3 | 2 | erfüllt | Sicher scheitern | Fehler brechen die Transaktion ab; ohne Recht gibt es 403, nie die Daten; eine Sicherung wird vor dem Einspielen ganz geprüft. |

### V17 WebRTC

| Nr. | Stufe | Ergebnis | Thema | Umsetzung |
|---|---|---|---|---|
| 17.1.1 | 2 | entfällt | WebRTC | Kein WebRTC. |
| 17.2.1 | 2 | entfällt | WebRTC | Kein WebRTC. |
| 17.2.2 | 2 | entfällt | WebRTC | Kein WebRTC. |
| 17.2.3 | 2 | entfällt | WebRTC | Kein WebRTC. |
| 17.2.4 | 2 | entfällt | WebRTC | Kein WebRTC. |
| 17.3.1 | 2 | entfällt | WebRTC | Kein WebRTC. |
| 17.3.2 | 2 | entfällt | WebRTC | Kein WebRTC. |
