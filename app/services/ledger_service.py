import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.wallet import Wallet
from app.models.user import User
from app.models.ledger import (
    JournalEntry,
    LedgerPosting,
    EntryType,
    PostingDirection,
    AccountType,
    EntryStatus,
)
from app.services.fx_service import fx_service

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    pass


class LedgerUnbalancedError(Exception):
    pass


class WalletNotFoundError(Exception):
    pass


class LedgerService:
    @staticmethod
    def initialize_user_wallets(db: Session, user: User, currencies: List[str] = ["USD", "GHS", "GBP"]) -> List[Wallet]:
        """Creates empty wallets in all supported currencies for a newly registered user."""
        wallets = []
        for curr in currencies:
            existing = db.query(Wallet).filter(Wallet.user_id == user.id, Wallet.currency == curr).first()
            if not existing:
                wallet = Wallet(
                    user_id=user.id,
                    currency=curr.upper(),
                    balance=Decimal("0.0000"),
                    status="ACTIVE"
                )
                db.add(wallet)
                wallets.append(wallet)
            else:
                wallets.append(existing)
        db.commit()
        return wallets

    @staticmethod
    def _verify_journal_balance(postings: List[LedgerPosting]):
        """
        Double-Entry Invariant: For each currency in a journal entry,
        Total Debits must EQUAL Total Credits.
        """
        currency_balance = {}
        for p in postings:
            curr = p.currency
            if curr not in currency_balance:
                currency_balance[curr] = {"debits": Decimal("0.0000"), "credits": Decimal("0.0000")}
            
            if p.direction == PostingDirection.DEBIT:
                currency_balance[curr]["debits"] += p.amount
            elif p.direction == PostingDirection.CREDIT:
                currency_balance[curr]["credits"] += p.amount

        for curr, totals in currency_balance.items():
            if totals["debits"] != totals["credits"]:
                raise LedgerUnbalancedError(
                    f"Ledger imbalance detected for {curr}: Debits ({totals['debits']}) != Credits ({totals['credits']})"
                )

    @classmethod
    def deposit_funds(
        cls,
        db: Session,
        user_id: int,
        currency: str,
        amount: Decimal,
        description: str = "External Deposit",
        reference_id: Optional[str] = None
    ) -> JournalEntry:
        """
        Deposits external funds into a user's wallet.
        Double-Entry:
          - DEBIT  User Wallet (Asset increase)
          - CREDIT System Reserve Account (External liability/funding source)
        """
        amount = Decimal(str(amount)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if amount <= Decimal("0.0000"):
            raise ValueError("Deposit amount must be strictly positive")

        currency = currency.upper()
        ref = reference_id or f"dep_{uuid.uuid4().hex[:16]}"

        # Check idempotency
        existing_entry = db.query(JournalEntry).filter(JournalEntry.reference_id == ref).first()
        if existing_entry:
            return existing_entry

        wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id,
            Wallet.currency == currency
        ).with_for_update().first() if db.bind.dialect.name == "postgresql" else db.query(Wallet).filter(
            Wallet.user_id == user_id,
            Wallet.currency == currency
        ).first()

        if not wallet:
            raise WalletNotFoundError(f"User has no {currency} wallet")

        # Update wallet balance
        wallet.balance = (Decimal(str(wallet.balance)) + amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        journal = JournalEntry(
            reference_id=ref,
            entry_type=EntryType.DEPOSIT,
            description=description,
            status=EntryStatus.POSTED,
            source_currency=currency,
            target_currency=currency,
            exchange_rate=Decimal("1.00000000"),
            fee_amount=Decimal("0.0000"),
            fee_currency=currency
        )
        db.add(journal)
        db.flush()

        posting_debit = LedgerPosting(
            journal_entry_id=journal.id,
            wallet_id=wallet.id,
            account_type=AccountType.USER_WALLET,
            currency=currency,
            direction=PostingDirection.DEBIT,
            amount=amount,
            balance_after=wallet.balance
        )
        posting_credit = LedgerPosting(
            journal_entry_id=journal.id,
            wallet_id=None,
            account_type=AccountType.SYSTEM_RESERVE,
            currency=currency,
            direction=PostingDirection.CREDIT,
            amount=amount,
            balance_after=None
        )

        postings = [posting_debit, posting_credit]
        cls._verify_journal_balance(postings)

        db.add_all(postings)
        db.commit()
        db.refresh(journal)
        return journal

    @classmethod
    async def convert_currency(
        cls,
        db: Session,
        user_id: int,
        source_currency: str,
        target_currency: str,
        source_amount: Decimal,
        quote_id: Optional[str] = None,
        reference_id: Optional[str] = None
    ) -> JournalEntry:
        """
        Converts money from user's source wallet to target wallet.
        Double-Entry Multi-Currency Structure:
          Leg 1 (Source Currency):
            - CREDIT User Source Wallet: `source_amount`
            - DEBIT  System FX Clearing: `source_amount - fee`
            - DEBIT  System Fee Revenue: `fee_amount`
            (Total Debits == Total Credits = source_amount)
          Leg 2 (Target Currency):
            - DEBIT  User Target Wallet: `target_amount`
            - CREDIT System FX Clearing: `target_amount`
            (Total Debits == Total Credits = target_amount)
        """
        source_curr = source_currency.upper()
        target_curr = target_currency.upper()
        source_amount = Decimal(str(source_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if source_curr == target_curr:
            raise ValueError("Source and target currencies must be distinct for conversion")

        ref = reference_id or f"fx_{uuid.uuid4().hex[:16]}"
        existing = db.query(JournalEntry).filter(JournalEntry.reference_id == ref).first()
        if existing:
            return existing

        # Fetch / Validate Quote
        if quote_id:
            quote = fx_service.get_valid_quote(quote_id)
            if not quote:
                raise ValueError("Quote has expired or is invalid. Please request a fresh quote.")
            if quote["source_currency"] != source_curr or quote["target_currency"] != target_curr:
                raise ValueError("Quote currency mismatch.")
            rate = quote["exchange_rate"]
            fee_amount = quote["fee_amount"]
            target_amount = quote["target_amount"]
        else:
            quote = await fx_service.create_quote(source_curr, target_curr, source_amount)
            rate = quote["exchange_rate"]
            fee_amount = quote["fee_amount"]
            target_amount = quote["target_amount"]

        # Fetch Wallets
        src_wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id,
            Wallet.currency == source_curr
        ).first()

        tgt_wallet = db.query(Wallet).filter(
            Wallet.user_id == user_id,
            Wallet.currency == target_curr
        ).first()

        if not src_wallet or not tgt_wallet:
            raise WalletNotFoundError(f"Missing wallet for {source_curr} or {target_curr}")

        if src_wallet.balance < source_amount:
            raise InsufficientFundsError(
                f"Insufficient funds in {source_curr} wallet. Available: {src_wallet.balance}, Required: {source_amount}"
            )

        # Update Balances
        src_wallet.balance = (Decimal(str(src_wallet.balance)) - source_amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        tgt_wallet.balance = (Decimal(str(tgt_wallet.balance)) + target_amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        # Create Journal Entry
        journal = JournalEntry(
            reference_id=ref,
            entry_type=EntryType.FX_CONVERSION,
            description=f"Exchange {source_amount} {source_curr} to {target_amount} {target_curr} @ {rate}",
            status=EntryStatus.POSTED,
            source_currency=source_curr,
            target_currency=target_curr,
            exchange_rate=rate,
            fee_amount=fee_amount,
            fee_currency=source_curr,
            extra_metadata={"quote_id": quote.get("quote_id")}
        )
        db.add(journal)
        db.flush()

        # Leg 1: Source Currency Postings
        net_source_amount = source_amount - fee_amount
        postings = [
            # User Source Wallet: Decreased (Credit)
            LedgerPosting(
                journal_entry_id=journal.id,
                wallet_id=src_wallet.id,
                account_type=AccountType.USER_WALLET,
                currency=source_curr,
                direction=PostingDirection.CREDIT,
                amount=source_amount,
                balance_after=src_wallet.balance
            ),
            # System FX Clearing: Increased (Debit)
            LedgerPosting(
                journal_entry_id=journal.id,
                wallet_id=None,
                account_type=AccountType.FX_CLEARING,
                currency=source_curr,
                direction=PostingDirection.DEBIT,
                amount=net_source_amount,
                balance_after=None
            ),
        ]

        if fee_amount > Decimal("0.00"):
            # System Fee Revenue: (Debit)
            postings.append(
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=None,
                    account_type=AccountType.FEE_REVENUE,
                    currency=source_curr,
                    direction=PostingDirection.DEBIT,
                    amount=fee_amount,
                    balance_after=None
                )
            )

        # Leg 2: Target Currency Postings
        postings.extend([
            # System FX Clearing: Decreased (Credit)
            LedgerPosting(
                journal_entry_id=journal.id,
                wallet_id=None,
                account_type=AccountType.FX_CLEARING,
                currency=target_curr,
                direction=PostingDirection.CREDIT,
                amount=target_amount,
                balance_after=None
            ),
            # User Target Wallet: Increased (Debit)
            LedgerPosting(
                journal_entry_id=journal.id,
                wallet_id=tgt_wallet.id,
                account_type=AccountType.USER_WALLET,
                currency=target_curr,
                direction=PostingDirection.DEBIT,
                amount=target_amount,
                balance_after=tgt_wallet.balance
            ),
        ])

        # Verify Double-Entry Balance
        cls._verify_journal_balance(postings)

        db.add_all(postings)
        db.commit()
        db.refresh(journal)
        return journal

    @classmethod
    async def p2p_transfer(
        cls,
        db: Session,
        sender_user: User,
        recipient_email: str,
        source_currency: str,
        target_currency: str,
        amount: Decimal,
        description: str = "P2P Transfer",
        reference_id: Optional[str] = None
    ) -> JournalEntry:
        """
        Transfers funds from sender to recipient (supports cross-currency P2P).
        """
        source_curr = source_currency.upper()
        target_curr = target_currency.upper()
        amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if sender_user.email.lower() == recipient_email.lower():
            raise ValueError("Sender and recipient cannot be the same user for P2P transfer")

        recipient = db.query(User).filter(func.lower(User.email) == recipient_email.lower()).first()
        if not recipient:
            raise ValueError(f"Recipient with email {recipient_email} not found")

        ref = reference_id or f"p2p_{uuid.uuid4().hex[:16]}"
        existing = db.query(JournalEntry).filter(JournalEntry.reference_id == ref).first()
        if existing:
            return existing

        sender_wallet = db.query(Wallet).filter(
            Wallet.user_id == sender_user.id,
            Wallet.currency == source_curr
        ).first()

        recipient_wallet = db.query(Wallet).filter(
            Wallet.user_id == recipient.id,
            Wallet.currency == target_curr
        ).first()

        if not sender_wallet:
            raise WalletNotFoundError(f"Sender has no {source_curr} wallet")
        if not recipient_wallet:
            raise WalletNotFoundError(f"Recipient has no {target_curr} wallet")

        if sender_wallet.balance < amount:
            raise InsufficientFundsError(f"Insufficient funds in sender's {source_curr} wallet")

        if source_curr == target_curr:
            # Same currency transfer
            rate = Decimal("1.00000000")
            fee_amount = Decimal("0.0000")
            target_amount = amount

            sender_wallet.balance = (Decimal(str(sender_wallet.balance)) - amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            recipient_wallet.balance = (Decimal(str(recipient_wallet.balance)) + amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            journal = JournalEntry(
                reference_id=ref,
                entry_type=EntryType.P2P_TRANSFER,
                description=f"{description} (Sent to {recipient_email})",
                status=EntryStatus.POSTED,
                source_currency=source_curr,
                target_currency=target_curr,
                exchange_rate=rate,
                fee_amount=fee_amount,
                fee_currency=source_curr,
                extra_metadata={"sender_id": sender_user.id, "recipient_id": recipient.id}
            )
            db.add(journal)
            db.flush()

            postings = [
                # Sender Wallet Credit (Decreased)
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=sender_wallet.id,
                    account_type=AccountType.USER_WALLET,
                    currency=source_curr,
                    direction=PostingDirection.CREDIT,
                    amount=amount,
                    balance_after=sender_wallet.balance
                ),
                # Recipient Wallet Debit (Increased)
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=recipient_wallet.id,
                    account_type=AccountType.USER_WALLET,
                    currency=target_curr,
                    direction=PostingDirection.DEBIT,
                    amount=amount,
                    balance_after=recipient_wallet.balance
                ),
            ]
            cls._verify_journal_balance(postings)
            db.add_all(postings)
            db.commit()
            db.refresh(journal)
            return journal

        else:
            # Cross-currency P2P Transfer
            quote = await fx_service.create_quote(source_curr, target_curr, amount)
            rate = quote["exchange_rate"]
            fee_amount = quote["fee_amount"]
            target_amount = quote["target_amount"]
            net_source = amount - fee_amount

            sender_wallet.balance = (Decimal(str(sender_wallet.balance)) - amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            recipient_wallet.balance = (Decimal(str(recipient_wallet.balance)) + target_amount).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            journal = JournalEntry(
                reference_id=ref,
                entry_type=EntryType.P2P_TRANSFER,
                description=f"P2P FX: {amount} {source_curr} -> {target_amount} {target_curr} to {recipient_email}",
                status=EntryStatus.POSTED,
                source_currency=source_curr,
                target_currency=target_curr,
                exchange_rate=rate,
                fee_amount=fee_amount,
                fee_currency=source_curr,
                extra_metadata={"sender_id": sender_user.id, "recipient_id": recipient.id}
            )
            db.add(journal)
            db.flush()

            postings = [
                # Leg 1 (Source Currency)
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=sender_wallet.id,
                    account_type=AccountType.USER_WALLET,
                    currency=source_curr,
                    direction=PostingDirection.CREDIT,
                    amount=amount,
                    balance_after=sender_wallet.balance
                ),
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=None,
                    account_type=AccountType.FX_CLEARING,
                    currency=source_curr,
                    direction=PostingDirection.DEBIT,
                    amount=net_source,
                    balance_after=None
                ),
            ]
            if fee_amount > Decimal("0.00"):
                postings.append(
                    LedgerPosting(
                        journal_entry_id=journal.id,
                        wallet_id=None,
                        account_type=AccountType.FEE_REVENUE,
                        currency=source_curr,
                        direction=PostingDirection.DEBIT,
                        amount=fee_amount,
                        balance_after=None
                    )
                )

            # Leg 2 (Target Currency)
            postings.extend([
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=None,
                    account_type=AccountType.FX_CLEARING,
                    currency=target_curr,
                    direction=PostingDirection.CREDIT,
                    amount=target_amount,
                    balance_after=None
                ),
                LedgerPosting(
                    journal_entry_id=journal.id,
                    wallet_id=recipient_wallet.id,
                    account_type=AccountType.USER_WALLET,
                    currency=target_curr,
                    direction=PostingDirection.DEBIT,
                    amount=target_amount,
                    balance_after=recipient_wallet.balance
                ),
            ])

            cls._verify_journal_balance(postings)
            db.add_all(postings)
            db.commit()
            db.refresh(journal)
            return journal

    @staticmethod
    def audit_ledger_integrity(db: Session) -> dict:
        """
        Audits all journal entries across the system to verify that Debits == Credits
        for all currencies, with 0 unbalanced entries.
        """
        all_entries = db.query(JournalEntry).all()
        unbalanced_entry_ids = []
        currency_totals = {}

        total_postings = 0

        for entry in all_entries:
            curr_map = {}
            for p in entry.postings:
                total_postings += 1
                curr = p.currency
                if curr not in curr_map:
                    curr_map[curr] = {"debit": Decimal("0.0000"), "credit": Decimal("0.0000")}
                if curr not in currency_totals:
                    currency_totals[curr] = {"debit": Decimal("0.0000"), "credit": Decimal("0.0000")}

                if p.direction == PostingDirection.DEBIT:
                    curr_map[curr]["debit"] += p.amount
                    currency_totals[curr]["debit"] += p.amount
                else:
                    curr_map[curr]["credit"] += p.amount
                    currency_totals[curr]["credit"] += p.amount

            is_entry_balanced = True
            for curr, val in curr_map.items():
                if val["debit"] != val["credit"]:
                    is_entry_balanced = False
                    break
            if not is_entry_balanced:
                unbalanced_entry_ids.append(entry.id)

        is_balanced = len(unbalanced_entry_ids) == 0

        return {
            "is_balanced": is_balanced,
            "total_journal_entries": len(all_entries),
            "total_postings": total_postings,
            "currency_balances": {
                c: {
                    "total_debits": str(v["debit"]),
                    "total_credits": str(v["credit"]),
                    "net_difference": str(v["debit"] - v["credit"])
                }
                for c, v in currency_totals.items()
            },
            "unbalanced_entries_count": len(unbalanced_entry_ids),
            "unbalanced_entry_ids": unbalanced_entry_ids,
            "message": "All double-entry ledger journals are in mathematical balance." if is_balanced else "WARNING: Ledger imbalance detected!"
        }
