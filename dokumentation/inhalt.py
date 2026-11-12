"""Inhalt der Verfahrensdokumentation (GoBD Rz. 151 ff.) und der Datenschutz-Dokumentation.

Ein Dokument ist eine Liste von Abschnitten mit Teilen, ein Teil eine Liste von Blöcken:
absatz (Zeilen), punkte, felder (Name, Zeilen), tabelle, antwort (Angabe des Inhabers)
oder offen (Frage, die der Inhaber noch beantworten muss). Nummern vergibt erst
`fassungen.druckdaten`, damit ein neuer Teil nicht alle folgenden als geändert meldet.

Hier steht nur, was sich selten ändert, also keine Zähler und keine Zeitpunkte der
letzten Sicherung oder Prüfung: Jede Änderung ergibt eine neue Fassung.
"""

import platform

from django.conf import settings
from django.db.models import Max, Min

from archive.models import Altbeleg
from auswertungen.models import Datev
from backups import sicherung
from benachrichtigungen.models import Einstellung
from core import updates
from core.models import Firmendaten
from konten.models import Benutzer
from konten.sitzungen import HOECHSTENS

from .models import Angaben


def zeilen(text):
    return [z.rstrip() for z in str(text).strip().splitlines()] or [""]


def absatz(text):
    return {"absatz": zeilen(text)}


def punkte(*eintraege):
    return {"punkte": [e for e in eintraege if e]}


def felder(*paare):
    return {"felder": [[name, zeilen(wert)] for name, wert in paare if wert]}


def tabelle(spalten, reihen, breit=()):
    return {
        "tabelle": {
            "spalten": spalten,
            "zeilen": [[zeilen(zelle) for zelle in reihe] for reihe in reihen],
            "breit": list(breit),
        }
    }


def antwort(angaben, feld):
    """Die Angabe des Inhabers oder, solange sie fehlt, die Frage danach."""
    wert = getattr(angaben, feld).strip()
    if wert:
        return {"antwort": zeilen(wert)}
    return {"offen": str(Angaben._meta.get_field(feld).verbose_name)}


def teil(titel, *bloecke):
    return {"titel": titel, "bloecke": [b for b in bloecke if b]}


def abschnitt(titel, *teile):
    return {"titel": titel, "teile": [t for t in teile if t]}


def _datum(wert):
    return f"{wert:%d.%m.%Y}" if wert else ""


def _anschrift(firma):
    return f"{firma.strasse}\n{firma.plz} {firma.ort}".strip()


def _umsatzsteuer(firma):
    # Wortlaut der ersten beiden wie vor der Auswahl, damit keine neue Fassung entsteht.
    if firma.kleinunternehmer:
        return "Kleinunternehmer nach § 19 UStG"
    if firma.umsatzsteuer == firma.Umsatzsteuer.STEUERFREI:
        hinweis = f" mit dem Hinweis „{firma.steuerfrei_hinweis}“"
        return f"Steuerfreie Leistungen nach § 4 UStG{hinweis if firma.steuerfrei_hinweis else ''}"
    return "Regelbesteuerung"


def betriebssystem():
    if platform.system() == "Darwin":
        return f"macOS {platform.mac_ver()[0]}".strip()
    if platform.system() == "Linux":
        try:
            return platform.freedesktop_os_release()["PRETTY_NAME"]
        except (OSError, KeyError):
            return "Linux"
    return f"{platform.system()} {platform.release()}".strip()


def programm():
    return f"{settings.PRODUCT_NAME} ({settings.PRODUCT_EDITION}) {settings.VERSION}"


def _altbelege():
    return Altbeleg.objects.aggregate(
        von=Min("datum"),
        bis=Max("datum"),
        am=Min("importiert"),
        zuletzt=Max("importiert"),
    ) | {
        "anzahl": Altbeleg.objects.count(),
        "quellen": sorted(set(Altbeleg.objects.values_list("quelle", flat=True))),
    }


def _benutzer():
    return list(Benutzer.objects.order_by("name", "email"))


# Die Suche nach neuen Versionen (D-7) erscheint nur, wenn der Inhaber sie eingeschaltet hat.
UPDATE_SUCHE = (
    "Eingeschaltet ist die Suche nach neuen Versionen: Einmal am Tag fragt Kontorfreund "
    "bei GitHub, wo die Installationspakete liegen, die neueste Version ab. Übertragen "
    "wird dabei nur die IP-Adresse, installiert wird nichts von selbst."
)


def _internet():
    if updates.suchen():
        return (
            "Kontorfreund läuft als Programm auf dem Rechner und wird im Browser "
            "bedient. Es braucht keine Internetverbindung und sendet keine Daten an "
            "den Hersteller. " + UPDATE_SUCHE
        )
    return (
        "Kontorfreund läuft als Programm auf dem Rechner und wird im Browser "
        "bedient. Es braucht keine Internetverbindung, sendet keine Daten an "
        "den Hersteller und lädt keine Inhalte aus dem Internet nach."
    )


def _keine_uebermittlung():
    if updates.suchen():
        return (
            "Keine Übermittlung an den Hersteller; aus dem Internet kommen nur Nummer "
            "und Neuerungen der neuesten Version (Abfrage bei GitHub, vom Inhaber "
            "eingeschaltet). Auch die Zuordnung von Postleitzahl und Ort geschieht auf "
            "dem Rechner."
        )
    return (
        "Keine Übermittlung an den Hersteller, keine Inhalte aus dem Internet; "
        "auch die Zuordnung von Postleitzahl und Ort geschieht auf dem Rechner."
    )


def _zugang():
    if settings.NETZWERK:
        return (
            "Kontorfreund ist im Netzwerk erreichbar. Inhaber müssen sich deshalb mit "
            "zweitem Faktor anmelden."
        )
    return (
        "Kontorfreund ist nur auf diesem Rechner erreichbar (Adresse 127.0.0.1), nicht "
        "von anderen Geräten im Netzwerk oder aus dem Internet."
    )


NUR_INHABER = (
    "Nur der Inhaber erreicht die Einstellungen, Benutzer, Datensicherung, das "
    "Änderungsprotokoll, die Datenschutz-Funktionen, die Aufbewahrungsfristen, das "
    "Datenpaket für die Betriebsprüfung, die Einstellungen für DATEV, Mahnwesen und "
    "Benachrichtigungen und diese Dokumentation."
)


PRUEFER = (
    "Ein Prüfer des Finanzamts liest nur, nur die Jahre seiner Prüfung und nur bis zu "
    "einem festen Tag."
)


def _zugang_benutzer(b):
    if not b.is_active:
        return "abgeschaltet"
    if b.ist_pruefer:
        return f"bis {_datum(b.zugang_bis)}"
    return "aktiv"


# ---------- Verfahrensdokumentation ----------


def verfahren():
    firma = Firmendaten.laden()
    angaben = Angaben.laden()
    alt = _altbelege()
    benutzer = _benutzer()
    stand = sicherung.zustand()
    datev = Datev.laden()
    seit = min((b.erstellt for b in benutzer), default=None)
    return [
        abschnitt(
            "Allgemeine Beschreibung",
            teil(
                "Unternehmen",
                felder(
                    ("Name", firma.name),
                    ("Marke oder Zusatz", firma.marke),
                    ("Inhaber", firma.inhaber),
                    ("Anschrift", _anschrift(firma)),
                    ("Steuernummer", firma.steuernummer),
                    ("USt-IdNr.", firma.ust_id),
                    ("Umsatzsteuer", _umsatzsteuer(firma)),
                ),
                antwort(angaben, "taetigkeit"),
            ),
            teil(
                "Gewinnermittlung und Steuererklärungen",
                antwort(angaben, "gewinnermittlung"),
                datev.beraternummer
                and absatz(
                    "Für den Steuerberater erzeugt Kontorfreund die Buchungen der Rechnungen "
                    f"als DATEV-Buchungsstapel (Beraternummer {datev.beraternummer}, "
                    f"Mandantennummer {datev.mandantennummer or 'nicht angegeben'}, "
                    f"{datev.get_kontenrahmen_display()})."
                ),
            ),
            teil(
                "Verantwortung und Zugriff",
                absatz(
                    "Verantwortlich für die Buchführung, die Aufbewahrung der Unterlagen und "
                    f"diese Dokumentation ist {firma.inhaber or 'der Inhaber'}. Mit "
                    "Kontorfreund arbeiten nur die folgenden Benutzer, jeder mit eigenem "
                    "Zugang:"
                ),
                tabelle(
                    ["Name", "E-Mail", "Rolle", "Zwei-Faktor", "Zugang"],
                    [
                        [
                            b.name,
                            b.email,
                            b.get_rolle_display(),
                            "ja" if b.zwei_faktor else "nein",
                            _zugang_benutzer(b),
                        ]
                        for b in benutzer
                    ],
                    breit=[1],
                ),
                absatz(
                    "Mitarbeiter arbeiten mit Adressen, Artikeln, Angeboten, "
                    "Auftragsbestätigungen, Rechnungen, Zahlungen, Mahnungen, "
                    f"Eingangsrechnungen und Wiedervorlagen. {NUR_INHABER} {PRUEFER}"
                ),
            ),
            teil(
                "Eingesetzte Hard- und Software",
                felder(
                    ("Programm", f"{programm()}, quelloffen unter der Lizenz AGPL-3.0"),
                    ("Im Einsatz seit", _datum(seit)),
                    ("Betriebssystem", betriebssystem()),
                    ("Datenordner", str(settings.DATA_DIR)),
                    ("Erreichbar", _zugang()),
                ),
                antwort(angaben, "rechner"),
                absatz(_internet()),
            ),
        ),
        abschnitt(
            "Belege und Abläufe in Kontorfreund",
            teil(
                "Ausgangsrechnungen",
                absatz(
                    "Eine Rechnung entsteht als Entwurf. Ein Entwurf hat noch keine Nummer "
                    "und lässt sich frei ändern oder löschen; er zählt nicht als Beleg. "
                    "Für wiederkehrende Leistungen legt Kontorfreund aus einem Vertrag am "
                    "Anfang jedes Zeitraums einen solchen Entwurf an; festgeschrieben wird "
                    "er wie jeder andere vom Nutzer."
                ),
                absatz(
                    "Beim Festschreiben prüft Kontorfreund die Pflichtangaben nach § 14 "
                    "Abs. 4 UStG: Absender, Empfänger mit Anschrift, Steuernummer oder "
                    "USt-IdNr., Menge und Art der Leistung, Leistungszeitraum und Betrag. "
                    "Fehlt etwas, lässt sich die Rechnung nicht festschreiben. Danach "
                    "vergibt Kontorfreund die Rechnungsnummer: zweistellige Jahreszahl und "
                    "vierstelliger Zähler, fortlaufend und ohne Lücken"
                    + (
                        ", im Anschluss an die Nummern aus dem bisherigen Programm"
                        if alt["anzahl"]
                        else ""
                    )
                    + ". Alle Angaben der Rechnung werden eingefroren, die Rechnung wird "
                    "als PDF/A-3 mit eingebetteter E-Rechnung im Format ZUGFeRD (EN 16931) "
                    "erzeugt und mit Prüfsumme in der Ablage gespeichert. Für Empfänger, "
                    "die eine XRechnung verlangen, entsteht zusätzlich die XML-Datei der "
                    "XRechnung 3.0; sie ist dann das maßgebliche Original."
                ),
                absatz(
                    "Eine festgeschriebene Rechnung lässt sich weder ändern noch löschen. "
                    "Vermerkt werden nur noch der Versand und die Zahlungen. Versendet "
                    "wird die abgelegte Datei"
                    + (
                        ", direkt aus Kontorfreund per E-Mail oder als Download"
                        if firma.mail_bereit
                        else ", heruntergeladen und vom Inhaber selbst verschickt"
                    )
                    + "."
                ),
                firma.kleinunternehmer
                and absatz(
                    "Jede Rechnung trägt den Hinweis auf die Steuerbefreiung nach § 19 "
                    "UStG. Kontorfreund rechnet die Umsätze des Vorjahres und des "
                    "laufenden Jahres zusammen und warnt ab 80 % der Grenzen von 25.000 € "
                    "und 100.000 €. Eine Rechnung, mit der der Umsatz des laufenden Jahres "
                    "100.000 € übersteigen würde, lässt sich nicht als Rechnung eines "
                    "Kleinunternehmers festschreiben."
                ),
            ),
            teil(
                "Stornorechnung und Rechnungskorrektur",
                absatz(
                    "Eine fehlerhafte Rechnung wird nicht geändert, sondern durch einen "
                    "neuen Beleg berichtigt. Die Stornorechnung hebt sie ganz auf: Sie "
                    "bekommt eine eigene Nummer, verweist auf die ursprüngliche Rechnung "
                    "und enthält deren Positionen mit negativer Menge. Eine "
                    "Rechnungskorrektur mindert nur einen Teil, höchstens bis zum noch "
                    "nicht korrigierten Betrag. Die ursprüngliche Rechnung bleibt in "
                    "beiden Fällen unverändert erhalten."
                ),
            ),
            teil(
                "Angebote und Auftragsbestätigungen",
                absatz(
                    "Angebote und Auftragsbestätigungen haben je einen eigenen "
                    "Nummernkreis im Format der Rechnungen. Beim Fertigstellen werden sie "
                    "wie Rechnungen eingefroren und als PDF/A-3 mit Prüfsumme abgelegt; "
                    "danach lassen sich nur noch Versand und Antwort des Kunden vermerken. "
                    "Eine geänderte Fassung ist ein neues Angebot mit neuer Nummer. Aus "
                    "einem Angebot oder einer Auftragsbestätigung lässt sich ein "
                    "Rechnungsentwurf mit denselben Positionen erstellen."
                ),
            ),
            teil(
                "Zahlungen und offene Posten",
                absatz(
                    "Jede festgeschriebene Rechnung ist ein offener Posten, bis sie bezahlt "
                    "ist. Zahlungseingänge erfasst der Inhaber von Hand nach dem "
                    "Kontoauszug, mit Datum und Betrag; Kontorfreund ist nicht mit dem "
                    "Bankkonto verbunden. Teilzahlungen sind möglich. Wird eine Rechnung "
                    "innerhalb der Skontofrist bis auf das Skonto bezahlt, bucht "
                    "Kontorfreund den Rest als Skonto. Uneinbringliche Beträge werden mit "
                    "Angabe eines Grundes ausgebucht. Jede Zahlung und Ausbuchung steht im "
                    "Änderungsprotokoll."
                ),
            ),
            teil(
                "Mahnungen",
                absatz(
                    "Zahlungserinnerung und Mahnungen folgen in bis zu drei Stufen mit "
                    "einstellbaren Fristen, Gebühren und Verzugszinsen. Jedes Schreiben "
                    "wird als PDF/A-3 mit Prüfsumme abgelegt und danach nicht mehr "
                    "geändert. Ein versehentlich erstelltes Schreiben lässt sich nur "
                    "löschen, solange es das letzte zur Rechnung ist; auch das steht im "
                    "Änderungsprotokoll."
                ),
            ),
            teil(
                "Eingangsrechnungen",
                absatz(
                    "Empfangene E-Rechnungen (XRechnung oder ZUGFeRD, als XML oder PDF) "
                    "werden in Kontorfreund hochgeladen. Die Datei wird unverändert mit "
                    "Prüfsumme abgelegt; dieselbe Datei ein zweites Mal erkennt "
                    "Kontorfreund und legt sie nicht doppelt ab. Angezeigt wird immer die "
                    "Originaldatei, nachdem ihre Prüfsumme geprüft wurde. Eine "
                    "Eingangsrechnung lässt sich nicht löschen; ändern lässt sich nur die "
                    "Zuordnung zum Lieferanten."
                ),
            ),
            teil(
                "Adressen und Artikel",
                absatz(
                    "Adressen von Kunden, Interessenten und Lieferanten und die Artikel "
                    "mit ihren Preisen sind Stammdaten. Jede Änderung steht im "
                    "Änderungsprotokoll. Eine Rechnung übernimmt Empfänger und Positionen "
                    "als Kopie; spätere Änderungen an Adresse oder Artikel berühren "
                    "festgeschriebene Belege nicht. Adressen und Artikel lassen sich auch "
                    "aus einer Tabelle übernehmen (CSV, Excel, LibreOffice); vorher zeigt "
                    "ein Probelauf, was angelegt wird, und jede übernommene Zeile steht wie "
                    "eine Eingabe von Hand im Änderungsprotokoll. Nicht mehr benötigte Adressen kommen "
                    "ins Archiv, Artikel werden inaktiv. Gelöscht wird eine Adresse nur, "
                    "wenn für ihre Belege keine Aufbewahrungsfrist mehr läuft; sonst wird "
                    "sie auf Verlangen der Person gesperrt (Art. 18 DSGVO)."
                ),
            ),
            alt["anzahl"]
            and teil(
                "Belege aus dem bisherigen Programm",
                absatz(
                    f"Am {_datum(alt['am'])} wurden {alt['anzahl']} Belege aus den Jahren "
                    f"{alt['von']:%Y} bis {alt['bis']:%Y} aus dem bisherigen Programm "
                    f"({', '.join(alt['quellen'])}) übernommen"
                    + (
                        f", die letzten am {_datum(alt['zuletzt'])}"
                        if _datum(alt["zuletzt"]) != _datum(alt["am"])
                        else ""
                    )
                    + ". Übernommen wurden die PDF-Dateien, die das bisherige Programm "
                    "erzeugt hatte, unverändert und mit Prüfsumme. Nummer, Datum, "
                    "Empfänger und Betrag wurden daraus gelesen, damit die Belege in "
                    "Listen, Suche und Auswertungen erscheinen. Maßgeblich bleibt die "
                    "Datei."
                ),
                antwort(angaben, "altprogramm"),
            ),
            teil(
                "Auswertungen",
                absatz(
                    "Das Rechnungsausgangsbuch listet je Jahr, Quartal oder Monat alle "
                    "festgeschriebenen Rechnungen, Stornos und Korrekturen mit "
                    "Zahlungsstand"
                    + (
                        ", dazu die Rechnungen aus dem bisherigen Programm"
                        if alt["anzahl"]
                        else ""
                    )
                    + ". Es lässt sich wie die Listen der Adressen und offenen Posten als "
                    "Excel-, LibreOffice- oder CSV-Datei herunterladen. Daneben erzeugt "
                    "Kontorfreund einen DATEV-Buchungsstapel für einen Steuerberater."
                ),
            ),
        ),
        abschnitt(
            "Unterlagen außerhalb von Kontorfreund",
            teil(
                "Zahlungsverkehr und Kontoauszüge",
                antwort(angaben, "zahlungsverkehr"),
            ),
            teil("Weitere Belege", antwort(angaben, "belege")),
            teil("E-Mails und Geschäftspost", antwort(angaben, "email")),
        ),
        abschnitt(
            "Technische Systemdokumentation",
            teil(
                "Aufbau",
                absatz(
                    "Kontorfreund ist in Python mit dem Web-Framework Django geschrieben. "
                    "Das Programm startet einen Webserver auf dem eigenen Rechner und "
                    "öffnet den Browser. Alle Daten liegen im Datenordner: die Datenbank "
                    "(SQLite, Datei db.sqlite3) und die Ablage mit den Belegdateien."
                ),
                tabelle(
                    ["Ordner im Datenordner", "Inhalt"],
                    [
                        [
                            "archiv/rechnungen/<Jahr>/",
                            "Rechnungen, Stornos und Korrekturen (PDF, bei XRechnung auch XML)",
                        ],
                        ["archiv/angebote/<Jahr>/", "Angebote"],
                        ["archiv/auftraege/<Jahr>/", "Auftragsbestätigungen"],
                        [
                            "archiv/mahnungen/<Jahr>/",
                            "Zahlungserinnerungen und Mahnungen",
                        ],
                        ["archiv/eingang/<Jahr>/", "Empfangene E-Rechnungen"],
                        *(
                            [
                                [
                                    "archiv/altbelege/",
                                    "Belege aus dem bisherigen Programm",
                                ]
                            ]
                            if alt["anzahl"]
                            else []
                        ),
                        [
                            "archiv/dateien/<Kundennummer>/",
                            "Dateien an Adressen, unter der Kundennummer beim Ablegen",
                        ],
                        ["archiv/dokumentation/", "Fassungen dieser Dokumentation"],
                        ["sicherung/", "Verschlüsselte Datensicherungen"],
                    ],
                    breit=[1],
                ),
            ),
            teil(
                "Belegformate und Prüfsummen",
                absatz(
                    "Ausgangsbelege sind PDF/A-3-Dateien mit eingebetteten Schriften, "
                    "also ohne Kontorfreund dauerhaft lesbar. Rechnungen enthalten die "
                    "E-Rechnung als XML nach EN 16931. Zu jeder abgelegten Datei speichert "
                    "Kontorfreund die Prüfsumme SHA-256. Weicht eine Datei davon ab, fällt "
                    "das bei der täglichen Prüfung auf."
                ),
            ),
            teil(
                "Unveränderbarkeit",
                absatz(
                    "Festgeschriebene Rechnungen, fertiggestellte Angebote und "
                    "Auftragsbestätigungen, Mahnungen, Eingangsrechnungen"
                    + (
                        " und die Belege aus dem bisherigen Programm"
                        if alt["anzahl"]
                        else ""
                    )
                    + " sperrt das Programm gegen jede Änderung und gegen das Löschen. Die eingefrorenen Angaben eines Belegs stehen "
                    "in der Datenbank, die Datei in der Ablage. Abgelegte Dateien werden "
                    "nie überschrieben. Löschen ist nur nach Ablauf der "
                    "Aufbewahrungsfrist möglich."
                ),
            ),
            teil(
                "Änderungsprotokoll",
                absatz(
                    "Kontorfreund schreibt jede Anlage, Änderung und Löschung von Adressen, "
                    "Artikeln, Belegen, Zahlungen, Einstellungen und Benutzern in ein "
                    "Protokoll: Zeitpunkt, Benutzer, Feld, alter und neuer Wert. Dazu "
                    "kommen An- und Abmeldungen, Fehlversuche, verweigerte Zugriffe, "
                    "Datenschutz-Auskünfte und Befunde "
                    "der Prüfung der Ablage. Einträge lassen sich im Programm weder ändern "
                    "noch löschen. Einzige Ausnahme: Nach einer Löschung auf Verlangen "
                    "(Art. 17 DSGVO) oder nach Ablauf der Aufbewahrungsfrist werden die "
                    "Werte der gelöschten Daten geschwärzt; Zeitpunkt, Benutzer und Art "
                    "der Änderung bleiben stehen."
                ),
            ),
            teil(
                "Zugriffsschutz",
                absatz(
                    "Jede Seite verlangt eine Anmeldung mit E-Mail-Adresse und Kennwort. "
                    "Kennwörter haben mindestens 12 Zeichen; bekannte aus Datenlecks und "
                    "solche aus Firmen- oder Benutzernamen lehnt das Programm ab. "
                    "Gespeichert werden sie nur als Argon2-Hash. Ein Kennwort, das der "
                    "Inhaber vergeben hat, ersetzt der Benutzer bei der ersten Anmeldung "
                    "durch ein eigenes. Nach fünf Fehlversuchen ist das Konto 15 Minuten "
                    "gesperrt. Wer "
                    f"{settings.SESSION_COOKIE_AGE // 3600} Stunden nichts tut, wird "
                    f"abgemeldet, spätestens {HOECHSTENS // 3600} Stunden nach der "
                    "Anmeldung. Eine Zwei-Faktor-Anmeldung mit Einmalcodes aus einer App "
                    "lässt sich je Benutzer einschalten. Unter „Mein Konto“ sieht jeder, "
                    "wo er angemeldet ist, und kann andere Geräte abmelden."
                ),
            ),
        ),
        abschnitt(
            "Betriebsdokumentation",
            teil(
                "Datensicherung",
                absatz(
                    "Eine Sicherung enthält die Datenbank und die ganze Ablage. Sie ist mit "
                    "AES-256-GCM verschlüsselt; der Schlüssel wird aus einem Kennwort des "
                    "Inhabers abgeleitet, ohne das sich keine Sicherung öffnen lässt. "
                    "Kontorfreund sichert einmal am Tag beim ersten Gebrauch und vor jeder "
                    "Umstellung der Datenbank auf eine neue Version. Liegt die letzte "
                    "Sicherung mehr "
                    "als 7 Tage zurück, warnt das Programm. Beim Wiederherstellen wird der "
                    "aktuelle Stand vorher gesichert. Einzelne fehlende oder veränderte "
                    "Belegdateien lassen sich aus den Sicherungen zurückholen."
                )
                if stand["eingerichtet"]
                else {
                    "offen": "Die Datensicherung ist noch nicht eingerichtet. Richten Sie "
                    "sie in Kontorfreund unter Datensicherung ein."
                },
                stand["eingerichtet"]
                and felder(
                    ("Aufbewahrt", f"die letzten {stand['aufbewahren']} Sicherungen"),
                    ("Speicherort", str(sicherung.sicherungsordner())),
                    ("Zweiter Speicherort", stand["ziel"] or "keiner eingerichtet"),
                ),
            ),
            teil(
                "Prüfung der Ablage",
                absatz(
                    "Einmal am Tag rechnet Kontorfreund die Prüfsummen aller abgelegten "
                    "Dateien nach. Fehlt eine Datei oder weicht sie ab, steht das auf der "
                    "Übersicht und im Änderungsprotokoll"
                    + (
                        " und kommt als Nachricht über Telegram"
                        if Einstellung.laden().verbunden
                        else ""
                    )
                    + ". Der Inhaber holt das Original dann aus der Datensicherung zurück."
                ),
            ),
            teil(
                "Programmänderungen",
                absatz(
                    "Neue Versionen von Kontorfreund erscheinen mit einer Liste der "
                    "Änderungen. Vor der Umstellung der Datenbank auf eine neue Version "
                    "sichert das Programm automatisch. Jede Fassung dieser Dokumentation "
                    "nennt die Version, für die sie gilt; eine neue Version ergibt beim "
                    "nächsten Herunterladen eine neue Fassung."
                ),
            ),
            teil(
                "Aufbewahrung und Löschung",
                absatz(
                    "Rechnungen und andere Buchungsbelege werden 8 Jahre aufbewahrt, "
                    "Angebote, Auftragsbestätigungen, Mahnungen und andere "
                    "Geschäftsbriefe 6 Jahre, jeweils ab Ende des Kalenderjahres (§ 147 "
                    "Abs. 3 AO, § 14b UStG). Diese Dokumentation und ihre früheren "
                    "Fassungen löscht Kontorfreund nicht. Einmal im Jahr schlägt das "
                    "Programm abgelaufene Belege zum Löschen vor. Gelöscht wird nur, was "
                    "der Inhaber bestätigt, und nie ein Beleg, auf den sich ein noch "
                    "aufzubewahrender Beleg bezieht. Belege, die für eine noch nicht "
                    "abgeschlossene Steuerfestsetzung, eine Außenprüfung oder ein "
                    "Rechtsbehelfsverfahren von Bedeutung sind, behält der Inhaber länger."
                ),
            ),
            teil(
                "Datenzugriff bei einer Betriebsprüfung",
                absatz(
                    "Für die Datenträgerüberlassung (§ 147 Abs. 6 AO) erzeugt Kontorfreund "
                    "je Zeitraum ein Datenpaket: die Tabellen als CSV mit einer "
                    "Beschreibung index.xml nach dem Beschreibungsstandard der "
                    "Finanzverwaltung und alle Belegdateien des Zeitraums. Für den "
                    "unmittelbaren Zugriff legt der Inhaber dem Prüfer ein eigenes Konto "
                    "mit der Rolle Prüfer an, mit den Jahren des Prüfungszeitraums und "
                    "einem letzten Tag, höchstens ein Jahr voraus. Der Prüfer sieht nur "
                    "diese Jahre: Rechnungsausgangsbuch, Rechnungen mit Positionen, "
                    "Zahlungen, Mahnungen, Eingangsrechnungen, "
                    + ("Belege aus dem bisherigen Programm, " if alt["anzahl"] else "")
                    + "die zugehörigen Adressen, das Änderungsprotokoll und die "
                    "Verfahrensdokumentation. Er filtert und sortiert die Tabellen und "
                    "öffnet die Belege, kann aber nichts ändern, nichts anlegen und keine "
                    "anderen Bereiche aufrufen. Nach dem letzten Tag ist keine Anmeldung "
                    "mehr möglich, eine laufende Sitzung endet. Ein Gesamtexport aller Daten und Belege in offenen Formaten hält die "
                    "Unterlagen auch nach einem Programmwechsel lesbar."
                ),
            ),
        ),
        abschnitt(
            "Internes Kontrollsystem",
            teil(
                "Kontrollen im Programm",
                punkte(
                    "Zugang nur nach Anmeldung, Rechte nach Rolle (Zugriffsschutz).",
                    "Rechnungen ohne Pflichtangaben lassen sich nicht festschreiben "
                    "(Ausgangsrechnungen).",
                    "Nummern entstehen erst beim Festschreiben, fortlaufend und lückenlos "
                    "(Ausgangsrechnungen).",
                    "Festgeschriebene Belege sind gesperrt; berichtigt wird nur durch einen "
                    "neuen Beleg (Unveränderbarkeit, Stornorechnung und Rechnungskorrektur).",
                    "Jede Änderung ist mit Zeitpunkt, Benutzer und altem Wert "
                    "nachvollziehbar (Änderungsprotokoll).",
                    "Tägliche Prüfung aller abgelegten Dateien gegen ihre Prüfsumme "
                    "(Prüfung der Ablage).",
                    "Tägliche verschlüsselte Sicherung mit Warnung nach 7 Tagen ohne "
                    "Sicherung (Datensicherung).",
                    firma.kleinunternehmer
                    and "Warnung vor den Umsatzgrenzen nach § 19 UStG (Ausgangsrechnungen).",
                    "Löschen nach Ablauf der Fristen nur nach Bestätigung des Inhabers "
                    "(Aufbewahrung und Löschung).",
                ),
            ),
        ),
    ]


# ---------- Verzeichnis von Verarbeitungstätigkeiten und TOM ----------


def _taetigkeit(titel, zweck, rechtsgrundlage, betroffene, daten, empfaenger, frist):
    return teil(
        titel,
        felder(
            ("Zweck", zweck),
            ("Rechtsgrundlage", rechtsgrundlage),
            ("Betroffene Personen", betroffene),
            ("Daten", daten),
            ("Empfänger", empfaenger),
            ("Löschung", frist),
            (
                "Technik",
                "Kontorfreund, siehe Technische und organisatorische Maßnahmen",
            ),
        ),
    )


MASSNAHMEN = (
    "tom_verschluesselt",
    "tom_bildschirmsperre",
    "tom_aktuell",
    "tom_zutritt",
    "tom_akten",
)

BELEG_FRISTEN = (
    "Rechnungen und Zahlungen 8 Jahre, Angebote, Auftragsbestätigungen und Mahnungen "
    "6 Jahre, jeweils ab Ende des Kalenderjahres (§ 147 AO, § 14b UStG). Kontorfreund "
    "schlägt abgelaufene Belege einmal im Jahr zum Löschen vor."
)


def datenschutz():
    firma = Firmendaten.laden()
    angaben = Angaben.laden()
    telegram = Einstellung.laden()
    stand = sicherung.zustand()
    benutzer = _benutzer()
    zwei_faktor = sum(b.zwei_faktor for b in benutzer if b.is_active)
    aktiv = sum(b.is_active for b in benutzer)
    am_platz = [
        str(Angaben._meta.get_field(feld).verbose_name)
        for feld in MASSNAHMEN
        if getattr(angaben, feld)
    ]
    if angaben.tom_weitere.strip():
        am_platz += zeilen(angaben.tom_weitere)
    return [
        abschnitt(
            "Verantwortlicher",
            teil(
                "Angaben nach Art. 30 Abs. 1 lit. a DSGVO",
                felder(
                    ("Name", firma.name),
                    ("Vertreten durch", firma.inhaber),
                    ("Anschrift", _anschrift(firma)),
                    ("E-Mail", firma.email),
                    ("Telefon", firma.telefon),
                    (
                        "Datenschutzbeauftragter",
                        angaben.datenschutzbeauftragter
                        or "nicht benannt; vorgeschrieben erst, wenn in der Regel "
                        "mindestens 20 Personen ständig mit der automatisierten "
                        "Verarbeitung personenbezogener Daten beschäftigt sind (§ 38 "
                        "Abs. 1 BDSG)",
                    ),
                ),
            ),
        ),
        abschnitt(
            "Verarbeitungstätigkeiten",
            _taetigkeit(
                "Kunden und Interessenten",
                "Anbahnung und Durchführung von Aufträgen, Betreuung der Kunden, "
                "Wiedervorlagen und Gesprächsnotizen",
                "Art. 6 Abs. 1 lit. b DSGVO (Vertrag und vorvertragliche Maßnahmen), "
                "lit. f (berechtigtes Interesse an der Betreuung der Kunden)",
                "Kunden, Interessenten und deren Ansprechpartner",
                "Name, Position, Anschrift, E-Mail-Adressen, Telefonnummern, Website, "
                "USt-IdNr., Notizen, Verlauf von Anrufen, E-Mails und Terminen, Dateien "
                "zur Adresse",
                "keine",
                "Adressen ohne Belege, sobald sie nicht mehr gebraucht werden oder die "
                "Person es verlangt (Art. 17 DSGVO); mit Belegen gesperrt bis zum Ende "
                "der Aufbewahrungsfrist (Art. 18 DSGVO).",
            ),
            _taetigkeit(
                "Angebote, Rechnungen und Zahlungen",
                "Angebote und Auftragsbestätigungen, Rechnungen, Überwachung der "
                "Zahlungen, Mahnungen, Erfüllung der Aufbewahrungspflichten",
                "Art. 6 Abs. 1 lit. b DSGVO (Vertrag), lit. c (§ 14 UStG, § 147 AO)",
                "Kunden und deren Ansprechpartner",
                "Name, Anschrift, Leistungen, Beträge, Zahlungen, Mahnungen, "
                "Leitweg-ID oder Käuferreferenz",
                "Kunden (Belege)"
                + (
                    ", Steuerberater (DATEV-Export)"
                    if Datev.laden().beraternummer
                    else ""
                )
                + ", Finanzamt bei einer Prüfung",
                BELEG_FRISTEN,
            ),
            _taetigkeit(
                "Lieferanten und Eingangsrechnungen",
                "Prüfung, Bezahlung und Aufbewahrung empfangener Rechnungen",
                "Art. 6 Abs. 1 lit. b DSGVO (Vertrag), lit. c (§ 147 AO)",
                "Lieferanten und deren Ansprechpartner",
                "Name, Anschrift, USt-IdNr., Bankverbindung und Inhalt der Rechnungen",
                "Finanzamt bei einer Prüfung",
                "Eingangsrechnungen 8 Jahre ab Ende des Kalenderjahres (§ 147 AO).",
            ),
            _taetigkeit(
                "Benutzer und Änderungsprotokoll",
                "Zugang zu Kontorfreund, Nachvollziehbarkeit aller Änderungen",
                "Art. 6 Abs. 1 lit. c DSGVO (§ 146 Abs. 4 AO), lit. f (Schutz vor "
                "unbefugtem Zugriff)",
                "Inhaber und Mitarbeiter",
                "Name, E-Mail-Adresse, Kennwort als Hash, Rolle, Anmeldungen und "
                "Fehlversuche, Änderungen mit Zeitpunkt",
                "keine",
                "Benutzer werden abgeschaltet statt gelöscht, damit das Protokoll "
                "nachvollziehbar bleibt. Protokolleinträge zu gelöschten Daten werden "
                "geschwärzt.",
            ),
            firma.mail_bereit
            and _taetigkeit(
                "Versand von Belegen per E-Mail",
                "Versand von Angeboten, Rechnungen und Mahnungen an die Kunden",
                "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
                "Kunden und deren Ansprechpartner",
                "E-Mail-Adresse, Nachricht, Beleg als Anhang",
                f"E-Mail-Anbieter des Unternehmens (Postausgang {firma.mail_server})",
                "Die Nachricht selbst speichert Kontorfreund nicht, nur Zeitpunkt und "
                "Empfänger am Beleg.",
            ),
            telegram.verbunden
            and _taetigkeit(
                "Benachrichtigungen über Telegram",
                "Erinnerung des Inhabers an Termine, fällige Wiedervorlagen und "
                "Zahlungen; auf seinen Knopfdruck Versand von Rechnungen und Mahnungen "
                "und Buchung von Zahlungen",
                "Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse an der eigenen "
                "Arbeitsorganisation)",
                "Inhaber; Personen, deren Namen im Titel einer Wiedervorlage stehen",
                "Titel und Uhrzeit von Wiedervorlagen, Nummern und Beträge offener "
                "Rechnungen mit fälliger Mahnstufe und fälliger Eingangsrechnungen, "
                "Bezeichnungen von Verträgen; ohne Namen von Kunden und Lieferanten",
                "Telegram (Server auch außerhalb der EU)",
                "Nachrichten liegen im Telegram-Konto des Inhabers; er löscht sie dort.",
            ),
            teil(
                "Weitere Verarbeitungen außerhalb von Kontorfreund",
                antwort(angaben, "weitere_verarbeitungen"),
            ),
        ),
        abschnitt(
            "Technische und organisatorische Maßnahmen",
            teil(
                "Vertraulichkeit",
                punkte(
                    _zugang(),
                    "Anmeldung mit E-Mail-Adresse und Kennwort von mindestens 12 Zeichen; "
                    "Kennwörter aus Datenlecks oder aus Firmen- und Benutzernamen werden "
                    "abgelehnt, gespeichert nur als Argon2-Hash. Ein vom Inhaber "
                    "vergebenes Kennwort wird bei der ersten Anmeldung ersetzt.",
                    "Nach fünf Fehlversuchen ist das Konto 15 Minuten gesperrt; "
                    f"Abmeldung nach {settings.SESSION_COOKIE_AGE // 3600} Stunden ohne "
                    f"Nutzung, spätestens {HOECHSTENS // 3600} Stunden nach der Anmeldung.",
                    f"Zwei-Faktor-Anmeldung eingeschaltet für {zwei_faktor} von {aktiv} "
                    f"Benutzer{'n' if aktiv != 1 else ''}.",
                    "Rollen Inhaber, Mitarbeiter und Prüfer. " + NUR_INHABER,
                    PRUEFER,
                    "Gesperrte Adressen erscheinen in keiner Liste und Suche und sind nur "
                    "für den Inhaber einsehbar.",
                    _keine_uebermittlung(),
                ),
            ),
            teil(
                "Integrität",
                punkte(
                    "Festgeschriebene Belege sind gegen Änderung und Löschung gesperrt.",
                    "Prüfsumme SHA-256 zu jeder abgelegten Datei, tägliche Prüfung.",
                    "Änderungsprotokoll mit Zeitpunkt, Benutzer, altem und neuem Wert, im "
                    "Programm nicht änderbar.",
                ),
            ),
            teil(
                "Verfügbarkeit und Belastbarkeit",
                punkte(
                    "Tägliche Sicherung von Datenbank und Ablage, verschlüsselt mit "
                    f"AES-256-GCM; aufbewahrt werden die letzten {stand['aufbewahren']}."
                    if stand["eingerichtet"]
                    else "Die Datensicherung ist noch nicht eingerichtet.",
                    stand["eingerichtet"]
                    and (
                        f"Zweiter Speicherort: {stand['ziel']}."
                        if stand["ziel"]
                        else "Kein zweiter Speicherort eingerichtet; die Sicherungen "
                        "liegen nur auf diesem Rechner."
                    ),
                    "Sicherung vor jeder Umstellung der Datenbank auf eine neue Version.",
                    "Wiederherstellung mit Vorschau; einzelne Belegdateien lassen sich "
                    "aus der Sicherung zurückholen.",
                ),
            ),
            teil(
                "Löschung und Einschränkung",
                punkte(
                    "Auskunft über alle Daten einer Person als PDF und JSON "
                    "(Art. 15 DSGVO).",
                    "Löschen auf Verlangen, wenn keine Aufbewahrungsfrist mehr läuft "
                    "(Art. 17 DSGVO), sonst Sperren (Art. 18 DSGVO).",
                    "Jährlicher Vorschlag, Belege nach Ablauf der Frist zu löschen.",
                    "Gesamtexport aller Daten in offenen Formaten (Art. 20 DSGVO).",
                ),
            ),
            teil(
                "Regelmäßige Überprüfung",
                punkte(
                    "Kontorfreund prüft täglich die Ablage und warnt, wenn die letzte "
                    "Sicherung älter als 7 Tage ist.",
                    "Der Inhaber prüft dieses Verzeichnis, wenn sich etwas ändert, "
                    "mindestens einmal im Jahr.",
                ),
            ),
            teil(
                "Am Arbeitsplatz",
                punkte(*am_platz)
                if am_platz
                else {
                    "offen": "Welche Maßnahmen schützen Rechner und Akten? Kreuzen Sie sie "
                    "in Kontorfreund an."
                },
            ),
        ),
    ]
