from . import sicherung


def taegliche_sicherung(get_response):
    """Stößt nach einer Anfrage die tägliche Sicherung an, wenn sie fällig ist."""

    def middleware(request):
        response = get_response(request)
        sicherung.bei_bedarf()
        return response

    return middleware
