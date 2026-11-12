from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.start, name="start"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("einstellungen/updates/", views.updates_seite, name="updates"),
    path("einstellungen/briefkopf/", views.briefkopf, name="briefkopf"),
    path("firmen/", views.firmen_liste, name="firmen"),
    path("firmen/oeffnen/", views.firma_oeffnen, name="firma_oeffnen"),
    path("firmen/neu/", views.firma_anlegen, name="firma_anlegen"),
    path("firmen/entfernen/", views.firma_entfernen, name="firma_entfernen"),
    path("firmen/offen/", views.firma_offen, name="firma_offen"),
    path("hilfe/", views.hilfe, name="hilfe"),
    path("hilfe/<slug:thema>/", views.hilfe, name="hilfe_thema"),
]
