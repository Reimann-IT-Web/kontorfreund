// Kontorfreund – kleine Helfer ohne Framework und ohne Inline-Skripte (CSP).
"use strict";

const ansage = (text) => {
  const region = document.querySelector("[data-announce]");
  if (region) region.textContent = text;
};

// ---------- Hell / Dunkel ----------

const themeKnopf = document.querySelector("[data-theme-toggle]");
if (themeKnopf) {
  const root = document.documentElement;
  const istDunkel = () =>
    root.dataset.theme === "dark" ||
    (!root.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  themeKnopf.setAttribute("aria-pressed", String(istDunkel()));
  themeKnopf.addEventListener("click", () => {
    const neu = istDunkel() ? "light" : "dark";
    root.dataset.theme = neu;
    try {
      localStorage.setItem("kf-theme", neu);
    } catch {
      // Wahl gilt dann nur für diese Seite.
    }
    themeKnopf.setAttribute("aria-pressed", String(neu === "dark"));
  });
}

// ---------- Navigation auf schmalen Bildschirmen ----------

const navKnopf = document.querySelector("[data-nav-toggle]");
const seitenleiste = document.getElementById("navigation");
if (navKnopf && seitenleiste) {
  const setzen = (offen) => {
    seitenleiste.classList.toggle("is-open", offen);
    navKnopf.setAttribute("aria-expanded", String(offen));
  };
  navKnopf.addEventListener("click", (e) => {
    e.stopPropagation();
    const offen = !seitenleiste.classList.contains("is-open");
    setzen(offen);
    if (offen) seitenleiste.querySelector("a").focus();
  });
  document.addEventListener("click", (e) => {
    if (seitenleiste.classList.contains("is-open") && !seitenleiste.contains(e.target)) setzen(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && seitenleiste.classList.contains("is-open")) {
      setzen(false);
      navKnopf.focus();
    }
  });
}

// ---------- Suche (Strg+K) ----------

const palette = document.getElementById("suche");
if (palette) {
  const eingabe = palette.querySelector("[data-palette-input]");
  const treffer = [...palette.querySelectorAll("[data-palette-item]")];
  const leer = palette.querySelector("[data-palette-empty]");
  let aktiv = -1;

  const normal = (text) =>
    text.toLocaleLowerCase("de").normalize("NFD").replace(/\p{Diacritic}/gu, "");
  const sichtbare = () => treffer.filter((li) => !li.hidden);

  const markieren = (index) => {
    const liste = sichtbare();
    treffer.forEach((li) => li.setAttribute("aria-selected", "false"));
    aktiv = liste.length ? (index + liste.length) % liste.length : -1;
    if (aktiv >= 0) {
      liste[aktiv].setAttribute("aria-selected", "true");
      liste[aktiv].scrollIntoView({ block: "nearest" });
      eingabe.setAttribute("aria-activedescendant", liste[aktiv].id);
    } else {
      eingabe.removeAttribute("aria-activedescendant");
    }
  };

  const filtern = () => {
    const suche = normal(eingabe.value.trim());
    treffer.forEach((li) => {
      li.hidden = suche !== "" && !normal(li.textContent).includes(suche);
    });
    leer.hidden = sichtbare().length > 0;
    markieren(0);
  };

  const oeffnen = () => {
    if (palette.open) return;
    palette.showModal();
    eingabe.value = "";
    filtern();
    eingabe.focus();
  };

  document.querySelectorAll("[data-open-search]").forEach((knopf) => knopf.addEventListener("click", oeffnen));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      oeffnen();
    }
  });
  eingabe.addEventListener("input", filtern);
  eingabe.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      markieren(aktiv + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      markieren(aktiv - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const ziel = sichtbare()[aktiv];
      if (ziel) ziel.querySelector("a").click();
    }
  });
  // Klick auf den abgedunkelten Hintergrund schließt die Suche.
  palette.addEventListener("click", (e) => {
    if (e.target === palette) palette.close();
  });
}

// ---------- Zeilen aufklappen, Wiedervorlagen erledigen ----------

document.addEventListener("click", (e) => {
  const aufklappen = e.target.closest("[data-expand]");
  if (aufklappen) {
    const details = document.getElementById(aufklappen.getAttribute("aria-controls"));
    const offen = aufklappen.getAttribute("aria-expanded") === "true";
    aufklappen.setAttribute("aria-expanded", String(!offen));
    details.hidden = offen;
    aufklappen.closest("tr").classList.toggle("is-open", !offen);
    return;
  }

  const erledigen = e.target.closest("[data-done]");
  if (erledigen) {
    const zeile = erledigen.closest("[data-task]");
    const erledigt = !zeile.classList.contains("is-done");
    zeile.classList.toggle("is-done", erledigt);
    ansage(erledigt ? "Wiedervorlage erledigt. Mit „Rückgängig“ nehmen Sie das zurück." : "Wiedervorlage wieder offen.");
  }
});

// ---------- Auswahlfelder, die ihr Formular sofort absenden ----------

document.querySelectorAll("[data-auto-submit]").forEach((feld) => {
  feld.addEventListener("change", () => feld.form.requestSubmit());
});

// ---------- Dateien hineinziehen (Spezifikation K-3) ----------

const ablagen = document.querySelectorAll("[data-ablage]");
ablagen.forEach((zone) => {
  const feld = zone.querySelector("input[type=file]");
  zone.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    zone.classList.add("is-ziel");
  });
  zone.addEventListener("dragleave", (e) => {
    if (!zone.contains(e.relatedTarget)) zone.classList.remove("is-ziel");
  });
  zone.addEventListener("drop", (e) => {
    zone.classList.remove("is-ziel");
    if (!e.dataTransfer.files.length) return;
    e.preventDefault();
    feld.files = e.dataTransfer.files;
    const anzahl = feld.files.length === 1 ? "1 Datei" : `${feld.files.length} Dateien`;
    if (zone.hasAttribute("data-sofort")) {
      ansage(`${anzahl} werden hochgeladen.`);
      feld.form.requestSubmit();
    } else {
      ansage(`${anzahl} ausgewählt.`);
    }
  });
});
// Daneben fallen gelassen, würde der Browser die Datei öffnen und die Seite verlassen.
if (ablagen.length) {
  for (const art of ["dragover", "drop"]) {
    window.addEventListener(art, (e) => {
      if (e.target.closest?.("[data-ablage]")) return;
      e.preventDefault();
      if (art === "dragover") e.dataTransfer.dropEffect = "none";
    });
  }
}

// ---------- Adressformular: Firmenfeld nur bei Firmen ----------

const kontaktForm = document.querySelector("[data-kontakt-form]");
if (kontaktForm) {
  const titel = kontaktForm.querySelector("[data-titel-firma]");
  const nurFirma = kontaktForm.querySelectorAll("[data-nur-firma]");
  const umschalten = () => {
    const firma = kontaktForm.querySelector("[name=art]:checked")?.value !== "person";
    nurFirma.forEach((el) => {
      el.hidden = !firma;
    });
    titel.textContent = firma ? titel.dataset.titelFirma : titel.dataset.titelPerson;
  };
  kontaktForm.addEventListener("change", (e) => {
    if (e.target.name === "art") umschalten();
  });
  umschalten();
}

// ---------- Anschrift: Ort zur Postleitzahl ----------

// Bei einer deutschen PLZ trägt Kontorfreund den Ort ein, solange er nicht von Hand
// geändert wurde. Teilen sich mehrere Orte die PLZ, stehen sie im Feld Ort zur Auswahl.
document.querySelectorAll("[data-plz]").forEach((plz) => {
  const ort = plz.form.querySelector("[data-ort]");
  const land = plz.form.querySelector("[data-land]");
  if (!ort) return;
  const vorschlaege = document.createElement("datalist");
  vorschlaege.id = `${ort.id}-vorschlaege`;
  ort.setAttribute("list", vorschlaege.id);
  const hinweis = document.createElement("p");
  hinweis.className = "hint";
  hinweis.hidden = true;
  hinweis.setAttribute("aria-live", "polite");
  ort.after(vorschlaege, hinweis);
  let vonHand = false;
  ort.addEventListener("input", () => {
    vonHand = true;
  });
  plz.addEventListener("input", async () => {
    const wert = plz.value.trim();
    vorschlaege.replaceChildren();
    hinweis.hidden = true;
    if (!/^\d{5}$/.test(wert) || !/^(deutschland|germany|de)?$/i.test(land?.value.trim() ?? "")) return;
    let daten;
    try {
      const antwort = await fetch(`${plz.dataset.plz}?plz=${wert}`);
      if (!antwort.ok) return;
      daten = await antwort.json();
    } catch {
      return; // Dann trägt man den Ort selbst ein.
    }
    if (plz.value.trim() !== wert) return; // inzwischen weitergetippt
    vorschlaege.replaceChildren(...daten.orte.map((o) => new Option(o)));
    if (vonHand) return;
    if (daten.ort) {
      ort.value = daten.ort;
    } else if (daten.orte.length > 1) {
      if (!daten.orte.includes(ort.value)) ort.value = "";
      hinweis.textContent = `Zur PLZ ${wert} gehören mehrere Orte. Wählen Sie den richtigen im Feld Ort aus.`;
      hinweis.hidden = false;
    }
  });
});

// ---------- Rechnung, Angebot und Auftragsbestätigung: rechnen und Pflichtangaben prüfen ----------

const rechnung = document.querySelector("[data-invoice]");
if (rechnung) {
  const angebot = rechnung.dataset.beleg === "angebot";
  const auftrag = rechnung.dataset.beleg === "auftrag";
  const euro = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
  const zahl = (text) => {
    const wert = Number(String(text).trim().replace(/\./g, "").replace(",", "."));
    return Number.isFinite(wert) ? wert : 0;
  };
  const cent = (wert) => Math.round(wert * 100) / 100;
  const feld = (name) => rechnung.elements[name];
  const tbody = rechnung.querySelector("[data-positions]");
  const vorlage = document.getElementById("position-vorlage");
  const festschreibenDialog = document.querySelector("[data-abschluss-dialog]");

  const STEUERHINWEIS = {
    kleinunternehmer: "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
    regel: "",
    "13b": "Steuerschuldnerschaft des Leistungsempfängers.",
  };
  const PRUEFPUNKT = {
    empfaenger: "Empfänger mit Anschrift",
    absender: "Ihre Firmendaten",
    datum: "Rechnungsdatum",
    leistung: "Menge und Art der Leistung",
    zeitraum: "Leistungszeitraum",
    entgelt: "Rechnungsbetrag",
    xrechnung: "Angaben für die XRechnung",
  };
  // Rechnungskorrektur: nur Minderungen (negative Mengen), höchstens um den offenen Betrag.
  const korrektur = rechnung.dataset.korrektur;
  if (korrektur) PRUEFPUNKT.entgelt = "Korrekturbetrag";
  if (angebot) {
    PRUEFPUNKT.datum = "Angebotsdatum";
    PRUEFPUNKT.entgelt = "Angebotsbetrag";
  }
  if (auftrag) {
    PRUEFPUNKT.datum = "Datum";
    PRUEFPUNKT.entgelt = "Auftragssumme";
  }
  const abschluss = angebot || auftrag ? ["fertigstellen", "Fertigstellen"] : ["festschreiben", "Festschreiben"];

  const pruefen = (ergebnis) => {
    const punkte = [...rechnung.querySelectorAll("[data-check]")].filter((li) => !li.hidden);
    const fehlt = [];
    punkte.forEach((li) => {
      const ok = ergebnis[li.dataset.check] ?? true;
      li.classList.toggle("is-ok", ok);
      li.classList.toggle("is-missing", !ok);
      if (!ok) fehlt.push(PRUEFPUNKT[li.dataset.check]);
    });
    rechnung.querySelector("[data-check-count]").textContent = `${punkte.length - fehlt.length} von ${punkte.length}`;
    const meldung = rechnung.querySelector("[data-check-message]");
    meldung.textContent = fehlt.length
      ? `Es fehlt noch: ${fehlt.join(", ")}.`
      : `Alles vollständig. Sie können ${abschluss[0]}.`;
    meldung.classList.toggle("is-ok", fehlt.length === 0);
    rechnung.querySelector("[data-submit]").disabled = fehlt.length > 0;

    const leiste = rechnung.querySelector("[data-check-bar]");
    leiste.classList.toggle("is-ok", fehlt.length === 0);
    leiste.classList.toggle("is-missing", fehlt.length > 0);
    rechnung.querySelector("[data-check-bar-state]").textContent = fehlt.length
      ? `${punkte.length - fehlt.length} von ${punkte.length} · Es fehlt: ${fehlt.join(", ")}`
      : `${punkte.length} von ${punkte.length} · bereit zum ${abschluss[1]}`;
  };

  const auswahl = feld("kontakt");
  const skontoHinweis = rechnung.querySelector("[data-skonto-hinweis]");
  const ohneSkonto = skontoHinweis?.textContent;
  const verzugshinweis = rechnung.querySelector("[data-verzugshinweis]");
  const karte = rechnung.querySelector("[data-address-card]");
  const anschriftFehlt = rechnung.querySelector("[data-address-missing]");

  // Anschrift des gewählten Empfängers zeigen; liefert, ob sie für eine Rechnung reicht.
  const anschriftZeigen = () => {
    const option = auswahl.selectedOptions[0];
    const gewaehlt = Boolean(option && option.value);
    const zeilen = gewaehlt ? option.dataset.anschrift.split("|") : [];
    karte.replaceChildren(...zeilen.flatMap((zeile, i) => (i ? [document.createElement("br"), zeile] : [zeile])));
    karte.hidden = !gewaehlt;
    const vollstaendig = gewaehlt && option.dataset.vollstaendig === "1";
    anschriftFehlt.hidden = !gewaehlt || vollstaendig;
    if (gewaehlt) anschriftFehlt.querySelector("a").href = `${rechnung.dataset.adressen}${option.value}/`;
    return vollstaendig;
  };

  // Die Anrede im Text folgt dem gewählten Empfänger, solange sie nicht von Hand geändert wurde.
  auswahl.addEventListener("change", () => {
    const anrede = auswahl.selectedOptions[0]?.dataset.briefanrede;
    const kopf = feld("kopftext");
    if (anrede && /^Sehr geehrte/.test(kopf.value)) kopf.value = kopf.value.replace(/^.*$/m, anrede);
  });

  const rechnen = () => {
    let netto = 0;
    let leistungOk = tbody.children.length > 0;
    tbody.querySelectorAll("[data-position]").forEach((zeile, i) => {
      zeile.querySelector("[data-pos-nr]").textContent = i + 1;
      const menge = zahl(zeile.querySelector("[name=menge]").value);
      const gesamt = cent(menge * zahl(zeile.querySelector("[name=preis]").value));
      zeile.querySelector("[data-line-total]").textContent = euro.format(gesamt);
      netto += gesamt;
      if (!zeile.querySelector("[name=bezeichnung]").value.trim() || (korrektur ? menge >= 0 : menge <= 0)) leistungOk = false;
    });
    netto = cent(netto);

    const fall = feld("steuerfall").value;
    const ust = fall === "regel" ? cent(netto * 0.19) : 0;
    const summe = cent(netto + ust);
    rechnung.querySelector("[data-row-netto]").hidden = fall !== "regel";
    rechnung.querySelector("[data-row-ust]").hidden = fall !== "regel";
    rechnung.querySelector("[data-sum-netto]").textContent = euro.format(netto);
    rechnung.querySelector("[data-sum-ust]").textContent = euro.format(ust);
    rechnung.querySelector("[data-sum-total]").textContent = euro.format(summe);
    rechnung.querySelector("[data-sum-side]").textContent = euro.format(summe);
    const steuerhinweis = rechnung.querySelector("[data-tax-note]");
    steuerhinweis.textContent = STEUERHINWEIS[fall];
    steuerhinweis.hidden = !STEUERHINWEIS[fall];

    // Fälligkeit der Rechnung bzw. Gültigkeit des Angebots; die Auftragsbestätigung hat keine Frist.
    const datum = feld("datum").valueAsDate;
    const frist = feld(angebot ? "bindefrist" : "zahlungsziel");
    if (datum && frist) {
      const faellig = new Date(datum);
      faellig.setDate(faellig.getDate() + Number(frist.value));
      const text = faellig.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
      rechnung.querySelectorAll("[data-due]").forEach((el) => {
        el.textContent = text;
      });
    }

    // Skonto zum Mitlesen; ob Frist und Satz passen, prüft der Server.
    if (skontoHinweis) {
      const prozent = zahl(feld("skonto_prozent").value);
      const tage = Number(feld("skonto_tage").value);
      if (datum && prozent > 0 && tage > 0 && summe > 0) {
        const bis = new Date(datum);
        bis.setDate(bis.getDate() + tage);
        const text = bis.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
        skontoHinweis.textContent = `Zahlt der Kunde bis ${text}, überweist er ${euro.format(cent(summe - cent((summe * prozent) / 100)))}.`;
      } else {
        skontoHinweis.textContent = ohneSkonto;
      }
    }

    // Empfänger mit XRechnung: Käuferreferenz aus der Adresse und eigene Pflichtangaben.
    // Angebote und Auftragsbestätigungen kennen keine XRechnung.
    const empfaenger = auswahl.selectedOptions[0];
    const xrechnung = !angebot && !auftrag && empfaenger?.dataset.xrechnung === "1";
    if (verzugshinweis) verzugshinweis.hidden = empfaenger?.dataset.verbraucher !== "1";
    if (!angebot && !auftrag) {
      rechnung.querySelector("[data-check=xrechnung]").hidden = !xrechnung;
      rechnung.querySelector("[data-format]").textContent = xrechnung ? "ZUGFeRD und XRechnung" : "ZUGFeRD";
      feld("referenz").placeholder = empfaenger?.dataset.referenz || "";
    }

    const von = feld("leistung_von")?.value;
    const bis = feld("leistung_bis")?.value;
    pruefen({
      empfaenger: anschriftZeigen(),
      absender: rechnung.dataset.absender === "1",
      datum: Boolean(feld("datum").value),
      leistung: leistungOk,
      zeitraum: Boolean(von) && (!bis || bis >= von),
      entgelt: korrektur ? summe < 0 && -summe <= Number(korrektur) : summe > 0,
      xrechnung: !xrechnung || rechnung.dataset.xrechnungAbsender === "1",
    });
  };

  // Artikelauswahl schließt bei Klick daneben und mit Esc.
  const artikelMenue = rechnung.querySelector("[data-artikel-menue]");
  if (artikelMenue) {
    document.addEventListener("click", (e) => {
      if (!artikelMenue.contains(e.target)) artikelMenue.open = false;
    });
    artikelMenue.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && artikelMenue.open) {
        e.preventDefault();
        artikelMenue.open = false;
        artikelMenue.querySelector("summary").focus();
      }
    });
  }

  // Artikel auch über die Bezeichnung: Wer einen Artikel aus der Liste wählt oder seinen
  // Namen tippt, bekommt Beschreibung, Einheit und Preis dazu. Nur beim Wechsel zu einem
  // anderen Artikel, damit ein geänderter Preis bleibt.
  const artikelListe = document.getElementById("artikel-liste");
  if (artikelListe) {
    tbody.querySelectorAll("[data-position]").forEach((zeile) => {
      zeile.dataset.artikelName = zeile.querySelector("[name=bezeichnung]").value;
    });
    rechnung.addEventListener("input", (e) => {
      if (e.target.name !== "bezeichnung") return;
      const zeile = e.target.closest("[data-position]");
      const gewaehlt = [...artikelListe.options].find((o) => o.value === e.target.value);
      if (!gewaehlt || zeile.dataset.artikelName === gewaehlt.value) return;
      zeile.dataset.artikelName = gewaehlt.value;
      for (const name of ["beschreibung", "einheit", "preis"]) {
        zeile.querySelector(`[name=${name}]`).value = gewaehlt.dataset[name];
      }
      ansage(`Beschreibung, Einheit und Preis von ${gewaehlt.value} übernommen.`);
    });
  }

  rechnung.addEventListener("input", rechnen);
  rechnung.addEventListener("change", rechnen);
  rechnung.addEventListener("click", (e) => {
    if (e.target.closest("[data-add-position]")) {
      tbody.append(vorlage.content.cloneNode(true));
      rechnen();
      tbody.lastElementChild.querySelector("[name=bezeichnung]").focus();
      return;
    }
    // Artikel füllen die letzte Position, wenn sie noch leer ist, sonst eine neue.
    const artikel = e.target.closest("[data-artikel]");
    if (artikel) {
      let zeile = tbody.lastElementChild;
      const leer = ["bezeichnung", "beschreibung", "preis"].every((name) => !zeile.querySelector(`[name=${name}]`).value.trim());
      if (!leer) {
        tbody.append(vorlage.content.cloneNode(true));
        zeile = tbody.lastElementChild;
      }
      for (const name of ["bezeichnung", "beschreibung", "einheit", "preis"]) {
        zeile.querySelector(`[name=${name}]`).value = artikel.dataset[name];
      }
      zeile.dataset.artikelName = artikel.dataset.bezeichnung;
      artikelMenue.open = false;
      rechnen();
      zeile.querySelector("[name=menge]").select();
      ansage(`${artikel.dataset.bezeichnung} eingefügt. Bitte die Menge prüfen.`);
      return;
    }
    const entfernen = e.target.closest("[data-remove-position]");
    if (entfernen) {
      if (tbody.children.length > 1) {
        entfernen.closest("tr").remove();
        rechnen();
        ansage("Position entfernt.");
      } else {
        ansage(`${angebot ? "Ein Angebot" : auftrag ? "Eine Auftragsbestätigung" : "Eine Rechnung"} braucht mindestens eine Position.`);
      }
      return;
    }
    const festschreiben = e.target.closest("[data-submit]");
    if (festschreiben && !festschreiben.disabled) festschreibenDialog.showModal();
  });

  // Aktuellen Schritt in der Schrittleiste markieren.
  const schrittLinks = [...rechnung.querySelectorAll(".steps a")];
  const beobachter = new IntersectionObserver(
    (eintraege) => {
      eintraege
        .filter((eintrag) => eintrag.isIntersecting)
        .forEach((eintrag) => {
          schrittLinks.forEach((link) => {
            if (link.hash === `#${eintrag.target.id}`) link.setAttribute("aria-current", "step");
            else link.removeAttribute("aria-current");
          });
        });
    },
    { rootMargin: "-35% 0px -60% 0px" },
  );
  rechnung.querySelectorAll(".step").forEach((schritt) => beobachter.observe(schritt));

  rechnen();
}

// Sicherheitsabfrage vor endgültigen Aktionen, z. B. dem Löschen eines Entwurfs.
document.addEventListener("click", (e) => {
  const knopf = e.target.closest("[data-confirm]");
  if (knopf && !window.confirm(knopf.dataset.confirm)) e.preventDefault();
});

// Knöpfe mit data-dialog öffnen eine Rückfrage, z. B. vor dem Stornieren.
document.addEventListener("click", (e) => {
  const knopf = e.target.closest("[data-dialog]");
  if (knopf) document.getElementById(knopf.dataset.dialog)?.showModal();
});

// Vorschau nach dem Speichern direkt öffnen.
document.querySelector("dialog[data-open-on-load]")?.showModal();

// Offene Posten: „Zahlung“ in einer Zeile bucht im Dialog statt auf der Rechnungsseite.
const zahlungDialog = document.getElementById("zahlung-dialog");
if (zahlungDialog) {
  const formular = zahlungDialog.querySelector("form");
  document.addEventListener("click", (e) => {
    const knopf = e.target.closest("[data-zahlung]");
    if (!knopf) return;
    e.preventDefault();
    formular.action = knopf.dataset.zahlung;
    formular.elements["zahlung-betrag"].value = knopf.dataset.betrag;
    zahlungDialog.querySelector("[data-zahlung-titel]").textContent = knopf.dataset.titel;
    zahlungDialog.showModal();
    formular.elements["zahlung-betrag"].select();
  });
}

// Firmenwechsel: warten, bis der Server mit der gewählten Firma wieder läuft.
const firmaWarten = document.querySelector("[data-firma-warten]");
if (firmaWarten) {
  const { firmaWarten: adresse, firma, weiter } = firmaWarten.dataset;
  const beginn = Date.now();
  const pruefen = async () => {
    try {
      const antwort = await fetch(adresse, { cache: "no-store" });
      if (antwort.ok && (await antwort.text()) === firma) {
        window.location.href = weiter;
        return;
      }
    } catch {
      // Der Server startet gerade neu.
    }
    if (Date.now() - beginn > 90000) {
      firmaWarten.querySelector("[data-zu-lange]").hidden = false;
      return;
    }
    setTimeout(pruefen, 700);
  };
  setTimeout(pruefen, 1500);
}
