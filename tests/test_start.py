from django.conf import settings


def test_startseite(client):
    response = client.get("/")

    assert response.status_code == 200
    assert settings.PRODUCT_NAME in response.text
