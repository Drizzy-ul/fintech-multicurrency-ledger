import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
from sqlalchemy.orm import relationship
from app.database import Base


class EntryType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    FX_CONVERSION = "FX_CONVERSION"
    P2P_TRANSFER = "P2P_TRANSFER"
    FEE_CHARGE = "FEE_CHARGE"
    ADJUSTMENT = "ADJUSTMENT"


class PostingDirection(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class AccountType(str, enum.Enum):
    USER_WALLET = "USER_WALLET"
    FX_CLEARING = "FX_CLEARING"
    SYSTEM_RESERVE = "SYSTEM_RESERVE"
    FEE_REVENUE = "FEE_REVENUE"


class EntryStatus(str, enum.Enum):
    POSTED = "POSTED"
    PENDING = "PENDING"
    REVERSED = "REVERSED"
    FAILED = "FAILED"


class JournalEntry(Base):
    """
    Represents an atomic financial transaction event.
    Must contain balanced LedgerPostings.
    """
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    reference_id = Column(String(64), unique=True, index=True, nullable=False)
    entry_type = Column(SQLEnum(EntryType), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    status = Column(SQLEnum(EntryStatus), default=EntryStatus.POSTED, nullable=False)
    
    # FX & Fee metadata if applicable
    source_currency = Column(String(3), nullable=True)
    target_currency = Column(String(3), nullable=True)
    exchange_rate = Column(Numeric(18, 8), nullable=True)
    fee_amount = Column(Numeric(18, 4), default=Decimal("0.0000"), nullable=True)
    fee_currency = Column(String(3), nullable=True)
    
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    postings = relationship("LedgerPosting", back_populates="journal_entry", cascade="all, delete-orphan")


class LedgerPosting(Base):
    """
    Individual debit or credit posting in the double-entry ledger.
    """
    __tablename__ = "ledger_postings"

    id = Column(Integer, primary_key=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True, index=True)
    
    account_type = Column(SQLEnum(AccountType), default=AccountType.USER_WALLET, nullable=False)
    currency = Column(String(3), nullable=False, index=True)
    direction = Column(SQLEnum(PostingDirection), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    
    # Running balance snapshot for quick statement rendering and audit verification
    balance_after = Column(Numeric(18, 4), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="postings")
    wallet = relationship("Wallet", back_populates="postings")

    __table_args__ = (
        Index("ix_postings_wallet_created", "wallet_id", "created_at"),
    )
