from django.urls import path

from . import views

app_name = "konten"

urlpatterns = [
    path("", views.konto, name="konto"),
    path("anmelden/", views.anmelden, name="anmelden"),
    path("anmelden/code/", views.code, name="code"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("einrichten/", views.einrichten, name="einrichten"),
    path("zwei-faktor/", views.zwei_faktor, name="zwei_faktor"),
    path("zwei-faktor/aus/", views.zwei_faktor_aus, name="zwei_faktor_aus"),
    path("benutzer/", views.benutzer, name="benutzer"),
    path("benutzer/<int:pk>/", views.benutzer_bearbeiten, name="benutzer_bearbeiten"),
]
