from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.wallet import WalletResponse, DepositRequest, UserWalletsOverview
from app.schemas.ledger import JournalEntryResponse
from app.services.ledger_service import LedgerService, WalletNotFoundError
from app.services.fx_service import fx_service
from app.api.deps import get_current_user
from app.config import settings

router = APIRouter(prefix="/wallets", tags=["Wallets"])


@router.get("", response_model=UserWalletsOverview)
async def get_my_wallets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns all wallets (GHS, USD, GBP) for the authenticated user and calculates total USD equivalent.
    """
    wallets = db.query(Wallet).filter(Wallet.user_id == current_user.id).all()
    
    # If user has missing wallets, initialize them
    if len(wallets) < len(settings.SUPPORTED_CURRENCIES):
        wallets = LedgerService.initialize_user_wallets(db, current_user, settings.SUPPORTED_CURRENCIES)

    # Calculate approximate portfolio balance in USD
    total_usd = Decimal("0.00")
    for w in wallets:
        if w.currency == "USD":
            total_usd += Decimal(str(w.balance))
        else:
            rate, _ = await fx_service.get_live_exchange_rate(w.currency, "USD")
            total_usd += (Decimal(str(w.balance)) * rate)

    return {
        "user_id": current_user.id,
        "wallets": wallets,
        "total_in_usd_estimate": total_usd.quantize(Decimal("0.01"))
    }


@router.get("/{currency}", response_model=WalletResponse)
def get_wallet_by_currency(
    currency: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns specific currency wallet balance for current user.
    """
    curr = currency.upper()
    if curr not in settings.SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported currency '{currency}'. Supported: {settings.SUPPORTED_CURRENCIES}"
        )

    wallet = db.query(Wallet).filter(
        Wallet.user_id == current_user.id,
        Wallet.currency == curr
    ).first()

    if not wallet:
        wallets = LedgerService.initialize_user_wallets(db, current_user, [curr])
        wallet = wallets[0]

    return wallet


@router.post("/deposit", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
def deposit_funds(
    payload: DepositRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Simulates external funding/deposit into a user's wallet using strict double-entry ledger logic.
    """
    curr = payload.currency.upper()
    if curr not in settings.SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported currency '{payload.currency}'. Supported: {settings.SUPPORTED_CURRENCIES}"
        )

    try:
        journal_entry = LedgerService.deposit_funds(
            db=db,
            user_id=current_user.id,
            currency=curr,
            amount=payload.amount,
            description=payload.description,
            reference_id=payload.reference_id
        )
        return journal_entry
    except WalletNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
