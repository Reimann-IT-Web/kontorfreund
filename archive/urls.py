from django.urls import path

from . import views

app_name = "archive"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("pruefen/", views.pruefen, name="pruefen"),
    path("zurueckholen/", views.zurueckholen, name="zurueckholen"),
    path("fristen/", views.aufbewahrung, name="fristen"),
    path("<int:pk>/datei/", views.datei, name="datei"),
]
