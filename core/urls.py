from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.start, name="start"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("firmen/", views.firmen_liste, name="firmen"),
    path("firmen/oeffnen/", views.firma_oeffnen, name="firma_oeffnen"),
    path("firmen/neu/", views.firma_anlegen, name="firma_anlegen"),
    path("firmen/entfernen/", views.firma_entfernen, name="firma_entfernen"),
    path("firmen/offen/", views.firma_offen, name="firma_offen"),
    path("<slug:slug>/", views.platzhalter, name="platzhalter"),
]
