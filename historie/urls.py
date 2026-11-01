from django.urls import path

from . import views

app_name = "historie"

urlpatterns = [
    path("<int:pk>/verlauf/", views.verlauf, name="verlauf"),
    path("eintrag/<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("eintrag/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
