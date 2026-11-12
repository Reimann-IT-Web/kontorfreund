// Briefkopf auf Seite 1 (Spezifikation B-6), gemeinsam für die Belege (rechnung.typ) und den
// Auskunftsbrief (contacts/typst/auskunft.typ). Die Einstellungen kommen als `d.briefkopf` aus
// invoicing/beleg.py (kopf_druck). Fehlen sie, entsteht der bisherige Kopf: Logo 12 mm hoch
// links, daneben Firmenname und Zusatz, rechts Anschrift, darunter die Linie.

#let zeilen(liste) = liste.join(linebreak())

// Der Infoblock rechts beginnt 50 mm unter der Blattkante. Ein Kopfbild endet spätestens hier,
// die Linie 2 mm darunter. Das Logo begrenzt core.models.LOGO_MM: Unter Logo und Angaben folgen
// noch 2 mm und der Absatzabstand (1,1em), bevor die Linie kommt.
#let kopf-ende = 44mm

#let einstellungen(d) = {
  let k = d.at("briefkopf", default: none)
  if k == none { (:) } else { k }
}

#let akzentfarbe(d) = rgb(einstellungen(d).at("farbe", default: "#1d5f6e"))

#let logo-setzen(daten, hoehe, breite) = {
  if breite == none {
    image(bytes(daten), height: hoehe)
  } else {
    // Ein sehr breites Logo wird schmaler statt die Angaben daneben zu verdrängen.
    context {
      let bild = image(bytes(daten), height: hoehe)
      if measure(bild).width > breite { image(bytes(daten), width: breite) } else { bild }
    }
  }
}

// Bild und Linie stehen an festen Stellen; im Textfluss bleibt nur der Platz bis unter die Linie.
#let kopfbild-setzen(daten, k, ausrichtung, rand, akzent) = context {
  let seite = k.at("breite", default: "text") == "seite"
  let breite = if seite { 210mm } else { 210mm - rand.left - rand.right }
  // Oberkante von der Blattkante: über die ganze Seite ab der Kante, sonst am Rand.
  let oben = if seite { 0mm } else { rand.top }
  let hoechstens = kopf-ende - oben
  let voll = image(bytes(daten), width: breite)
  let zu-hoch = measure(voll).height > hoechstens
  let bild = if zu-hoch { image(bytes(daten), height: hoechstens) } else { voll }
  let unten = calc.max(0mm, oben + calc.min(measure(voll).height, hoechstens) - rand.top)
  place(
    top + left,
    dx: if seite { -rand.left } else { 0mm },
    dy: oben - rand.top,
    box(width: breite, align(ausrichtung, bild)),
  )
  if k.at("linie", default: true) {
    place(top + left, dy: unten + 2mm, line(length: 100%, stroke: 0.6pt + akzent))
  }
  v(unten + 2mm + 0.6pt)
}

#let briefkopf(d, akzent, leise, rand) = {
  let k = einstellungen(d)
  let lage = k.at("lage", default: "links")
  let ausrichtung = (links: left, mitte: center, rechts: right).at(lage)
  let kopfbild = d.at("kopfbild", default: none)

  if k.at("art", default: "logo") == "bild" and kopfbild != none {
    kopfbild-setzen(kopfbild, k, ausrichtung, rand, akzent)
  } else {
    let name = if k.at("name", default: true) {
      stack(
        spacing: 2.2mm,
        text(size: 15pt, weight: "bold", fill: akzent, d.absender_name),
        ..if d.marke != "" { (text(size: 10pt, fill: leise, d.marke),) },
      )
    } else { [] }
    let anschrift = if k.at("anschrift", default: true) {
      text(size: 8.5pt, fill: leise, zeilen(d.kopf))
    } else { [] }

    if d.logo == none {
      grid(
        columns: (1fr, auto),
        column-gutter: 4mm,
        align: (left + bottom, right + bottom),
        name,
        anschrift,
      )
    } else {
      let breite = k.at("logo_breite", default: none)
      let logo = logo-setzen(
        d.logo,
        k.at("logo_hoehe", default: 12) * 1mm,
        if breite == none { none } else { breite * 1mm },
      )
      if lage == "rechts" {
        grid(
          columns: (1fr, auto, auto),
          column-gutter: 4mm,
          align: (left + horizon, right + bottom, right + horizon),
          name,
          anschrift,
          logo,
        )
      } else if lage == "mitte" {
        grid(
          columns: (1fr, auto, 1fr),
          column-gutter: 4mm,
          align: (left + horizon, center + horizon, right + bottom),
          name,
          logo,
          anschrift,
        )
      } else {
        grid(
          columns: (auto, 1fr, auto),
          column-gutter: 4mm,
          align: (left + horizon, left + horizon, right + bottom),
          logo,
          name,
          anschrift,
        )
      }
    }
    v(2mm)
    if k.at("linie", default: true) {
      line(length: 100%, stroke: 0.6pt + akzent)
    }
  }
}

// Der Inhalt beginnt 64 mm unter dem Kopf, aber nie früher als 74 mm unter dem oberen Rand:
// Ein flacher Kopf darf den Text nicht ins Anschriftfeld oder den Infoblock ziehen.
#let abstand-zum-inhalt(rand) = context {
  v(calc.max(64mm, rand.top + 74mm - here().position().y))
}
