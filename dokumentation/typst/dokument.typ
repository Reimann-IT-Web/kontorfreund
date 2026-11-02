// Verfahrensdokumentation und Verzeichnis von Verarbeitungstätigkeiten, im Aussehen der
// Rechnung (invoicing/typst/rechnung.typ). Alle Texte kommen fertig aus
// dokumentation/fassungen.py und werden als reiner Text gesetzt, nie als Typst-Code
// ausgewertet.

#let d = json(bytes(sys.inputs.daten))

#let akzent = rgb("#1d5f6e")
#let tinte = rgb("#1f2326")
#let leise = rgb("#61686c")
#let linie = rgb("#d5d2cb")
#let offen-grund = rgb("#fbf3e4")
#let offen-rand = rgb("#c98a1b")
#let zeilen(liste) = liste.join(linebreak())

#set document(title: d.titel, author: d.firma)
#set text(
  font: "Atkinson Hyperlegible Next",
  size: 10pt,
  lang: "de",
  fill: tinte,
  number-width: "tabular",
)
#set par(leading: 0.62em, spacing: 1.1em)
#set page(
  paper: "a4",
  margin: (left: 25mm, right: 20mm, top: 20mm, bottom: 24mm),
  footer: context {
    set text(size: 7.5pt, fill: leise)
    line(length: 100%, stroke: 0.4pt + linie)
    v(1pt)
    grid(
      columns: (1fr, auto),
      d.fuss,
      [Seite #counter(page).display() von #counter(page).final().first()],
    )
  },
)
#show heading.where(level: 1): it => block(
  above: 7mm,
  below: 3.5mm,
  sticky: true,
  text(size: 13pt, weight: "bold", fill: akzent, it.body),
)
#show heading.where(level: 2): it => block(
  above: 5mm,
  below: 2.5mm,
  sticky: true,
  text(size: 10.5pt, weight: "bold", it.body),
)

// ---------- Kopf ----------

#text(size: 9pt, fill: leise, d.firma)
#v(1mm)
#text(size: 20pt, weight: "bold", fill: akzent, d.titel)
#v(0.5mm)
#text(size: 11pt, fill: leise, d.untertitel)
#v(4mm)
#grid(
  columns: (32mm, 1fr),
  column-gutter: 4mm,
  row-gutter: 5.5pt,
  ..d.kopf.map(((name, wert)) => (text(fill: leise, name), zeilen(wert))).flatten(),
)
#v(2mm)
#line(length: 100%, stroke: 0.6pt + akzent)
#v(1mm)
#for absatz in d.einleitung { par(absatz) }

#v(2mm)
#outline(title: text(size: 11pt, weight: "bold", fill: akzent, "Inhalt"), depth: 1)

// ---------- Abschnitte ----------

// Blöcke: absatz (Zeilen), punkte, felder (Name, Zeilen), tabelle (Spalten, Zeilen mit
// Zellen aus Zeilen, `breit` sind Spaltennummern), antwort (Angabe des Inhabers, eingerückt)
// oder offen (Frage, die noch fehlt).
#let block-setzen(b) = {
  if "absatz" in b { par(zeilen(b.absatz)) }
  if "punkte" in b { list(..b.punkte) }
  if "felder" in b {
    block(grid(
      columns: (42mm, 1fr),
      column-gutter: 4mm,
      row-gutter: 5.5pt,
      ..b.felder.map(((name, wert)) => (text(fill: leise, name), zeilen(wert))).flatten(),
    ))
  }
  if "tabelle" in b {
    let t = b.tabelle
    table(
      columns: range(t.spalten.len()).map(i => if i in t.breit { 1fr } else { auto }),
      column-gutter: 3mm,
      inset: (x: 0pt, y: 4.5pt),
      stroke: none,
      table.header(
        ..t.spalten.map(s => text(size: 8.5pt, fill: leise, s)),
        table.hline(stroke: 0.6pt + tinte),
      ),
      ..t.zeilen.map(z => (..z.map(zeilen), table.hline(stroke: 0.4pt + linie))).flatten(),
    )
  }
  if "antwort" in b {
    block(
      inset: (left: 4mm, y: 1mm),
      stroke: (left: 1.5pt + linie),
      zeilen(b.antwort),
    )
  }
  if "offen" in b {
    block(
      width: 100%,
      inset: (x: 4mm, y: 3mm),
      fill: offen-grund,
      stroke: (left: 1.5pt + offen-rand),
      [#text(weight: "bold", "Noch offen: ")#b.offen],
    )
  }
}

#for a in d.abschnitte {
  heading(level: 1, a.titel)
  for t in a.teile {
    heading(level: 2, outlined: false, t.titel)
    for b in t.bloecke { block-setzen(b) }
  }
}
