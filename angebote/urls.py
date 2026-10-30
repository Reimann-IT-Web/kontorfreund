from django.urls import path

from . import views

app_name = "angebote"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.neu, name="neu"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("<int:pk>/kopieren/", views.kopieren, name="kopieren"),
    path("<int:pk>/antwort/", views.antwort, name="antwort"),
    path("<int:pk>/rechnung/", views.rechnung_erstellen, name="rechnung_erstellen"),
]
