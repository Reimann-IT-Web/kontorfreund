from django.shortcuts import render


def start(request):
    return render(request, "core/start.html")
