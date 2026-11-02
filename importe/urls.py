from django.urls import path

from . import views

app_name = "importe"

urlpatterns = [
    path("adressen/", views.hochladen, {"ziel": "kontakte"}, name="adressen"),
    path("artikel/", views.hochladen, {"ziel": "artikel"}, name="artikel"),
    path("<int:pk>/", views.zuordnen, name="zuordnen"),
    path("<int:pk>/bericht/", views.bericht, name="bericht"),
    path("<int:pk>/uebernehmen/", views.uebernehmen, name="uebernehmen"),
    path("<int:pk>/abbrechen/", views.verwerfen, name="verwerfen"),
    path(
        "zuordnungen/<int:pk>/loeschen/",
        views.zuordnung_loeschen,
        name="zuordnung_loeschen",
    ),
]
