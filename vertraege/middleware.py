from . import abrechnen as vertraege


def abrechnen(get_response):
    """Legt vor einer angemeldeten Anfrage fällige Entwürfe aus Verträgen an (B-10).

    Vorher, nicht danach: So stehen sie schon auf der Seite, die gerade geöffnet wird.
    """

    def middleware(request):
        if request.user.is_authenticated:
            vertraege.bei_bedarf()
        return get_response(request)

    return middleware
