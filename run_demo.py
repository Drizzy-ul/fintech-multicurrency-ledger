"""
Antigravity FinTech - Multi-Currency Ledger & Live FX Demonstration
"""
import sys
import os
import asyncio
from datetime import date, timedelta
from decimal import Decimal

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy.orm import Session

from app.database import SessionLocal, Base, engine
from app.models.user import User
from app.models.wallet import Wallet
from app.services.auth_service import AuthService
from app.services.fx_service import fx_service
from app.services.ledger_service import LedgerService
from app.services.pdf_service import PDFStatementService


async def main():
    print("=" * 75)
    print(" [>] ANTIGRAVITY FINTECH MULTI-CURRENCY DOUBLE-ENTRY LEDGER SYSTEM")
    print("=" * 75)

    # 1. Initialize Database Schema
    print("\n[1] Initializing SQLite / PostgreSQL Database Schema...")
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    # 2. Setup User & Multi-Currency Wallets
    print("\n[2] Provisioning User & Wallets (USD, GHS, GBP)...")
    email = "demo.developer@antigravity.io"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            full_name="Kofi Mensah (FinTech Dev)",
            hashed_password=AuthService.get_password_hash("FintechDev2026!"),
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    wallets = LedgerService.initialize_user_wallets(db, user, ["USD", "GHS", "GBP"])
    print(f"    User Created: {user.full_name} <{user.email}>")
    for w in wallets:
        print(f"    - Wallet #{w.id}: {w.currency} Balance = {w.balance}")

    # 3. External Wallet Deposit (Double-Entry: Debit User Wallet, Credit System Reserve)
    print("\n[3] Depositing $1,000.00 USD into Wallet...")
    deposit_entry = LedgerService.deposit_funds(
        db=db,
        user_id=user.id,
        currency="USD",
        amount=Decimal("1000.00"),
        description="International Wire Transfer Inflow"
    )
    print(f"    [+] Deposit Posted! Journal Ref: {deposit_entry.reference_id}")
    for p in deposit_entry.postings:
        print(f"        * {p.direction.value:<6} {p.account_type.value:<15} {p.amount} {p.currency} (Wallet: #{p.wallet_id})")

    # 4. Live FX Rate Lookup & Quoting
    print("\n[4] Querying Live Real-Time Exchange Rates...")
    usd_to_ghs_rate, cached = await fx_service.get_live_exchange_rate("USD", "GHS")
    print(f"    Live FX Rate USD -> GHS: 1 USD = {usd_to_ghs_rate} GHS (Cached: {cached})")
    
    usd_to_gbp_rate, _ = await fx_service.get_live_exchange_rate("USD", "GBP")
    print(f"    Live FX Rate USD -> GBP: 1 USD = {usd_to_gbp_rate} GBP")

    # 5. Guaranteed Rate Conversion
    print("\n[5] Converting $300.00 USD to Ghanaian Cedis (GHS)...")
    quote = await fx_service.create_quote("USD", "GHS", Decimal("300.00"))
    print(f"    Quote Locked: {quote['quote_id']} | Rate: {quote['exchange_rate']} | Fee: {quote['fee_amount']} USD")
    print(f"    Target Payout: {quote['target_amount']} GHS")

    conv_entry = await LedgerService.convert_currency(
        db=db,
        user_id=user.id,
        source_currency="USD",
        target_currency="GHS",
        source_amount=Decimal("300.00"),
        quote_id=quote["quote_id"]
    )
    print(f"    [+] FX Conversion Posted! Journal Ref: {conv_entry.reference_id}")
    for p in conv_entry.postings:
        print(f"        * {p.direction.value:<6} {p.account_type.value:<15} {p.amount} {p.currency} (Wallet: #{p.wallet_id})")

    # 6. Second Conversion: Convert $200.00 USD to British Pounds (GBP)
    print("\n[6] Converting $200.00 USD to British Pounds (GBP)...")
    conv_gbp_entry = await LedgerService.convert_currency(
        db=db,
        user_id=user.id,
        source_currency="USD",
        target_currency="GBP",
        source_amount=Decimal("200.00")
    )
    print(f"    [+] FX Conversion Posted! Journal Ref: {conv_gbp_entry.reference_id}")

    # 7. Print Updated Wallet Balances
    print("\n[7] Current User Multi-Currency Wallet Balances:")
    db.refresh(user)
    wallets = db.query(Wallet).filter(Wallet.user_id == user.id).all()
    for w in wallets:
        print(f"    - {w.currency} Wallet: {w.balance:,.2f} {w.currency}")

    # 8. Double-Entry Ledger System Audit
    print("\n[8] Running Double-Entry Mathematical Integrity Audit...")
    audit = LedgerService.audit_ledger_integrity(db)
    print(f"    Total Journal Entries : {audit['total_journal_entries']}")
    print(f"    Total Ledger Postings : {audit['total_postings']}")
    print(f"    Unbalanced Entries    : {audit['unbalanced_entries_count']}")
    print(f"    Audit Status          : {'[+] ALL BALANCED (Zero-Sum Invariant Satisfied)' if audit['is_balanced'] else '[-] IMBALANCE DETECTED'}")
    for curr, totals in audit['currency_balances'].items():
        print(f"      - {curr:<3}: Debits = {totals['total_debits']:>10} | Credits = {totals['total_credits']:>10} | Net Diff = {totals['net_difference']}")

    # 9. ReportLab PDF Bank Statement Generation
    print("\n[9] Generating Official PDF Account Statement using ReportLab...")
    usd_wallet = next(w for w in wallets if w.currency == "USD")
    start_date = date.today() - timedelta(days=30)
    end_date = date.today()
    filepath, filename, file_size = PDFStatementService.generate_statement_pdf(
        db=db,
        wallet_id=usd_wallet.id,
        start_date=start_date,
        end_date=end_date
    )
    print(f"    [+] Statement PDF Generated: {filename}")
    print(f"    [+] File Size: {file_size:,} bytes")
    print(f"    [+] Local Path: {filepath}")

    print("\n" + "=" * 75)
    print(" [OK] DEMONSTRATION COMPLETE: ALL SYSTEMS FULLY OPERATIONAL")
    print("=" * 75)
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
