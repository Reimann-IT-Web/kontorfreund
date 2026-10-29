// Gewähltes Design vor dem ersten Zeichnen setzen, damit nichts aufblitzt.
try {
  const theme = localStorage.getItem("kf-theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {
  // Ohne Speicher gilt die Systemeinstellung.
}
