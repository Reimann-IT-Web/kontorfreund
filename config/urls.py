from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

# Fehlende Rechte: verständliche Seite und Eintrag im Protokoll.
handler403 = "core.sicherheit.kein_zugriff"

urlpatterns = [
    # Browser fragen /favicon.ico direkt ab, auch wenn die Seite ein anderes Symbol nennt.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("img/favicon.svg"), permanent=True),
    ),
    # Verlauf je Adresse unter /adressen/<nr>/verlauf/, sonst die Adressen selbst.
    path("adressen/", include("historie.urls")),
    path("adressen/", include("contacts.urls")),
    path("wiedervorlagen/", include("wiedervorlagen.urls")),
    path("rechnungen/", include("invoicing.urls")),
    path("angebote/", include("angebote.urls")),
    path("vertraege/", include("vertraege.urls")),
    path("auftragsbestaetigungen/", include("auftraege.urls")),
    path("offene-posten/", include("zahlungen.urls")),
    path("artikel/", include("artikel.urls")),
    path("ablage/", include("archive.urls")),
    path("eingangsrechnungen/", include("eingang.urls")),
    path("auswertungen/", include("auswertungen.urls")),
    path("benachrichtigungen/", include("benachrichtigungen.urls")),
    path("datensicherung/", include("backups.urls")),
    path("konto/", include("konten.urls")),
    path("protokoll/", include("protokoll.urls")),
    path("dokumentation/", include("dokumentation.urls")),
    path("datenzugriff/", include("datenzugriff.urls")),
    path("import/", include("importe.urls")),
    path("", include("core.urls")),
]
