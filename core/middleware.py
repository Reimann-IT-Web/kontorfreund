from . import updates


def update_suche(get_response):
    """Stößt nach einer Anfrage die tägliche Suche nach neuen Versionen an (D-7)."""

    def middleware(request):
        response = get_response(request)
        # Erst nach der Anmeldung: Der Selbsttest ruft nur die Anmeldeseite auf.
        if request.user.is_authenticated:
            updates.bei_bedarf()
        return response

    return middleware
