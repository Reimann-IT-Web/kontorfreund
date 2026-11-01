// Auskunft nach Art. 15 DSGVO als Brief nach DIN 5008 Form B, im Aussehen der Rechnung
// (invoicing/typst/rechnung.typ). Alle Texte kommen fertig formatiert aus
// contacts/datenschutz.py und werden als reiner Text gesetzt, nie als Typst-Code ausgewertet.

#let d = json(bytes(sys.inputs.daten))

#let akzent = rgb("#1d5f6e")
#let tinte = rgb("#1f2326")
#let leise = rgb("#61686c")
#let linie = rgb("#d5d2cb")
#let zeilen(liste) = liste.join(linebreak())

#set document(title: d.titel, author: d.absender_name)
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
  margin: (left: 25mm, right: 20mm, top: 20mm, bottom: 34mm),
  background: {
    // Falz- und Lochmarken
    for (y, laenge) in ((105mm, 4mm), (148.5mm, 6mm), (210mm, 4mm)) {
      place(top + left, dx: 5mm, dy: y, line(length: laenge, stroke: 0.4pt + linie))
    }
  },
  footer: context {
    set text(size: 7.5pt, fill: leise)
    line(length: 100%, stroke: 0.4pt + linie)
    v(1pt)
    grid(
      columns: (1fr, 1fr, 1.25fr),
      column-gutter: 6mm,
      ..d.fuss.map(zeilen),
    )
    let seiten = counter(page).final().first()
    if seiten > 1 {
      align(right)[Seite #counter(page).display() von #seiten]
    }
  },
)

// ---------- Kopf (nur Seite 1) ----------

#grid(
  columns: if d.logo != none { (auto, 1fr, auto) } else { (1fr, auto) },
  column-gutter: 4mm,
  align: if d.logo != none {
    (left + horizon, left + horizon, right + bottom)
  } else { (left + bottom, right + bottom) },
  ..if d.logo != none { (image(bytes(d.logo), height: 12mm),) },
  stack(
    spacing: 2.2mm,
    text(size: 15pt, weight: "bold", fill: akzent, d.absender_name),
    ..if d.marke != "" { (text(size: 10pt, fill: leise, d.marke),) },
  ),
  text(size: 8.5pt, fill: leise, zeilen(d.kopf)),
)
#v(2mm)
#line(length: 100%, stroke: 0.6pt + akzent)

// Anschriftfeld: 45 mm von oben, 20 mm von links; Rücksendeangabe in der unteren Zeile der Vermerkzone.
#place(top + left, dx: -5mm, dy: 37mm, block(width: 85mm)[
  #text(size: 7pt, fill: leise, d.ruecksende)
  #v(3mm, weak: false)
  #zeilen(d.empfaenger)
])

// Informationsblock rechts
#place(top + right, dy: 30mm, block(width: 66mm, grid(
  columns: (auto, 1fr),
  column-gutter: 4mm,
  row-gutter: 5.5pt,
  align: (left, right),
  ..d.info.map(((name, wert)) => (text(fill: leise, name), wert)).flatten(),
)))

#v(64mm)

// ---------- Inhalt ----------

#text(size: 16pt, weight: "bold", d.titel)
#v(2mm)

#for absatz in d.kopftext { par(zeilen(absatz)) }

// Jeder Abschnitt hat Felder (Name, Zeilen), eine Tabelle (Spalten, Zeilen mit Zellen aus
// Zeilen; `breit` und `rechts` sind Spaltennummern) oder Absätze.
#for a in d.abschnitte {
  v(4mm)
  block(sticky: true, below: 3mm, text(size: 11pt, weight: "bold", fill: akzent, a.titel))
  if "felder" in a {
    grid(
      columns: (48mm, 1fr),
      column-gutter: 4mm,
      row-gutter: 5.5pt,
      ..a.felder.map(((name, wert)) => (text(fill: leise, name), zeilen(wert))).flatten(),
    )
  }
  if "zeilen" in a {
    table(
      columns: range(a.spalten.len()).map(i => if i in a.breit { 1fr } else { auto }),
      column-gutter: 3mm,
      inset: (x: 0pt, y: 4.5pt),
      stroke: none,
      align: range(a.spalten.len()).map(i => if i in a.rechts { right } else { left }),
      table.header(
        ..a.spalten.map(t => text(size: 8.5pt, fill: leise, t)),
        table.hline(stroke: 0.6pt + tinte),
      ),
      ..a.zeilen.map(z => (..z.map(zeilen), table.hline(stroke: 0.4pt + linie))).flatten(),
    )
  }
  if "absaetze" in a {
    for absatz in a.absaetze { par(zeilen(absatz)) }
  }
}

#v(4mm)
#for absatz in d.fusstext { par(zeilen(absatz)) }
