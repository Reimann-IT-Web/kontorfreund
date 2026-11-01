from . import pruefung


def taegliche_pruefung(get_response):
    """Stößt nach einer Anfrage die tägliche Prüfung der Ablage an, wenn sie fällig ist."""

    def middleware(request):
        response = get_response(request)
        # Erst nach der Anmeldung: Der Selbsttest ruft nur die Anmeldeseite auf und
        # soll in der Datenbank nichts hinterlassen.
        if request.user.is_authenticated:
            pruefung.bei_bedarf()
        return response

    return middleware
