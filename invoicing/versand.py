"""Versand festgeschriebener Rechnungen über den eigenen E-Mail-Server (SMTP)."""

import smtplib
import ssl
from email.utils import formataddr
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend as SmtpVersand
from django.utils import timezone

from core.models import Firmendaten
from core.templatetags.kf import euro

from .beleg import briefanrede


def vorschlag(rechnung, firma):
    """Empfänger, Betreff und Text, die der Nutzer vor dem Senden noch ändern kann."""
    gruss = "\n".join(z for z in (firma.inhaber, firma.name) if z)
    return {
        "an": rechnung.kontakt.email if rechnung.kontakt else "",
        "betreff": f"Rechnung {rechnung.nummer}",
        "text": (
            f"{briefanrede(rechnung.kontakt)}\n\n"
            f"anbei erhalten Sie die Rechnung {rechnung.nummer} "
            f"vom {rechnung.datum:%d.%m.%Y} über {euro(rechnung.brutto)}.\n\n"
            f"Mit freundlichen Grüßen\n{gruss}"
        ),
        "kopie": True,
    }


def senden(rechnung, firma, an, betreff, text, kopie):
    verbindung = SmtpVersand(
        host=firma.mail_server,
        port=firma.mail_port,
        username=firma.mail_benutzer or None,
        password=firma.mail_passwort or None,
        use_tls=firma.mail_verschluesselung == Firmendaten.Verschluesselung.STARTTLS,
        use_ssl=firma.mail_verschluesselung == Firmendaten.Verschluesselung.SSL,
        timeout=30,
    )
    nachricht = EmailMessage(
        subject=betreff,
        body=text,
        from_email=formataddr((firma.name, firma.email)),
        to=[an],
        bcc=[firma.email] if kopie else [],
    )
    nachricht.attach(
        f"Rechnung-{rechnung.nummer}.pdf",
        (Path(settings.DATA_DIR) / rechnung.datei).read_bytes(),
        "application/pdf",
    )
    verbindung.send_messages([nachricht])
    rechnung.versendet_am = timezone.now()
    rechnung.versendet_an = an
    rechnung.save(update_fields=["versendet_am", "versendet_an"])


def fehlertext(fehler):
    """Verständliche Meldung zu einem Versandfehler."""
    if isinstance(fehler, smtplib.SMTPAuthenticationError):
        return (
            "Der E-Mail-Server hat die Anmeldung abgelehnt. Bitte Benutzername und "
            "Passwort in den Einstellungen prüfen (bei Gmail ein App-Passwort verwenden)."
        )
    if isinstance(fehler, smtplib.SMTPRecipientsRefused):
        return "Der E-Mail-Server hat die Empfängeradresse abgelehnt."
    if isinstance(fehler, ssl.SSLError | smtplib.SMTPServerDisconnected):
        return (
            "Die Verschlüsselung passt nicht zum Port. Üblich sind 587 mit STARTTLS "
            "oder 465 mit SSL/TLS."
        )
    if isinstance(fehler, smtplib.SMTPException):
        return f"Der E-Mail-Server hat abgelehnt: {fehler}"
    return (
        "Keine Verbindung zum E-Mail-Server. Bitte Servername und Port in den "
        "Einstellungen prüfen."
    )
