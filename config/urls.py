from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # Browser fragen /favicon.ico direkt ab, auch wenn die Seite ein anderes Symbol nennt.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("img/favicon.svg"), permanent=True),
    ),
    path("adressen/", include("contacts.urls")),
    path("rechnungen/", include("invoicing.urls")),
    path("angebote/", include("angebote.urls")),
    path("offene-posten/", include("zahlungen.urls")),
    path("artikel/", include("artikel.urls")),
    path("ablage/", include("archive.urls")),
    path("eingangsrechnungen/", include("eingang.urls")),
    path("datensicherung/", include("backups.urls")),
    path("konto/", include("konten.urls")),
    path("protokoll/", include("protokoll.urls")),
    # Zuletzt: core enthält die Platzhalter-Bereiche unter /<bereich>/.
    path("", include("core.urls")),
]
