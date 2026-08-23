from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    currency: str
    balance: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class DepositRequest(BaseModel):
    currency: str = Field(..., description="Currency code (GHS, USD, GBP)")
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Deposit amount (must be positive)")
    description: str = Field(default="External Wallet Deposit", description="Description of the deposit")
    reference_id: Optional[str] = Field(default=None, description="Optional custom idempotency reference")


class UserWalletsOverview(BaseModel):
    user_id: int
    wallets: List[WalletResponse]
    total_in_usd_estimate: Optional[Decimal] = None
