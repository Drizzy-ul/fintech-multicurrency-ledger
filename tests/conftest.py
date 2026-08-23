import os
import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.database as app_db
import app.tasks.celery_app as app_celery
from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.models.wallet import Wallet
from app.services.auth_service import AuthService
from app.services.ledger_service import LedgerService

# SQLite database for testing
TEST_DATABASE_URL = "sqlite:///./test_fintech.db"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch Celery and DB SessionLocal to use the test database
app_db.engine = test_engine
app_db.SessionLocal = TestingSessionLocal
app_celery.SessionLocal = TestingSessionLocal


@pytest.fixture(autouse=True)
def setup_test_db():
    """Isolates each test with a pristine schema."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session) -> User:
    user = User(
        email="kwame.mensah@example.com",
        full_name="Kwame Mensah",
        hashed_password=AuthService.get_password_hash("FintechPass123!"),
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    LedgerService.initialize_user_wallets(db_session, user)
    return user


@pytest.fixture
def test_user2(db_session) -> User:
    user = User(
        email="jane.smith@example.com",
        full_name="Jane Smith",
        hashed_password=AuthService.get_password_hash("SecurePass456!"),
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    LedgerService.initialize_user_wallets(db_session, user)
    return user


@pytest.fixture
def auth_headers(test_user) -> dict:
    token = AuthService.create_access_token(data={"sub": test_user.email, "user_id": test_user.id})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user2(test_user2) -> dict:
    token = AuthService.create_access_token(data={"sub": test_user2.email, "user_id": test_user2.id})
    return {"Authorization": f"Bearer {token}"}
