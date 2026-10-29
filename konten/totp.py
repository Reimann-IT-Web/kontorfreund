"""Einmalcodes für Authenticator-Apps nach RFC 6238 (TOTP), ohne Fremdbibliothek."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

import segno

SCHRITT = 30  # Sekunden je Code
STELLEN = 6


def neues_geheimnis():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code(geheimnis, schritt):
    digest = hmac.new(
        base64.b32decode(geheimnis), struct.pack(">Q", schritt), hashlib.sha1
    ).digest()
    versatz = digest[-1] & 0x0F
    zahl = struct.unpack(">I", digest[versatz : versatz + 4])[0] & 0x7FFFFFFF
    return f"{zahl % 10**STELLEN:0{STELLEN}d}"


def pruefen(geheimnis, eingabe, zuletzt=0, jetzt=None):
    """Zeitschritt des passenden Codes, sonst None.

    Ein Schritt Toleranz in jede Richtung gleicht abweichende Uhren aus; ein schon
    benutzter oder älterer Schritt gilt nicht noch einmal.
    """
    eingabe = "".join(eingabe.split())
    if not (eingabe.isdigit() and len(eingabe) == STELLEN):
        return None
    aktuell = int((time.time() if jetzt is None else jetzt) // SCHRITT)
    for schritt in (aktuell - 1, aktuell, aktuell + 1):
        if schritt > zuletzt and hmac.compare_digest(code(geheimnis, schritt), eingabe):
            return schritt
    return None


def einrichtungsadresse(geheimnis, konto, aussteller):
    """otpauth-Adresse, die Authenticator-Apps aus dem QR-Code lesen."""
    return (
        f"otpauth://totp/{quote(aussteller)}:{quote(konto)}"
        f"?secret={geheimnis}&issuer={quote(aussteller)}"
    )


def qr_bild(adresse):
    return segno.make(adresse, error="m").svg_data_uri(scale=5, border=2)
