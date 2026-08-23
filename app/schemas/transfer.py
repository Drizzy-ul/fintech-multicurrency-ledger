from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class FXQuoteRequest(BaseModel):
    source_currency: str = Field(..., description="Source currency (e.g. USD, GHS, GBP)")
    target_currency: str = Field(..., description="Target currency (e.g. USD, GHS, GBP)")
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Source amount to convert")


class FXQuoteResponse(BaseModel):
    quote_id: str
    source_currency: str
    target_currency: str
    source_amount: Decimal
    target_amount: Decimal
    exchange_rate: Decimal
    fee_amount: Decimal
    fee_currency: str
    expires_at: datetime
    is_cached: bool


class CurrencyConvertRequest(BaseModel):
    source_currency: str = Field(..., description="Currency to convert from")
    target_currency: str = Field(..., description="Currency to convert to")
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Amount in source currency")
    quote_id: Optional[str] = Field(default=None, description="Optional locked FX quote ID")
    reference_id: Optional[str] = Field(default=None, description="Optional idempotency reference")


class P2PTransferRequest(BaseModel):
    recipient_email: EmailStr = Field(..., description="Recipient user's registered email")
    source_currency: str = Field(..., description="Source currency to send (e.g. USD)")
    target_currency: str = Field(..., description="Target currency for recipient (e.g. GHS, GBP, USD)")
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Amount to send in source currency")
    description: Optional[str] = Field(default="P2P Transfer", description="Transfer memo/description")
    reference_id: Optional[str] = Field(default=None, description="Optional idempotency reference")


class TransferResponse(BaseModel):
    reference_id: str
    status: str
    entry_type: str
    source_currency: str
    target_currency: str
    source_amount: Decimal
    target_amount: Decimal
    exchange_rate: Decimal
    fee_amount: Decimal
    fee_currency: str
    timestamp: datetime
    message: str
