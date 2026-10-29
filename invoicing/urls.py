from django.urls import path

from . import views

app_name = "invoicing"

urlpatterns = [
    path("neu/", views.neu, name="neu"),
]
