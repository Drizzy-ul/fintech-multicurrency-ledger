import pytest
from decimal import Decimal
from fastapi.testclient import TestClient


def test_deposit_and_view_wallets(client: TestClient, auth_headers: dict):
    # Deposit 250 USD
    dep_res = client.post("/api/v1/wallets/deposit", json={
        "currency": "USD",
        "amount": "250.00",
        "description": "API Test Deposit"
    }, headers=auth_headers)
    assert dep_res.status_code == 201

    # Check wallets overview
    overview_res = client.get("/api/v1/wallets", headers=auth_headers)
    assert overview_res.status_code == 200
    wallets = overview_res.json()["wallets"]
    usd_w = next(w for w in wallets if w["currency"] == "USD")
    assert Decimal(str(usd_w["balance"])) == Decimal("250.00")


def test_currency_conversion_flow(client: TestClient, auth_headers: dict):
    # 1. Deposit $500
    client.post("/api/v1/wallets/deposit", json={
        "currency": "USD",
        "amount": "500.00"
    }, headers=auth_headers)

    # 2. Get Quote
    quote_res = client.post("/api/v1/transfers/quote", json={
        "source_currency": "USD",
        "target_currency": "GHS",
        "amount": "100.00"
    }, headers=auth_headers)
    assert quote_res.status_code == 200
    quote = quote_res.json()
    assert Decimal(str(quote["source_amount"])) == Decimal("100.00")
    quote_id = quote["quote_id"]

    # 3. Convert with quote
    conv_res = client.post("/api/v1/transfers/convert", json={
        "source_currency": "USD",
        "target_currency": "GHS",
        "amount": "100.00",
        "quote_id": quote_id
    }, headers=auth_headers)
    assert conv_res.status_code == 200
    conv_data = conv_res.json()
    assert conv_data["source_currency"] == "USD"
    assert conv_data["target_currency"] == "GHS"
    assert conv_data["status"] == "POSTED"

    # 4. Check GHS wallet balance is now positive
    ghs_res = client.get("/api/v1/wallets/GHS", headers=auth_headers)
    assert ghs_res.status_code == 200
    assert Decimal(str(ghs_res.json()["balance"])) > Decimal("0.00")


def test_p2p_cross_currency_transfer(
    client: TestClient,
    auth_headers: dict,
    test_user2
):
    # 1. Deposit 300 GBP for sender
    client.post("/api/v1/wallets/deposit", json={
        "currency": "GBP",
        "amount": "300.00"
    }, headers=auth_headers)

    # 2. P2P Transfer from Sender (GBP) to Recipient (GHS)
    p2p_res = client.post("/api/v1/transfers/p2p", json={
        "recipient_email": test_user2.email,
        "source_currency": "GBP",
        "target_currency": "GHS",
        "amount": "50.00",
        "description": "Ghana remittance gift"
    }, headers=auth_headers)
    assert p2p_res.status_code == 200
    p2p_data = p2p_res.json()
    assert p2p_data["status"] == "POSTED"
    assert p2p_data["source_currency"] == "GBP"
    assert p2p_data["target_currency"] == "GHS"


def test_system_audit_endpoint(client: TestClient, auth_headers: dict):
    audit_res = client.get("/api/v1/ledger/audit", headers=auth_headers)
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["is_balanced"] is True
    assert audit_data["unbalanced_entries_count"] == 0
