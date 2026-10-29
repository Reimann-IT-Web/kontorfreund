import pytest


@pytest.fixture(autouse=True)
def datenordner(tmp_path, settings):
    """Kein Test schreibt in den echten Datenordner, auch keine Sicherung."""
    settings.DATA_DIR = tmp_path
