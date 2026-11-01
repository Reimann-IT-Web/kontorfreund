from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("orte/", views.orte, name="orte"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/archivieren/", views.archivieren, name="archivieren"),
]
