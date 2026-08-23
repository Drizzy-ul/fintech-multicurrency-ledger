import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.wallet import Wallet
from app.models.ledger import JournalEntry, LedgerPosting, EntryType, PostingDirection, AccountType
from app.services.ledger_service import (
    LedgerService,
    InsufficientFundsError,
    LedgerUnbalancedError
)


def test_deposit_double_entry_balance(db_session: Session, test_user: User):
    """
    Tests that a deposit creates strictly balanced Debits and Credits.
    """
    deposit_amount = Decimal("500.00")
    journal = LedgerService.deposit_funds(
        db=db_session,
        user_id=test_user.id,
        currency="USD",
        amount=deposit_amount,
        description="Initial USD Deposit"
    )

    assert journal.entry_type == EntryType.DEPOSIT
    assert len(journal.postings) == 2

    debit_posting = next(p for p in journal.postings if p.direction == PostingDirection.DEBIT)
    credit_posting = next(p for p in journal.postings if p.direction == PostingDirection.CREDIT)

    assert debit_posting.account_type == AccountType.USER_WALLET
    assert debit_posting.amount == deposit_amount
    assert debit_posting.currency == "USD"

    assert credit_posting.account_type == AccountType.SYSTEM_RESERVE
    assert credit_posting.amount == deposit_amount
    assert credit_posting.currency == "USD"

    # Verify wallet balance
    usd_wallet = db_session.query(Wallet).filter(Wallet.user_id == test_user.id, Wallet.currency == "USD").first()
    assert usd_wallet.balance == deposit_amount


@pytest.mark.asyncio
async def test_currency_conversion_zero_sum_balance(db_session: Session, test_user: User):
    """
    Tests currency conversion from USD to GHS:
    - Verifies mathematical balance across both currency legs.
    - Verifies user USD wallet is credited, and GHS wallet is debited.
    - Verifies system audit passes with zero errors.
    """
    # 1. Deposit 1,000 USD
    LedgerService.deposit_funds(
        db=db_session,
        user_id=test_user.id,
        currency="USD",
        amount=Decimal("1000.00"),
        description="Deposit for FX Conversion"
    )

    # 2. Convert 200 USD to GHS
    conv_amount = Decimal("200.00")
    journal = await LedgerService.convert_currency(
        db=db_session,
        user_id=test_user.id,
        source_currency="USD",
        target_currency="GHS",
        source_amount=conv_amount
    )

    assert journal.entry_type == EntryType.FX_CONVERSION
    assert journal.source_currency == "USD"
    assert journal.target_currency == "GHS"

    # Check USD leg balance
    usd_debits = sum(p.amount for p in journal.postings if p.currency == "USD" and p.direction == PostingDirection.DEBIT)
    usd_credits = sum(p.amount for p in journal.postings if p.currency == "USD" and p.direction == PostingDirection.CREDIT)
    assert usd_debits == usd_credits
    assert usd_credits == conv_amount

    # Check GHS leg balance
    ghs_debits = sum(p.amount for p in journal.postings if p.currency == "GHS" and p.direction == PostingDirection.DEBIT)
    ghs_credits = sum(p.amount for p in journal.postings if p.currency == "GHS" and p.direction == PostingDirection.CREDIT)
    assert ghs_debits == ghs_credits
    assert ghs_debits > Decimal("0.00")

    # Check resulting wallet balances
    usd_wallet = db_session.query(Wallet).filter(Wallet.user_id == test_user.id, Wallet.currency == "USD").first()
    ghs_wallet = db_session.query(Wallet).filter(Wallet.user_id == test_user.id, Wallet.currency == "GHS").first()

    assert usd_wallet.balance == Decimal("800.00")
    assert ghs_wallet.balance == ghs_debits

    # 3. System-wide ledger audit verification
    audit = LedgerService.audit_ledger_integrity(db_session)
    assert audit["is_balanced"] is True
    assert audit["unbalanced_entries_count"] == 0


@pytest.mark.asyncio
async def test_insufficient_funds_protection(db_session: Session, test_user: User):
    """
    Ensures conversions and transfers fail cleanly if balance is inadequate,
    with zero partial state written to the ledger.
    """
    with pytest.raises(InsufficientFundsError):
        await LedgerService.convert_currency(
            db=db_session,
            user_id=test_user.id,
            source_currency="GBP",
            target_currency="USD",
            source_amount=Decimal("5000.00")
        )

    # Balance remains intact at 0
    gbp_wallet = db_session.query(Wallet).filter(Wallet.user_id == test_user.id, Wallet.currency == "GBP").first()
    assert gbp_wallet.balance == Decimal("0.0000")


def test_custom_imbalance_prevention():
    """
    Tests that the safety validator raises LedgerUnbalancedError if postings do not balance.
    """
    imbalanced_postings = [
        LedgerPosting(
            currency="USD",
            direction=PostingDirection.DEBIT,
            amount=Decimal("100.00")
        ),
        LedgerPosting(
            currency="USD",
            direction=PostingDirection.CREDIT,
            amount=Decimal("99.90")  # Imbalance of $0.10!
        )
    ]
    with pytest.raises(LedgerUnbalancedError):
        LedgerService._verify_journal_balance(imbalanced_postings)
