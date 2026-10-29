from . import sicherung


def datensicherung(request):
    """Stand der Sicherung für Seitenleiste und Übersicht."""
    return {"sicherung": sicherung.zustand()}
