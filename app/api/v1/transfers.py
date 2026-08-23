from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.transfer import (
    FXQuoteRequest,
    FXQuoteResponse,
    CurrencyConvertRequest,
    P2PTransferRequest,
    TransferResponse
)
from app.services.fx_service import fx_service
from app.services.ledger_service import (
    LedgerService,
    InsufficientFundsError,
    WalletNotFoundError,
    LedgerUnbalancedError
)
from app.api.deps import get_current_user
from app.config import settings

router = APIRouter(prefix="/transfers", tags=["Transfers & Currency Exchange"])


@router.post("/quote", response_model=FXQuoteResponse)
async def get_exchange_rate_quote(
    payload: FXQuoteRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Fetches real-time live exchange rates from the external API (cached via Redis)
    and returns a guaranteed rate quote valid for 60 seconds.
    """
    src = payload.source_currency.upper()
    tgt = payload.target_currency.upper()

    if src not in settings.SUPPORTED_CURRENCIES or tgt not in settings.SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Currencies must be one of {settings.SUPPORTED_CURRENCIES}"
        )

    quote = await fx_service.create_quote(src, tgt, payload.amount)
    return quote


@router.post("/convert", response_model=TransferResponse)
async def convert_currency(
    payload: CurrencyConvertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Converts funds between the user's own wallets (e.g. USD to GHS or GBP)
    using guaranteed double-entry balanced ledger postings.
    """
    src = payload.source_currency.upper()
    tgt = payload.target_currency.upper()

    if src not in settings.SUPPORTED_CURRENCIES or tgt not in settings.SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Currencies must be one of {settings.SUPPORTED_CURRENCIES}"
        )

    try:
        journal = await LedgerService.convert_currency(
            db=db,
            user_id=current_user.id,
            source_currency=src,
            target_currency=tgt,
            source_amount=payload.amount,
            quote_id=payload.quote_id,
            reference_id=payload.reference_id
        )

        # Retrieve target posting amount
        target_amount = Decimal("0.00")
        for p in journal.postings:
            if p.wallet_id is not None and p.currency == tgt and p.direction.value == "DEBIT":
                target_amount = p.amount

        return {
            "reference_id": journal.reference_id,
            "status": journal.status.value,
            "entry_type": journal.entry_type.value,
            "source_currency": journal.source_currency,
            "target_currency": journal.target_currency,
            "source_amount": payload.amount,
            "target_amount": target_amount,
            "exchange_rate": journal.exchange_rate,
            "fee_amount": journal.fee_amount or Decimal("0.00"),
            "fee_currency": journal.fee_currency or src,
            "timestamp": journal.created_at,
            "message": f"Successfully converted {payload.amount} {src} to {target_amount} {tgt}"
        }

    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (WalletNotFoundError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LedgerUnbalancedError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ledger safety violation: {e}")


@router.post("/p2p", response_model=TransferResponse)
async def p2p_transfer(
    payload: P2PTransferRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Sends money from authenticated user to another user by email.
    Supports same-currency and cross-currency multi-wallet transfers.
    """
    src = payload.source_currency.upper()
    tgt = payload.target_currency.upper()

    if src not in settings.SUPPORTED_CURRENCIES or tgt not in settings.SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Currencies must be one of {settings.SUPPORTED_CURRENCIES}"
        )

    try:
        journal = await LedgerService.p2p_transfer(
            db=db,
            sender_user=current_user,
            recipient_email=payload.recipient_email,
            source_currency=src,
            target_currency=tgt,
            amount=payload.amount,
            description=payload.description or "P2P Transfer",
            reference_id=payload.reference_id
        )

        target_amount = payload.amount
        for p in journal.postings:
            if p.wallet_id is not None and p.currency == tgt and p.direction.value == "DEBIT":
                target_amount = p.amount

        return {
            "reference_id": journal.reference_id,
            "status": journal.status.value,
            "entry_type": journal.entry_type.value,
            "source_currency": journal.source_currency,
            "target_currency": journal.target_currency,
            "source_amount": payload.amount,
            "target_amount": target_amount,
            "exchange_rate": journal.exchange_rate,
            "fee_amount": journal.fee_amount or Decimal("0.00"),
            "fee_currency": journal.fee_currency or src,
            "timestamp": journal.created_at,
            "message": f"Successfully transferred {payload.amount} {src} to {payload.recipient_email}"
        }
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (WalletNotFoundError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LedgerUnbalancedError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ledger safety violation: {e}")
