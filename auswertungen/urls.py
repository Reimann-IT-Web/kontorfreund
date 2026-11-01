from django.urls import path

from . import views

app_name = "auswertungen"

urlpatterns = [
    path("", views.rechnungsausgangsbuch, name="rechnungsausgangsbuch"),
]
