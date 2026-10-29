from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.start, name="start"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("<slug:slug>/", views.platzhalter, name="platzhalter"),
]
