from django.urls import path

from . import views

app_name = "benachrichtigungen"

urlpatterns = [
    path("", views.einstellungen, name="einstellungen"),
    path("autostart/", views.autostart_setzen, name="autostart"),
]
