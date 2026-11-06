// Rechnung oder Angebot nach DIN 5008 Form B. Alle Texte kommen fertig formatiert aus Python (beleg.py)
// und werden als reiner Text gesetzt, nie als Typst-Code ausgewertet.

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
    if d.entwurf {
      place(center + horizon, rotate(-35deg, text(
        size: 110pt,
        weight: "bold",
        fill: luma(236),
        "ENTWURF",
      )))
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
#if d.betreff != "" [
  #v(-2mm)
  #text(size: 11pt, d.betreff)
]
// Fehlt bei Mahnungen und älteren Belegen.
#if d.at("lieferanschrift", default: none) != none [
  #v(-2mm)
  #text(size: 9pt, fill: leise, "Lieferanschrift: " + d.lieferanschrift)
]
#v(2mm)

#for absatz in d.kopftext { par(zeilen(absatz)) }

#v(1mm)
// Mahnungen haben statt Positionen eine Aufstellung der Forderung: (Text, Betrag).
#if "aufstellung" in d {
  table(
    columns: (1fr, 30mm),
    column-gutter: 2.5mm,
    inset: (x: 0pt, y: 5.5pt),
    stroke: none,
    align: (left, right),
    table.header(
      ..([Forderung], [Betrag]).map(t => text(size: 8.5pt, fill: leise, t)),
      table.hline(stroke: 0.6pt + tinte),
    ),
    ..d.aufstellung.map(((posten, betrag)) => (posten, betrag, table.hline(stroke: 0.4pt + linie))).flatten(),
  )
}
// Zahlenspalten so breit wie ihr Inhalt; die Leistung bekommt den Rest.
#if d.positionen.len() > 0 { table(
  columns: (7mm, 1fr, auto, auto, auto),
  column-gutter: 5mm,
  inset: (x: 0pt, y: 5.5pt),
  stroke: none,
  align: (left, left, right, right, right),
  table.header(
    ..([Pos.], [Leistung], [Menge], [Einzelpreis], [Gesamt]).map(t => text(size: 8.5pt, fill: leise, t)),
    table.hline(stroke: 0.6pt + tinte),
  ),
  ..d.positionen
    .map(p => (
      p.nr,
      {
        text(weight: "bold", p.bezeichnung)
        if p.beschreibung.len() > 0 {
          linebreak()
          text(size: 9pt, fill: leise, zeilen(p.beschreibung))
        }
      },
      p.menge,
      p.preis,
      p.gesamt,
      table.hline(stroke: 0.4pt + linie),
    ))
    .flatten(),
) }

#align(right, block(width: 80mm, breakable: false, grid(
  columns: (1fr, auto),
  column-gutter: 6mm,
  row-gutter: 7pt,
  ..d.summen.flatten(),
  grid.hline(stroke: 0.6pt + tinte),
  text(size: 11pt, weight: "bold", d.summe_titel),
  text(size: 11pt, weight: "bold", d.brutto),
)))

#if d.steuerhinweis != "" [
  #v(1mm)
  #d.steuerhinweis
]

#v(2mm)
#block(breakable: false, grid(
  columns: if d.girocode != none { (1fr, 24mm) } else { (1fr,) },
  column-gutter: 6mm,
  align: (left + top, center + top),
  zeilen(d.zahlung),
  ..if d.girocode != none {
    (
      {
        image(bytes(d.girocode), width: 22mm)
        v(-1mm)
        text(size: 7pt, fill: leise, "GiroCode")
      },
    )
  },
))

#v(2mm)
#for absatz in d.fusstext { par(zeilen(absatz)) }
