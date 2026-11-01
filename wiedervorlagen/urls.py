from django.urls import path

from . import views

app_name = "wiedervorlagen"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/aendern/", views.aendern, name="aendern"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
