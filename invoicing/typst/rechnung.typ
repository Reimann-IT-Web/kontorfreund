// Rechnung oder Angebot nach DIN 5008 Form B. Alle Texte kommen fertig formatiert aus Python (beleg.py)
// und werden als reiner Text gesetzt, nie als Typst-Code ausgewertet.

#import "kopf.typ": abstand-zum-inhalt, akzentfarbe, briefkopf

#let d = json(bytes(sys.inputs.daten))

#let akzent = akzentfarbe(d)
#let tinte = rgb("#1f2326")
#let leise = rgb("#61686c")
#let linie = rgb("#d5d2cb")
#let zeilen(liste) = liste.join(linebreak())
#let rand = (left: 25mm, right: 20mm, top: 20mm, bottom: 34mm)
#let satzbreite = 210mm - rand.left - rand.right

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
  margin: rand,
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

// ---------- Kopf (nur Seite 1, kopf.typ) ----------

#briefkopf(d, akzent, leise, rand)

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

#abstand-zum-inhalt(rand)

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
// Eine Position bleibt auf einer Seite. Ist sie höher als 60 mm, trennt die Seite nur zwischen zwei
// Zeilen der Beschreibung. Nur was selbst höher ist, darf reißen, sonst liefe es über den Seitenrand.
#let leistung(p) = layout(platz => context {
  let ganz = {
    text(weight: "bold", p.bezeichnung)
    if p.beschreibung.len() > 0 {
      linebreak()
      text(size: 9pt, fill: leise, zeilen(p.beschreibung))
    }
  }
  let hoch(inhalt) = measure(inhalt, width: platz.width).height > 60mm
  if not hoch(ganz) {
    block(breakable: false, ganz)
  } else {
    let abstand = par.leading.to-absolute()
    set par(leading: abstand)
    set block(spacing: abstand)
    block(sticky: true, text(weight: "bold", p.bezeichnung))
    for zeile in p.beschreibung {
      let inhalt = text(size: 9pt, fill: leise, if zeile == "" { hide[x] } else { zeile })
      block(breakable: hoch(inhalt), inhalt)
    }
  }
})

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
      leistung(p),
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
  ..(d.summe_titel, d.brutto).map(t => grid.cell(inset: (top: 5pt), text(size: 11pt, weight: "bold", t))),
)))

#if d.steuerhinweis != "" [
  #v(1mm)
  #d.steuerhinweis
]

// Unterschrift: Quer- wie Hochformat passen in 60 × 16 mm.
#let unterschrift = d.unterschrift != none or d.unterschrift_text.len() > 0
#let signatur = {
  if d.unterschrift != none {
    context {
      let groesse = measure(image(bytes(d.unterschrift)))
      let faktor = calc.min(60mm / groesse.width, 16mm / groesse.height)
      image(bytes(d.unterschrift), width: groesse.width * faktor)
    }
  }
  if d.unterschrift_text.len() > 0 { par(zeilen(d.unterschrift_text)) }
}
#let schluss = {
  for absatz in d.fusstext { par(zeilen(absatz)) }
  if unterschrift { signatur }
}

#v(2mm)
// Der Zahlungshinweis wechselt mit dem Schluss die Seite, damit Gruß und Name nie allein auf der
// letzten Seite stehen.
#block(breakable: false, sticky: d.fusstext.len() > 0 or unterschrift, grid(
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
// Schlusstext und Unterschrift bleiben bis 60 mm Höhe auf einer Seite. Ein längerer Schluss trennt wie
// eine lange Position nur zwischen zwei Zeilen; die letzten beiden Zeilen mit Text (Gruß und Name)
// bleiben beisammen und bei der Unterschrift. Leere Zeilen behalten ihre Höhe: Aus dem Browser kommen
// Absätze als Zeilen mit einer Leerzeile dazwischen.
#context if measure(schluss, width: satzbreite).height <= 60mm {
  block(above: 1.1em, breakable: false, schluss)
} else {
  let liste = ()
  for (i, absatz) in d.fusstext.enumerate() {
    for (j, zeile) in absatz.enumerate() {
      liste.push((zeile, if j > 0 { par.leading } else if i > 0 { par.spacing } else { 1.1em }))
    }
  }
  let gefuellt = range(liste.len()).filter(k => liste.at(k).first() != "")
  let letzte = gefuellt.at(-1, default: liste.len())
  let gruss = gefuellt.at(-2, default: letzte)
  {
    set block(spacing: par.leading)
    for (k, (zeile, abstand)) in liste.enumerate() {
      let inhalt = if zeile == "" { hide[x] } else { zeile }
      block(
        above: abstand,
        breakable: measure(inhalt, width: satzbreite).height > 60mm,
        sticky: gruss <= k and (k < letzte or unterschrift),
        inhalt,
      )
    }
  }
  if unterschrift {
    block(above: 1.1em, breakable: measure(signatur, width: satzbreite).height > 60mm, signatur)
  }
}
