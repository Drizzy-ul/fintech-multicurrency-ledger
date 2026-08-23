import pytest
from decimal import Decimal
from app.services.fx_service import fx_service


@pytest.mark.asyncio
async def test_get_live_exchange_rate_same_currency():
    rate, is_cached = await fx_service.get_live_exchange_rate("USD", "USD")
    assert rate == Decimal("1.00000000")
    assert is_cached is True


@pytest.mark.asyncio
async def test_get_live_exchange_rate_usd_ghs():
    rate, _ = await fx_service.get_live_exchange_rate("USD", "GHS")
    assert rate > Decimal("0.0")
    # Rate should be positive and reasonable (typically around 10-25 GHS per USD)
    assert rate >= Decimal("5.0")


@pytest.mark.asyncio
async def test_quote_creation_and_expiration():
    source_amount = Decimal("100.00")
    quote = await fx_service.create_quote("USD", "GHS", source_amount)
    
    assert quote["source_currency"] == "USD"
    assert quote["target_currency"] == "GHS"
    assert quote["source_amount"] == source_amount
    assert quote["fee_amount"] == Decimal("0.50") # 0.5% fee of $100
    assert quote["target_amount"] > Decimal("0.00")
    
    # Retrieve valid quote
    retrieved = fx_service.get_valid_quote(quote["quote_id"])
    assert retrieved is not None
    assert retrieved["quote_id"] == quote["quote_id"]
    assert retrieved["exchange_rate"] == quote["exchange_rate"]

    # Non-existent quote
    assert fx_service.get_valid_quote("quote_invalid123") is None
