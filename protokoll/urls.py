from django.urls import path

from . import views

app_name = "protokoll"

urlpatterns = [
    path("", views.liste, name="liste"),
]
