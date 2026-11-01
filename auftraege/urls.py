from django.urls import path

from . import views

app_name = "auftraege"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.neu, name="neu"),
    path("aus-angebot/<int:pk>/", views.aus_angebot, name="aus_angebot"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("<int:pk>/kopieren/", views.kopieren, name="kopieren"),
    path("<int:pk>/rechnung/", views.rechnung_erstellen, name="rechnung_erstellen"),
]
