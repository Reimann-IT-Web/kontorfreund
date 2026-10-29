from django.urls import path

from . import views

app_name = "backups"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("einlesen/", views.einlesen, name="einlesen"),
    path("<str:ort>/<str:name>/", views.wiederherstellen, name="wiederherstellen"),
]
