import pytest
from fastapi.testclient import TestClient


def test_user_registration_auto_provisions_wallets(client: TestClient):
    payload = {
        "email": "kofi.addo@example.com",
        "password": "Password123!",
        "full_name": "Kofi Addo"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "kofi.addo@example.com"
    assert data["full_name"] == "Kofi Addo"

    # Login
    login_res = client.post("/api/v1/auth/login", json={
        "email": "kofi.addo@example.com",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify all 3 wallets (USD, GHS, GBP) were automatically provisioned
    wallets_res = client.get("/api/v1/wallets", headers=headers)
    assert wallets_res.status_code == 200
    wallets_data = wallets_res.json()
    currencies = {w["currency"] for w in wallets_data["wallets"]}
    assert "USD" in currencies
    assert "GHS" in currencies
    assert "GBP" in currencies


def test_duplicate_registration_rejected(client: TestClient):
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
        "full_name": "Duplicate User"
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


def test_invalid_login(client: TestClient):
    res = client.post("/api/v1/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "WrongPassword!"
    })
    assert res.status_code == 401
