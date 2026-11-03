from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("orte/", views.orte, name="orte"),
    path("kategorien/", views.kategorien, name="kategorien"),
    path("kategorien/<int:pk>/", views.kategorien, name="kategorie"),
    path(
        "kategorien/<int:pk>/loeschen/",
        views.kategorie_loeschen,
        name="kategorie_loeschen",
    ),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/archivieren/", views.archivieren, name="archivieren"),
    path("<int:pk>/datenschutz/", views.datenschutz, name="datenschutz"),
    path("<int:pk>/auskunft/", views.auskunft, name="auskunft"),
    path("<int:pk>/sperren/", views.sperren, name="sperren"),
    path("<int:pk>/entsperren/", views.entsperren, name="entsperren"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
