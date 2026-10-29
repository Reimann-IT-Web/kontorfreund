def test_startseite(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Kontorfreund (Kleinunternehmen)" in response.text
