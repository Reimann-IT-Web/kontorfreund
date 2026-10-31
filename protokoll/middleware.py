from .erfassen import ANFRAGE


def anfrage_merken(get_response):
    """Merkt sich die Anfrage, damit das Protokoll weiß, wer etwas geändert hat."""

    def middleware(request):
        token = ANFRAGE.set(request)
        try:
            return get_response(request)
        finally:
            ANFRAGE.reset(token)

    return middleware
