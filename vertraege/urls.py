from django.urls import path

from . import views

app_name = "vertraege"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.neu, name="neu"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
