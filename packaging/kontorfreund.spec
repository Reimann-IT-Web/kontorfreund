# PyInstaller: Kontorfreund als Programmordner ohne vorinstalliertes Python.
#
#   uv sync --group paket
#   uv run pyinstaller packaging/kontorfreund.spec --noconfirm
#
# Ergebnis: dist/Kontorfreund/ mit Kontorfreund(.exe). Prüfen mit
# `dist/Kontorfreund/Kontorfreund selbsttest` (APP_DATA_DIR auf einen leeren Ordner).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

WURZEL = Path(SPECPATH).parent
APPS = [
    "config",
    "core",
    "contacts",
    "invoicing",
    "angebote",
    "auftraege",
    "vertraege",
    "zahlungen",
    "artikel",
    "archive",
    "eingang",
    "auswertungen",
    "wiedervorlagen",
    "historie",
    "benachrichtigungen",
    "backups",
    "konten",
    "protokoll",
    "dokumentation",
    "datenzugriff",
    "importe",
]

# Lädt Django erst zur Laufzeit über Namen aus den Einstellungen.
module = ["whitenoise.middleware", "waitress", *collect_submodules("argon2")]
dateien = [
    (str(WURZEL / "templates"), "templates"),
    (str(WURZEL / "static"), "static"),
    (str(WURZEL / "LICENSE"), "."),
]
# Die eigenen Apps sind keine installierten Pakete; Module und Dateien
# (Vorlagen, Typst-Vorlage, Schriften) kommen deshalb direkt aus den Ordnern.
for app in APPS:
    for datei in (WURZEL / app).rglob("*"):
        if not datei.is_file() or "__pycache__" in datei.parts:
            continue
        relativ = datei.relative_to(WURZEL)
        if datei.suffix == ".py":
            module.append(".".join(relativ.with_suffix("").parts).removesuffix(".__init__"))
        else:
            dateien.append((str(datei), str(relativ.parent)))
# Django lädt Kommandos, Migrationen und Sprachdateien über Namen; drafthorse
# braucht seine XML-Schemata.
module += collect_submodules("django", filter=lambda name: ".gis" not in name)
dateien += collect_data_files("django") + collect_data_files("drafthorse")

a = Analysis(
    [str(WURZEL / "kontorfreund.py")],
    pathex=[str(WURZEL)],
    hiddenimports=module,
    datas=dateien,
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kontorfreund",
    icon=str(WURZEL / "static" / "img" / "kontorfreund.ico"),
    console=True,
)
COLLECT(exe, a.binaries, a.datas, name="Kontorfreund")
