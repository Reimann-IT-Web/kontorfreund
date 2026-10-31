from django.urls import path

from . import views

app_name = "eingang"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("hochladen/", views.hochladen, name="hochladen"),
    path("<int:pk>/", views.anzeigen, name="anzeigen"),
    path("<int:pk>/zuordnen/", views.zuordnen, name="zuordnen"),
    path("<int:pk>/datei/", views.datei, name="datei"),
    path("<int:pk>/anhang/<int:nr>/", views.anhang, name="anhang"),
]
