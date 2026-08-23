import os
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.user import User
from app.models.wallet import Wallet
from app.services.ledger_service import LedgerService
from app.services.pdf_service import PDFStatementService


def test_pdf_statement_generation_file_output(db_session: Session, test_user: User, tmp_path):
    # 1. Setup transactions
    usd_wallet = db_session.query(Wallet).filter(
        Wallet.user_id == test_user.id,
        Wallet.currency == "USD"
    ).first()

    LedgerService.deposit_funds(
        db=db_session,
        user_id=test_user.id,
        currency="USD",
        amount=Decimal("1250.00"),
        description="Salary Deposit"
    )

    start_date = date.today() - timedelta(days=30)
    end_date = date.today()

    filepath, filename, file_size = PDFStatementService.generate_statement_pdf(
        db=db_session,
        wallet_id=usd_wallet.id,
        start_date=start_date,
        end_date=end_date,
        output_dir=str(tmp_path)
    )

    assert os.path.exists(filepath)
    assert filename.endswith(".pdf")
    assert file_size > 1000  # PDF should be generated and non-trivial in size

    # Verify PDF magic header bytes (%PDF)
    with open(filepath, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_statement_api_endpoint(client: TestClient, auth_headers: dict, test_user: User, db_session: Session):
    usd_wallet = db_session.query(Wallet).filter(
        Wallet.user_id == test_user.id,
        Wallet.currency == "USD"
    ).first()

    # Commit wallet so background task's separate SessionLocal can see it in SQLite
    db_session.commit()

    start_date = (date.today() - timedelta(days=15)).isoformat()
    end_date = date.today().isoformat()

    # Trigger generation
    gen_res = client.post("/api/v1/statements/generate", json={
        "wallet_id": usd_wallet.id,
        "start_date": start_date,
        "end_date": end_date
    }, headers=auth_headers)
    assert gen_res.status_code == 200
    task_data = gen_res.json()
    task_id = task_data["task_id"]

    # Check status
    status_res = client.get(f"/api/v1/statements/{task_id}/status", headers=auth_headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] in ["QUEUED", "PROCESSING", "SUCCESS"]
