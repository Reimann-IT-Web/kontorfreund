from django.urls import path

from . import views

app_name = "invoicing"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.neu, name="neu"),
    path("<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
]
