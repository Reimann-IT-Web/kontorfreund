from django.urls import path

from . import views

app_name = "dokumentation"

urlpatterns = [
    path("", views.seite, name="seite"),
    path("<str:art>/herunterladen/", views.herunterladen, name="herunterladen"),
    path("fassung/<int:pk>/", views.fassung, name="fassung"),
]
