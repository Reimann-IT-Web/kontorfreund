from django.urls import path

from . import views

app_name = "auswertungen"

urlpatterns = [
    path("", views.rechnungsausgangsbuch, name="rechnungsausgangsbuch"),
    path("datev/", views.datev_export, name="datev"),
    path("datev/einstellungen/", views.datev_einstellungen, name="datev_einstellungen"),
    path("betriebspruefung/", views.betriebspruefung, name="betriebspruefung"),
]
