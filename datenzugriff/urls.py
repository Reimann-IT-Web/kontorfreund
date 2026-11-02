from django.urls import path

from . import views

app_name = "datenzugriff"

urlpatterns = [
    path("", views.start, name="start"),
    path("beleg/", views.beleg, name="beleg"),
    path(
        "verfahrensdokumentation/<int:pk>/", views.dokumentation, name="dokumentation"
    ),
    path("<slug:name>/", views.tabelle, name="tabelle"),
]
