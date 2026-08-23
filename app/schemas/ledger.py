from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class LedgerPostingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wallet_id: Optional[int]
    account_type: str
    currency: str
    direction: str
    amount: Decimal
    balance_after: Optional[Decimal]
    created_at: datetime


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference_id: str
    entry_type: str
    description: str
    status: str
    source_currency: Optional[str]
    target_currency: Optional[str]
    exchange_rate: Optional[Decimal]
    fee_amount: Optional[Decimal]
    fee_currency: Optional[str]
    created_at: datetime
    postings: List[LedgerPostingResponse]


class AuditIntegrityCheck(BaseModel):
    is_balanced: bool
    total_journal_entries: int
    total_postings: int
    currency_balances: dict
    unbalanced_entries_count: int
    unbalanced_entry_ids: List[int]
    message: str
