from django.urls import path

from . import views

app_name = "historie"

urlpatterns = [
    path("<int:pk>/verlauf/", views.verlauf, name="verlauf"),
    path("<int:pk>/dateien/", views.hochladen, name="hochladen"),
    path("eintrag/<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("eintrag/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("datei/<int:pk>/", views.datei, name="datei"),
    path("datei/<int:pk>/loeschen/", views.datei_loeschen, name="datei_loeschen"),
    path(
        "datei/<int:pk>/zurueckholen/",
        views.datei_zurueckholen,
        name="datei_zurueckholen",
    ),
]
