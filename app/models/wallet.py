from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    currency = Column(String(3), nullable=False)  # USD, GHS, GBP
    # Using Numeric(18, 4) with Decimal precision for exact currency storage
    balance = Column(Numeric(18, 4), default=Decimal("0.0000"), nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False)  # ACTIVE, FROZEN, CLOSED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = relationship("User", back_populates="wallets")
    postings = relationship("LedgerPosting", back_populates="wallet")

    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_user_currency"),
    )
