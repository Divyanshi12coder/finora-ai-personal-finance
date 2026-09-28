"""Budget computation, warnings and AI recommendations."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from tests.conftest import make_transaction

from app.utils.dates import add_months, month_key, month_start


class TestBudgetCrud:
    def test_create_with_category_limits(self, client: TestClient, user_a: dict, categories: dict):
        response = client.post(
            "/api/budgets",
            json={
                "name": "September",
                "period_month": month_key(date.today()),
                "total_limit": "50000",
                "items": [
                    {"category_id": categories["Food"], "limit_amount": "8000"},
                    {"category_id": categories["Transport"], "limit_amount": "4000"},
                ],
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 201
        body = response.json()
        assert len(body["items"]) == 2
        assert float(body["allocated"]) == 12000.0

    def test_one_budget_per_month(self, client: TestClient, user_a: dict, categories: dict):
        payload = {
            "name": "First",
            "period_month": month_key(date.today()),
            "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
        }
        assert (
            client.post("/api/budgets", json=payload, headers=user_a["headers"]).status_code == 201
        )
        second = client.post("/api/budgets", json=payload, headers=user_a["headers"])
        assert second.status_code == 400
        assert "already exists" in second.json()["detail"]

    def test_duplicate_category_in_one_budget_rejected(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        response = client.post(
            "/api/budgets",
            json={
                "name": "Dup",
                "period_month": month_key(date.today()),
                "items": [
                    {"category_id": categories["Food"], "limit_amount": "8000"},
                    {"category_id": categories["Food"], "limit_amount": "9000"},
                ],
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 400

    def test_update_replaces_items(self, client: TestClient, user_a: dict, categories: dict):
        budget = client.post(
            "/api/budgets",
            json={
                "name": "Original",
                "period_month": month_key(date.today()),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()

        updated = client.put(
            f"/api/budgets/{budget['id']}",
            json={
                "name": "Revised",
                "items": [
                    {"category_id": categories["Transport"], "limit_amount": "5000"},
                ],
            },
            headers=user_a["headers"],
        ).json()

        assert updated["name"] == "Revised"
        assert len(updated["items"]) == 1
        assert updated["items"][0]["category"]["name"] == "Transport"

    def test_delete(self, client: TestClient, user_a: dict, categories: dict):
        budget = client.post(
            "/api/budgets",
            json={
                "name": "Temp",
                "period_month": month_key(date.today()),
                "items": [{"category_id": categories["Food"], "limit_amount": "1000"}],
            },
            headers=user_a["headers"],
        ).json()
        assert (
            client.delete(f"/api/budgets/{budget['id']}", headers=user_a["headers"]).status_code
            == 200
        )
        assert (
            client.get(f"/api/budgets/{budget['id']}", headers=user_a["headers"]).status_code == 404
        )

    def test_invalid_period_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/budgets",
            json={"name": "Bad", "period_month": "not-a-month", "items": []},
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_zero_limit_rejected(self, client: TestClient, user_a: dict, categories: dict):
        response = client.post(
            "/api/budgets",
            json={
                "name": "Zero",
                "period_month": month_key(date.today()),
                "items": [{"category_id": categories["Food"], "limit_amount": "0"}],
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 422


class TestBudgetCalculations:
    """Spend must always be derived from transactions, never stored."""

    def test_spend_is_derived_from_transactions(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        this_month = month_start(today)

        for amount in ["2000.00", "1500.00", "2200.00", "1000.00"]:
            make_transaction(
                client,
                user_a["headers"],
                amount=amount,
                occurred_on=this_month,
                category_id=categories["Food"],
            )

        budget = client.post(
            "/api/budgets",
            json={
                "name": "Derived",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "10000"}],
            },
            headers=user_a["headers"],
        ).json()

        item = budget["items"][0]
        assert float(item["spent"]) == 6700.0
        assert float(item["remaining"]) == 3300.0
        assert item["utilization"] == 67.0

    def test_adding_a_transaction_moves_utilisation(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        budget = client.post(
            "/api/budgets",
            json={
                "name": "Live",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()
        assert float(budget["items"][0]["spent"]) == 0.0

        make_transaction(
            client,
            user_a["headers"],
            amount="6250.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        refetched = client.get(f"/api/budgets/{budget['id']}", headers=user_a["headers"]).json()
        item = refetched["items"][0]
        assert float(item["spent"]) == 6250.0
        assert item["utilization"] == 78.12

    def test_other_categories_do_not_count(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="5000.00",
            occurred_on=month_start(today),
            category_id=categories["Shopping"],
        )

        budget = client.post(
            "/api/budgets",
            json={
                "name": "Scoped",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()
        assert float(budget["items"][0]["spent"]) == 0.0

    def test_transactions_outside_the_month_do_not_count(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        last_month = month_start(add_months(today, -1))
        make_transaction(
            client,
            user_a["headers"],
            amount="4000.00",
            occurred_on=last_month,
            category_id=categories["Food"],
        )

        budget = client.post(
            "/api/budgets",
            json={
                "name": "Current",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()
        assert float(budget["items"][0]["spent"]) == 0.0

    def test_exceeded_status_and_negative_remaining(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        budget = client.post(
            "/api/budgets",
            json={
                "name": "Over",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()

        item = budget["items"][0]
        assert item["status"] == "exceeded"
        assert float(item["remaining"]) == -1000.0
        assert item["utilization"] == 112.5
        assert "exceeded" in item["warning"].lower()

    def test_warning_mentions_days_remaining(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="7500.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        budget = client.post(
            "/api/budgets",
            json={
                "name": "Risk",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()

        item = budget["items"][0]
        assert item["status"] in {"at_risk", "watch", "exceeded"}
        assert item["warning"]
        assert budget["days_remaining"] >= 0
        assert 0 <= budget["expected_utilization"] <= 100

    def test_projection_is_pace_based(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="3000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        budget = client.post(
            "/api/budgets",
            json={
                "name": "Pace",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        ).json()

        item = budget["items"][0]
        # Projection scales the daily average across the whole month, so it can
        # never be below what has already been spent.
        assert float(item["projected_spend"]) >= float(item["spent"])
        assert float(item["daily_average"]) > 0

    def test_current_endpoint(self, client: TestClient, user_a: dict, categories: dict):
        assert client.get("/api/budgets/current", headers=user_a["headers"]).json() is None

        client.post(
            "/api/budgets",
            json={
                "name": "Now",
                "period_month": month_key(date.today()),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        )
        current = client.get("/api/budgets/current", headers=user_a["headers"]).json()
        assert current is not None
        assert current["name"] == "Now"


class TestBudgetRecommendations:
    def test_declines_without_enough_history(self, client: TestClient, user_a: dict):
        response = client.get("/api/budgets/recommendations", headers=user_a["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["sufficient_data"] is False
        assert body["items"] == []
        assert "history" in body["message"].lower()

    def test_recommends_from_actual_history(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """The worked example from the spec: 8000 -> 9200 -> 10100 -> 9800."""
        today = date.today()
        monthly = {1: "8000.00", 2: "9200.00", 3: "10100.00", 4: "9800.00"}
        for offset, amount in monthly.items():
            month = month_start(add_months(today, -offset))
            make_transaction(
                client,
                user_a["headers"],
                amount=amount,
                occurred_on=month.replace(day=10),
                category_id=categories["Food"],
            )

        body = client.get("/api/budgets/recommendations", headers=user_a["headers"]).json()
        assert body["sufficient_data"] is True

        food = next(i for i in body["items"] if i["category_name"] == "Food")
        # Trimmed mean drops the 10100 -> mean(8000, 9200, 9800) = 9000,
        # then a balanced 8% buffer -> 9720, rounded up to the nearest 50.
        assert float(food["recommended_amount"]) == 9750.0
        assert food["months_analyzed"] == 4
        assert len(food["monthly_history"]) == 4
        assert float(food["mean"]) == 9275.0
        assert food["method"] == "trimmed_mean_plus_style_buffer"

    def test_rationale_explains_the_number(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        for offset, amount in {1: "8000.00", 2: "9200.00", 3: "10100.00"}.items():
            month = month_start(add_months(today, -offset))
            make_transaction(
                client,
                user_a["headers"],
                amount=amount,
                occurred_on=month.replace(day=10),
                category_id=categories["Food"],
            )

        body = client.get("/api/budgets/recommendations", headers=user_a["headers"]).json()
        food = next(i for i in body["items"] if i["category_name"] == "Food")

        rationale = food["rationale"]
        assert "Food" in rationale
        assert "8,000" in rationale  # the actual history is quoted back
        assert "buffer" in rationale.lower()
        assert body["methodology"]
        assert food["confidence"] in {"low", "medium", "high"}

    def test_upward_trend_shifts_the_recommendation(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """A category rising steeply should not be budgeted at its stale average."""
        today = date.today()
        for offset, amount in {1: "20000.00", 2: "10000.00", 3: "10000.00"}.items():
            month = month_start(add_months(today, -offset))
            make_transaction(
                client,
                user_a["headers"],
                amount=amount,
                occurred_on=month.replace(day=10),
                category_id=categories["Shopping"],
            )

        body = client.get("/api/budgets/recommendations", headers=user_a["headers"]).json()
        shopping = next(i for i in body["items"] if i["category_name"] == "Shopping")

        assert shopping["trend_pct"] is not None and shopping["trend_pct"] > 15
        # Weighted toward the latest month, so above the plain mean of 13,333.
        assert float(shopping["recommended_amount"]) > 13333
        assert "recent month" in shopping["rationale"]

    def test_budgeting_style_changes_the_buffer(
        self, client: TestClient, user_a: dict, categories: dict, session
    ):
        today = date.today()
        for offset in (1, 2, 3):
            month = month_start(add_months(today, -offset))
            make_transaction(
                client,
                user_a["headers"],
                amount="10000.00",
                occurred_on=month.replace(day=10),
                category_id=categories["Food"],
            )

        balanced = client.get("/api/budgets/recommendations", headers=user_a["headers"]).json()
        balanced_amount = float(
            next(i for i in balanced["items"] if i["category_name"] == "Food")["recommended_amount"]
        )

        client.patch(
            "/api/auth/me",
            json={"budgeting_preference": "strict"},
            headers=user_a["headers"],
        )
        strict = client.get("/api/budgets/recommendations", headers=user_a["headers"]).json()
        strict_amount = float(
            next(i for i in strict["items"] if i["category_name"] == "Food")["recommended_amount"]
        )

        assert strict_amount < balanced_amount

    def test_apply_recommendations_creates_a_budget(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        for offset in (1, 2, 3):
            month = month_start(add_months(today, -offset))
            make_transaction(
                client,
                user_a["headers"],
                amount="9000.00",
                occurred_on=month.replace(day=10),
                category_id=categories["Food"],
            )

        response = client.post(
            "/api/budgets/recommendations/apply",
            json={"period_month": month_key(today)},
            headers=user_a["headers"],
        )
        assert response.status_code == 200
        body = response.json()

        food = next(i for i in body["items"] if i["category"]["name"] == "Food")
        assert float(food["limit_amount"]) > 0
        # The rationale is stored with the limit so the suggestion is auditable.
        assert food["recommended_amount"] is not None
        assert food["recommendation_basis"]

    def test_apply_without_history_is_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/budgets/recommendations/apply",
            json={"period_month": month_key(date.today())},
            headers=user_a["headers"],
        )
        assert response.status_code == 400
