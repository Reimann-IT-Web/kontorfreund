from django.urls import path

from . import views

app_name = "benachrichtigungen"

urlpatterns = [
    path("", views.einstellungen, name="einstellungen"),
    path("verbinden/", views.verbinden, name="verbinden"),
    path("testen/", views.testen, name="testen"),
    path("trennen/", views.trennen, name="trennen"),
    path("autostart/", views.autostart_setzen, name="autostart"),
]
