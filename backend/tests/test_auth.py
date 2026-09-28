"""Authentication, authorisation and per-user data isolation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import make_transaction, register_user


class TestRegistration:
    def test_register_returns_token_and_profile(self, client: TestClient):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "new@finora.app",
                "password": "StrongPass123",
                "full_name": "New User",
                "currency": "INR",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == "new@finora.app"
        assert body["user"]["onboarding_completed"] is False

    def test_password_never_returned(self, client: TestClient):
        response = client.post(
            "/api/auth/register",
            json={
                "email": "secret@finora.app",
                "password": "StrongPass123",
                "full_name": "Secret",
            },
        )
        assert "StrongPass123" not in response.text
        assert "hashed_password" not in response.text

    def test_password_is_hashed_in_database(self, client: TestClient, session):
        register_user(client, email="hashme@finora.app", password="StrongPass123")

        from app.services import auth_service
        from app.utils.security import verify_password

        user = auth_service.get_by_email(session, "hashme@finora.app")
        assert user is not None
        assert user.hashed_password != "StrongPass123"
        assert user.hashed_password.startswith("$2")  # bcrypt
        assert verify_password("StrongPass123", user.hashed_password)

    @pytest.mark.parametrize(
        "password",
        ["short1", "nodigitshere", "12345678", "Ab1"],
    )
    def test_weak_passwords_rejected(self, client: TestClient, password: str):
        response = client.post(
            "/api/auth/register",
            json={
                "email": f"weak{len(password)}@finora.app",
                "password": password,
                "full_name": "Weak",
            },
        )
        assert response.status_code == 422

    def test_invalid_email_rejected(self, client: TestClient):
        response = client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "StrongPass123", "full_name": "X"},
        )
        assert response.status_code == 422

    def test_duplicate_email_rejected(self, client: TestClient):
        register_user(client, email="dup@finora.app")
        response = client.post(
            "/api/auth/register",
            json={"email": "dup@finora.app", "password": "StrongPass123", "full_name": "Dup"},
        )
        assert response.status_code == 409

    def test_email_is_case_insensitive(self, client: TestClient):
        register_user(client, email="case@finora.app")
        response = client.post(
            "/api/auth/register",
            json={"email": "CASE@finora.app", "password": "StrongPass123", "full_name": "X"},
        )
        assert response.status_code == 409


class TestLogin:
    def test_login_succeeds(self, client: TestClient):
        register_user(client, email="login@finora.app", password="StrongPass123")
        response = client.post(
            "/api/auth/login",
            json={"email": "login@finora.app", "password": "StrongPass123"},
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_wrong_password_rejected(self, client: TestClient):
        register_user(client, email="wrong@finora.app", password="StrongPass123")
        response = client.post(
            "/api/auth/login",
            json={"email": "wrong@finora.app", "password": "WrongPass123"},
        )
        assert response.status_code == 401

    def test_unknown_email_rejected_with_same_message(self, client: TestClient):
        """The error must not reveal whether the account exists."""
        register_user(client, email="known@finora.app", password="StrongPass123")

        unknown = client.post(
            "/api/auth/login",
            json={"email": "nobody@finora.app", "password": "StrongPass123"},
        )
        wrong = client.post(
            "/api/auth/login",
            json={"email": "known@finora.app", "password": "WrongPass123"},
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_login_case_insensitive(self, client: TestClient):
        register_user(client, email="mixed@finora.app", password="StrongPass123")
        response = client.post(
            "/api/auth/login",
            json={"email": "MiXeD@FINORA.app", "password": "StrongPass123"},
        )
        assert response.status_code == 200


class TestProtectedRoutes:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/dashboard"),
            ("get", "/api/transactions"),
            ("get", "/api/budgets"),
            ("get", "/api/goals"),
            ("get", "/api/insights"),
            ("get", "/api/analytics/spending"),
            ("get", "/api/forecast"),
            ("get", "/api/health-score"),
            ("get", "/api/anomalies"),
            ("get", "/api/receipts"),
            ("get", "/api/auth/me"),
        ],
    )
    def test_requires_authentication(self, client: TestClient, method: str, path: str):
        response = getattr(client, method)(path)
        assert response.status_code == 401

    def test_malformed_token_rejected(self, client: TestClient):
        response = client.get(
            "/api/dashboard", headers={"Authorization": "Bearer not.a.real.token"}
        )
        assert response.status_code == 401

    def test_token_for_deleted_user_rejected(self, client: TestClient, session):
        auth = register_user(client, email="ghost@finora.app")

        from app.services import auth_service

        user = auth_service.get_by_email(session, "ghost@finora.app")
        session.delete(user)
        session.commit()

        response = client.get("/api/auth/me", headers=auth["headers"])
        assert response.status_code == 401

    def test_expired_token_rejected(self, client: TestClient):
        from app.utils.security import create_access_token

        expired = create_access_token(subject="whoever", expires_minutes=-10)
        response = client.get("/api/dashboard", headers={"Authorization": f"Bearer {expired}"})
        assert response.status_code == 401

    def test_token_signed_with_other_secret_rejected(self, client: TestClient, user_a: dict):
        import jwt

        forged = jwt.encode(
            {"sub": user_a["user"]["id"], "type": "access", "exp": 9999999999},
            "a-completely-different-secret",
            algorithm="HS256",
        )
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert response.status_code == 401


class TestDataIsolation:
    """The most important security property: users cannot see each other's data."""

    def test_list_endpoints_are_scoped(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        make_transaction(
            client, user_a["headers"], amount="1000.00", category_id=categories["Food"]
        )

        a_list = client.get("/api/transactions", headers=user_a["headers"]).json()
        b_list = client.get("/api/transactions", headers=user_b["headers"]).json()
        assert a_list["total"] == 1
        assert b_list["total"] == 0

    def test_cannot_read_another_users_transaction(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        response = client.get(f"/api/transactions/{tx['id']}", headers=user_b["headers"])
        assert response.status_code == 404

    def test_cannot_update_another_users_transaction(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        response = client.put(
            f"/api/transactions/{tx['id']}",
            json={"amount": "1.00"},
            headers=user_b["headers"],
        )
        assert response.status_code == 404

        # And the original is untouched.
        original = client.get(f"/api/transactions/{tx['id']}", headers=user_a["headers"]).json()
        assert float(original["amount"]) == 500.0

    def test_cannot_delete_another_users_transaction(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        response = client.delete(f"/api/transactions/{tx['id']}", headers=user_b["headers"])
        assert response.status_code == 404
        assert (
            client.get(f"/api/transactions/{tx['id']}", headers=user_a["headers"]).status_code
            == 200
        )

    def test_bulk_delete_cannot_reach_other_users_rows(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        response = client.post(
            "/api/transactions/bulk-delete",
            json={"ids": [tx["id"]]},
            headers=user_b["headers"],
        )
        assert response.status_code == 200
        assert "0 transaction" in response.json()["detail"]
        assert (
            client.get(f"/api/transactions/{tx['id']}", headers=user_a["headers"]).status_code
            == 200
        )

    def test_cannot_read_another_users_budget(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        budget = client.post(
            "/api/budgets",
            json={
                "name": "Alice budget",
                "period_month": "2026-09",
                "items": [{"category_id": categories["Food"], "limit_amount": "5000"}],
            },
            headers=user_a["headers"],
        ).json()

        assert (
            client.get(f"/api/budgets/{budget['id']}", headers=user_b["headers"]).status_code == 404
        )
        assert (
            client.delete(f"/api/budgets/{budget['id']}", headers=user_b["headers"]).status_code
            == 404
        )

    def test_cannot_read_another_users_goal(self, client: TestClient, user_a: dict, user_b: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Alice goal", "target_amount": "10000"},
            headers=user_a["headers"],
        ).json()

        assert client.get(f"/api/goals/{goal['id']}", headers=user_b["headers"]).status_code == 404
        assert (
            client.post(
                f"/api/goals/{goal['id']}/contributions",
                json={"amount": "100"},
                headers=user_b["headers"],
            ).status_code
            == 404
        )

    def test_cannot_use_another_users_custom_category(
        self, client: TestClient, user_a: dict, user_b: dict
    ):
        custom = client.post(
            "/api/categories",
            json={"name": "Alice Only", "kind": "expense"},
            headers=user_a["headers"],
        ).json()

        response = client.post(
            "/api/transactions",
            json={
                "amount": "100.00",
                "type": "expense",
                "occurred_on": "2026-09-01",
                "category_id": custom["id"],
                "auto_categorize": False,
            },
            headers=user_b["headers"],
        )
        assert response.status_code == 400

    def test_dashboards_are_independent(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        make_transaction(
            client, user_a["headers"], amount="7777.00", category_id=categories["Food"]
        )

        b_dash = client.get("/api/dashboard", headers=user_b["headers"]).json()
        expenses = next(m for m in b_dash["metrics"] if m["key"] == "monthly_expenses")
        assert float(expenses["value"]) == 0.0
        assert "7777" not in client.get("/api/dashboard", headers=user_b["headers"]).text


class TestPasswordManagement:
    def test_change_password(self, client: TestClient):
        auth = register_user(client, email="change@finora.app", password="OldPass123")

        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "OldPass123", "new_password": "NewPass456"},
            headers=auth["headers"],
        )
        assert response.status_code == 200

        assert (
            client.post(
                "/api/auth/login",
                json={"email": "change@finora.app", "password": "OldPass123"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "change@finora.app", "password": "NewPass456"},
            ).status_code
            == 200
        )

    def test_change_password_requires_current(self, client: TestClient):
        auth = register_user(client, email="guard@finora.app", password="OldPass123")
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "WrongOld123", "new_password": "NewPass456"},
            headers=auth["headers"],
        )
        assert response.status_code == 400

    def test_forgot_password_does_not_reveal_accounts(self, client: TestClient):
        register_user(client, email="exists@finora.app")

        known = client.post("/api/auth/forgot-password", json={"email": "exists@finora.app"})
        unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@finora.app"})

        assert known.status_code == unknown.status_code == 200
        assert known.json()["detail"] == unknown.json()["detail"]

    def test_reset_password_flow(self, client: TestClient):
        register_user(client, email="reset@finora.app", password="OldPass123")

        forgot = client.post("/api/auth/forgot-password", json={"email": "reset@finora.app"})
        token = forgot.json()["reset_token"]
        assert token

        response = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "BrandNew123"},
        )
        assert response.status_code == 200
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "reset@finora.app", "password": "BrandNew123"},
            ).status_code
            == 200
        )

    def test_reset_token_is_single_use(self, client: TestClient):
        register_user(client, email="once@finora.app", password="OldPass123")
        token = client.post("/api/auth/forgot-password", json={"email": "once@finora.app"}).json()[
            "reset_token"
        ]

        assert (
            client.post(
                "/api/auth/reset-password",
                json={"token": token, "new_password": "FirstNew123"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/reset-password",
                json={"token": token, "new_password": "SecondNew123"},
            ).status_code
            == 400
        )

    def test_invalid_reset_token_rejected(self, client: TestClient):
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "x" * 40, "new_password": "Whatever123"},
        )
        assert response.status_code == 400

    def test_reset_token_stored_only_as_hash(self, client: TestClient, session):
        register_user(client, email="hashed@finora.app")
        token = client.post(
            "/api/auth/forgot-password", json={"email": "hashed@finora.app"}
        ).json()["reset_token"]

        from app.services import auth_service

        user = auth_service.get_by_email(session, "hashed@finora.app")
        session.refresh(user)
        assert user.reset_token_hash is not None
        assert user.reset_token_hash != token


class TestOnboarding:
    def test_onboarding_saves_profile_and_creates_goals(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/auth/onboarding",
            json={
                "monthly_income": "120000",
                "income_source": "Salaried employment",
                "typical_monthly_expenses": "70000",
                "savings_goal_amount": "300000",
                "currency": "INR",
                "budgeting_preference": "balanced",
                "goals": [
                    {
                        "name": "Emergency Fund",
                        "target_amount": "400000",
                        "goal_type": "emergency_fund",
                    },
                    {"name": "Bali Trip", "target_amount": "150000", "goal_type": "vacation"},
                ],
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 200
        body = response.json()
        assert body["onboarding_completed"] is True
        assert float(body["monthly_income"]) == 120000.0
        # Emergency fund target defaults to 6x monthly expenses.
        assert float(body["emergency_fund_target"]) == 420000.0

        goals = client.get("/api/goals", headers=user_a["headers"]).json()
        assert {g["name"] for g in goals} == {"Emergency Fund", "Bali Trip"}

    def test_profile_update(self, client: TestClient, user_a: dict):
        response = client.patch(
            "/api/auth/me",
            json={"full_name": "Alice Updated", "monthly_income": "99000"},
            headers=user_a["headers"],
        )
        assert response.status_code == 200
        assert response.json()["full_name"] == "Alice Updated"
        assert float(response.json()["monthly_income"]) == 99000.0
