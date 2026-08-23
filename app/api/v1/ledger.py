from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.wallet import Wallet
from app.models.ledger import JournalEntry, LedgerPosting
from app.schemas.ledger import JournalEntryResponse, LedgerPostingResponse, AuditIntegrityCheck
from app.services.ledger_service import LedgerService
from app.api.deps import get_current_user

router = APIRouter(prefix="/ledger", tags=["Double-Entry Ledger"])


@router.get("/audit", response_model=AuditIntegrityCheck)
def run_ledger_audit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Executes a system-wide mathematical integrity audit across all journal entries and postings.
    Guarantees zero-sum balance and verifies Debits == Credits across every currency.
    """
    audit_report = LedgerService.audit_ledger_integrity(db)
    return audit_report


@router.get("/history", response_model=List[LedgerPostingResponse])
def get_user_ledger_postings(
    currency: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns itemized double-entry postings for the authenticated user's wallets.
    """
    query = db.query(LedgerPosting).join(Wallet, LedgerPosting.wallet_id == Wallet.id).filter(
        Wallet.user_id == current_user.id
    )

    if currency:
        query = query.filter(LedgerPosting.currency == currency.upper())

    postings = query.order_by(LedgerPosting.created_at.desc()).limit(limit).all()
    return postings


@router.get("/journal/{reference_id}", response_model=JournalEntryResponse)
def get_journal_entry_by_reference(
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetches the atomic journal entry along with all corresponding debit and credit legs.
    """
    entry = db.query(JournalEntry).filter(JournalEntry.reference_id == reference_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Journal entry with reference '{reference_id}' not found."
        )
    return entry
