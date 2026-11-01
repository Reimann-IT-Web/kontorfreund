"""Django-Einstellungen.

Betriebswerte kommen aus Umgebungsvariablen (APP_*). Ohne Angaben läuft das
Programm als Einzelplatz-Installation mit SQLite im Datenverzeichnis.
"""

import os
import secrets
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", BASE_DIR / "data"))
# Nur für den eigenen Benutzer lesbar (macOS, Linux); Windows schützt den Benutzerordner selbst.
DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
# Mehrere Firmen (core/firmen.py): der Ordner mit allen Firmen und welche hier offen ist.
HAUPTORDNER = Path(os.environ.get("APP_HAUPTORDNER", DATA_DIR))
FIRMA = os.environ.get("APP_FIRMA", "")
# Nur unter dem Startprogramm, das den Server zum Firmenwechsel neu startet.
NEUSTART = os.environ.get("APP_NEUSTART") == "1"

# Marke und Edition getrennt, damit weitere Editionen dieselbe Codebasis nutzen können.
PRODUCT_NAME = "Kontorfreund"
PRODUCT_EDITION = "Kleinunternehmen"
# Wie in pyproject.toml; das Installationspaket kennt die Datei nicht.
VERSION = "0.8.0"

DEBUG = os.environ.get("APP_DEBUG") == "1"
ALLOWED_HOSTS = os.environ.get("APP_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


def _secret_key() -> str:
    """Schlüssel aus der Umgebung.

    Fehlt er, wird er beim ersten Start erzeugt und im Datenverzeichnis abgelegt.
    """
    if key := os.environ.get("APP_SECRET_KEY"):
        return key
    path = DATA_DIR / "secret_key"
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(secrets.token_urlsafe(50))
    return path.read_text(encoding="utf-8").strip()


SECRET_KEY = _secret_key()

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "contacts",
    "invoicing",
    "angebote",
    "auftraege",
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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "protokoll.middleware.anfrage_merken",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "konten.rechte.zwei_faktor_pflicht",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "backups.middleware.taegliche_sicherung",
    "archive.middleware.taegliche_pruefung",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.product",
                "core.context_processors.navigation",
                "backups.context_processors.datensicherung",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}

# Anmeldung per E-Mail und Kennwort (Spezifikation K-5).
AUTH_USER_MODEL = "konten.Benutzer"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = [{"NAME": "konten.kennwort.Kennwortregeln"}]
LOGIN_URL = "konten:anmelden"
# Automatisch abgemeldet nach so vielen Stunden ohne Anfrage.
SESSION_COOKIE_AGE = int(os.environ.get("APP_ABMELDEN_NACH_STUNDEN", "8")) * 3600
SESSION_SAVE_EVERY_REQUEST = True
# Jede Firma hat eigene Anmeldungen, Cookies gelten aber für alle Firmen unter derselben
# Adresse. Mit eigenem Namen bleibt man nach einem Wechsel in jeder Firma angemeldet.
SESSION_COOKIE_NAME = f"sessionid-{FIRMA}" if FIRMA else "sessionid"
# Im Netzwerk erreichbar, sobald andere Adressen als der eigene Rechner erlaubt sind;
# dann ist die Zwei-Faktor-Anmeldung für Inhaber Pflicht.
NETZWERK = any(
    host not in {"localhost", "127.0.0.1", "::1", "[::1]"} for host in ALLOWED_HOSTS
)

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Ohne Debug-Modus liefert WhiteNoise die Dateien direkt aus dem Programmordner aus.
WHITENOISE_USE_FINDERS = True

# Fehler (Status 500) landen in einer Datei im Datenverzeichnis, für die Fehlersuche.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "datei": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": DATA_DIR / "fehler.log",
            "maxBytes": 1_000_000,
            "backupCount": 2,
            "encoding": "utf-8",
            "delay": True,
            "level": "ERROR",
        },
    },
    "root": {"handlers": ["datei"], "level": "ERROR"},
}

# Nur eigene Quellen, keine Inline-Skripte oder -Styles (Spezifikation 02, Sicherheit).
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
