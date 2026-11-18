from django.urls import path

from . import views

app_name = "serien"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("hochladen/", views.hochladen, name="hochladen"),
    path("liste/<int:pk>/", views.vorschau, name="vorschau"),
    path("liste/<int:pk>/verwerfen/", views.verwerfen, name="verwerfen"),
    path("vorlage/", views.vorlage, name="vorlage"),
    path("vorlage/beilage/", views.beilage, name="beilage"),
    path("<int:pk>/", views.serie, name="serie"),
    path("<int:pk>/festschreiben/", views.festschreiben, name="festschreiben"),
    path("<int:pk>/senden/", views.senden, name="senden"),
    path("<int:pk>/drucken/", views.drucken, name="drucken"),
    path("<int:pk>/eingezogen/", views.eingezogen, name="eingezogen"),
]
