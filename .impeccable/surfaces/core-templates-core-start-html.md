---
version: 1
slug: "core-templates-core-start-html"
primary_target: "core/templates/core/start.html"
related_targets: ["contacts/templates/contacts/liste.html","contacts/templates/contacts/formular.html","invoicing/templates/invoicing/rechnung.html"]
---

# Surface brief: Übersicht, Adressen, Rechnung

Mode: Operate. Scope: App-Rahmen (Seitenleiste, Kopfzeile, Suche) plus Übersicht, Adressliste und -formular, Einstellungen, Rechnungseditor. Keine Beispieldaten: alle Inhalte gibt der Nutzer selbst ein; leere Zustände führen durch die ersten Schritte. Zielgruppe und Aufgaben stehen in PRODUCT.md. Häufigste Aufgabe: Rechnung schreiben.

Vom Nutzer festgelegt: vertraut für Umsteiger von klassischer Desktop-Bürosoftware (Bereiche, Reihenfolge, Begriffe, Rechnung in Schritten), aber eigenes, ruhigeres und schöneres Aussehen; keine Übernahme fremder Gestaltung. Bloß nicht: verspielt/bunt, kalt wie Buchhaltung, zu leer, zu voll.

## Direction contract

THESIS: Das vertraute Büro, aufgeräumt. Aufbau, Reihenfolge und Begriffe klassischer Desktop-Bürosoftware (Hauptauswahl, Adressen, Angebote & Rechnungen in Schritten) als ruhige, helle Arbeitsfläche. Verweigert: Kennzahl-Dashboard mit Kacheln und Diagrammen ebenso wie Maskenwüste mit Reitern.

OWN-WORLD: Helles, leicht warmes Neutralgrau als Fläche, eine zweite, etwas dunklere Ebene für die Seitenleiste, fast schwarze Tinte. Eine Akzentfarbe, Petrol, nur für Hauptaktion, Auswahl und Fokus. Status als Wort plus Form, nie nur Farbe. Eine Schrift: Atkinson Hyperlegible Next; Beträge in Tabellenziffern, rechtsbündig. Haarlinien statt Kästen, kleine Radien, keine Kartenraster.

STORY: Der Inhaber öffnet morgens, sieht in einer Arbeitsliste, was heute fällig ist, erledigt es mit einem Klick und schreibt eine Rechnung, deren Pflichtangaben das Programm sichtbar abhakt.

FIRST VIEWPORT: Links Seitenleiste mit den Bereichen in vertrauter Reihenfolge und Zählern. Oben Suche (Strg+K). Inhalt: Datumszeile, Schnellstart-Leiste mit „Neue Rechnung“ als einziger gefüllter Schaltfläche, darunter die Arbeitsliste „Heute zu tun“ in drei Gruppen; rechts eine schmale Spalte, durch Haarlinien gegliedert: offene Beträge, Umsatzgrenze nach § 19, „Entwürfe“ und „Zuletzt bearbeitet“ als Wiedereinstieg. Auf schmalen Bildschirmen begleitet eine Prüfleiste („7 von 8 · Es fehlt …“) den Rechnungseditor am unteren Rand.

FORM: Standardweg, vom Nutzer gewählt (vertraut wie die bisherige Software, eigenes Aussehen); nicht von der gewürfelten Liste; Seed 44122482. Signatur-Interaktion: Die Pflichtangaben-Prüfung im Rechnungseditor hakt live ab, Festschreiben wird erst bei 8 von 8 möglich. Bewegung nur für Zustandswechsel, 150–200 ms, ease-out.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
