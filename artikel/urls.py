from django.urls import path

from . import views

app_name = "artikel"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/aktiv/", views.aktiv, name="aktiv"),
]
