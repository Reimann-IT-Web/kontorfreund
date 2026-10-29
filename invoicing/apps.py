from django.apps import AppConfig


class InvoicingConfig(AppConfig):
    """Angebote und Rechnungen. Bis Phase 2 nur der Editor, ohne Speichern."""

    name = "invoicing"
    verbose_name = "Angebote & Rechnungen"
