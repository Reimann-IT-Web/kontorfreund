from django.urls import path

from . import views

app_name = "zahlungen"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("kunde/<int:pk>/", views.kontoauszug, name="kontoauszug"),
    path("rechnung/<int:pk>/zahlung/", views.buchen, name="buchen"),
    path("rechnung/<int:pk>/ausbuchen/", views.ausbuchen, name="ausbuchen"),
    path("rechnung/<int:pk>/mahnen/", views.mahnung_neu, name="mahnen"),
    path("zahlung/<int:pk>/loeschen/", views.zahlung_loeschen, name="zahlung_loeschen"),
    path("mahnung/<int:pk>/", views.mahnung, name="mahnung"),
    path("mahnung/<int:pk>/pdf/", views.mahnung_pdf, name="mahnung_pdf"),
    path("mahnung/<int:pk>/loeschen/", views.mahnung_loeschen, name="mahnung_loeschen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path(
        "basiszins/<int:pk>/loeschen/",
        views.basiszins_loeschen,
        name="basiszins_loeschen",
    ),
]
