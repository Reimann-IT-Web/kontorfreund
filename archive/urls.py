from django.urls import path

from . import views

app_name = "archive"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("<int:pk>/datei/", views.datei, name="datei"),
]
