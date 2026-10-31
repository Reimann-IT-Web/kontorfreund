from django.core.paginator import Paginator
from django.shortcuts import render

from konten.rechte import nur_inhaber

from .models import Eintrag


@nur_inhaber
def liste(request):
    seite = Paginator(Eintrag.objects.all(), 100).get_page(request.GET.get("seite"))
    return render(
        request,
        "protokoll/liste.html",
        {"bereich": "protokoll", "seite": seite},
    )
