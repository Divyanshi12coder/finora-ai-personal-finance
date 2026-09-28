"""Pytest fixtures.

Each test gets an isolated, file-backed SQLite database so tests never touch a
developer's real data and never share state. The ``app.database`` engine is
rebound before the application is imported, which is why the environment is set
up at module import time rather than inside a fixture.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

# --- Environment must be configured before app modules are imported ---------
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
for path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

_TMP_DIR = tempfile.mkdtemp(prefix="finora-tests-")
os.environ["DATABASE_URL"] = ""  # force the SQLite fallback
os.environ["JWT_SECRET"] = "test-secret-not-used-in-production"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["UPLOAD_DIR"] = str(Path(_TMP_DIR) / "uploads")
os.environ["AI_API_KEY"] = ""  # exercise the deterministic fallback path

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.database as database_module  # noqa: E402


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def engine(db_path: Path):
    """A fresh SQLite engine with foreign keys enforced."""
    test_engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(test_engine, "connect")
    def _fk_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Rebind the module-level engine/session factory so application code (which
    # imports these by name) uses the test database.
    original_engine = database_module.engine
    original_factory = database_module.SessionLocal

    database_module.engine = test_engine
    database_module.SessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, future=True
    )

    from app import models  # noqa: F401  ensures all tables are registered

    database_module.Base.metadata.create_all(bind=test_engine)

    yield test_engine

    database_module.Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    database_module.engine = original_engine
    database_module.SessionLocal = original_factory


@pytest.fixture
def session(engine):
    """A database session for service-level tests."""
    factory = database_module.SessionLocal
    db = factory()
    try:
        from app.services import category_service

        category_service.ensure_system_categories(db)
        db.commit()
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def client(engine):
    """A TestClient wired to the test database."""
    from app.main import app

    # Override the request-scoped session dependency to use the test engine.
    def override_get_db():
        db = database_module.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database_module.get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def register_user(
    client: TestClient,
    email: str = "user@finora.app",
    password: str = "TestPass123",
    full_name: str = "Test User",
) -> dict:
    """Register a user and return ``{token, user, headers}``."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "currency": "INR",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {
        "token": payload["access_token"],
        "user": payload["user"],
        "headers": {"Authorization": f"Bearer {payload['access_token']}"},
    }


@pytest.fixture
def user_a(client: TestClient) -> dict:
    return register_user(client, email="alice@finora.app", full_name="Alice")


@pytest.fixture
def user_b(client: TestClient) -> dict:
    return register_user(client, email="bob@finora.app", full_name="Bob")


@pytest.fixture
def categories(client: TestClient, user_a: dict) -> dict[str, str]:
    """Map of category name -> id."""
    response = client.get("/api/categories", headers=user_a["headers"])
    assert response.status_code == 200
    return {c["name"]: c["id"] for c in response.json()}


def make_transaction(
    client: TestClient,
    headers: dict,
    amount: str = "500.00",
    tx_type: str = "expense",
    occurred_on: date | None = None,
    merchant: str = "Test Merchant",
    description: str = "Test transaction",
    category_id: str | None = None,
    auto_categorize: bool = False,
    payment_method: str = "UPI",
) -> dict:
    body = {
        "amount": amount,
        "type": tx_type,
        "occurred_on": (occurred_on or date.today()).isoformat(),
        "merchant": merchant,
        "description": description,
        "payment_method": payment_method,
        "auto_categorize": auto_categorize,
    }
    if category_id:
        body["category_id"] = category_id

    response = client.post("/api/transactions", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def seed_history(
    client: TestClient,
    headers: dict,
    category_id: str,
    months: int = 6,
    monthly_amount: Decimal = Decimal("5000"),
    per_month: int = 4,
    today: date | None = None,
) -> None:
    """Create a spread of expenses across several months."""
    from app.utils.dates import add_months, month_start

    today = today or date.today()
    per_transaction = monthly_amount / per_month

    for offset in range(months):
        month = month_start(add_months(today, -offset))
        for index in range(per_month):
            day = min(2 + index * 5, 27)
            occurred = month.replace(day=day)
            if occurred > today:
                continue
            make_transaction(
                client,
                headers,
                amount=f"{per_transaction:.2f}",
                occurred_on=occurred,
                merchant=f"Merchant {index}",
                category_id=category_id,
            )


def add_income(
    client: TestClient,
    headers: dict,
    category_id: str,
    months: int = 6,
    amount: str = "100000.00",
    today: date | None = None,
) -> None:
    from app.utils.dates import add_months, month_start

    today = today or date.today()
    for offset in range(months):
        month = month_start(add_months(today, -offset))
        make_transaction(
            client,
            headers,
            amount=amount,
            tx_type="income",
            occurred_on=month,
            merchant="Employer",
            category_id=category_id,
            payment_method="Bank Transfer",
        )
