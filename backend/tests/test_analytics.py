"""Dashboard, analytics, forecasting, anomaly detection and the health score."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from tests.conftest import add_income, make_transaction, seed_history

from app.utils.dates import add_months, month_start


class TestDashboard:
    def test_empty_dashboard_is_honest(self, client: TestClient, user_a: dict):
        response = client.get("/api/dashboard", headers=user_a["headers"])
        assert response.status_code == 200
        body = response.json()
        assert body["has_data"] is False
        assert all(float(m["value"]) == 0.0 for m in body["metrics"])
        assert body["recent_transactions"] == []

    def test_metrics_reflect_transactions(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        this_month = month_start(today)
        make_transaction(
            client,
            user_a["headers"],
            amount="50000.00",
            tx_type="income",
            occurred_on=this_month,
            category_id=categories["Salary"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="12000.00",
            occurred_on=this_month,
            category_id=categories["Food"],
        )

        body = client.get("/api/dashboard", headers=user_a["headers"]).json()
        metrics = {m["key"]: m for m in body["metrics"]}

        assert float(metrics["monthly_income"]["value"]) == 50000.0
        assert float(metrics["monthly_expenses"]["value"]) == 12000.0
        assert float(metrics["savings"]["value"]) == 38000.0
        assert float(metrics["savings_rate"]["value"]) == 76.0
        assert body["has_data"] is True

    def test_expense_direction_is_marked_bad(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """The UI needs to know an expense rise is not a good thing."""
        body = client.get("/api/dashboard", headers=user_a["headers"]).json()
        metrics = {m["key"]: m for m in body["metrics"]}
        assert metrics["monthly_expenses"]["direction_is_good"] is False
        assert metrics["monthly_income"]["direction_is_good"] is True
        assert metrics["savings"]["direction_is_good"] is True

    def test_change_is_null_when_no_previous_data(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """No prior period means no percentage - not a fabricated 100%."""
        make_transaction(
            client,
            user_a["headers"],
            amount="1000.00",
            occurred_on=month_start(date.today()),
            category_id=categories["Food"],
        )
        body = client.get("/api/dashboard", headers=user_a["headers"]).json()
        expenses = next(m for m in body["metrics"] if m["key"] == "monthly_expenses")
        assert expenses["change_pct"] is None

    def test_serialises_with_budget_and_goals_present(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """Regression: nested ORM objects must not reach the serialiser.

        The budget summary embeds category details and the goal summary embeds
        the soonest goal; both live inside untyped dict fields, so they must be
        flattened to primitives before the response is built.
        """
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="3000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )
        client.post(
            "/api/budgets",
            json={
                "name": "B",
                "period_month": today.strftime("%Y-%m"),
                "items": [{"category_id": categories["Food"], "limit_amount": "8000"}],
            },
            headers=user_a["headers"],
        )
        client.post(
            "/api/goals",
            json={
                "name": "Trip",
                "target_amount": "50000",
                "current_amount": "5000",
                "target_date": (today + timedelta(days=200)).isoformat(),
            },
            headers=user_a["headers"],
        )

        response = client.get("/api/dashboard", headers=user_a["headers"])
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["budget_summary"] is not None
        assert body["budget_summary"]["top_categories"][0]["category"] == "Food"
        assert body["goal_summary"]["next_goal"]["name"] == "Trip"
        # Contributions are ORM rows and must not be embedded here.
        assert "contributions" not in body["goal_summary"]["next_goal"]

    def test_daily_series_includes_zero_days(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="500.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.get("/api/dashboard", headers=user_a["headers"]).json()
        daily = body["daily_spending"]
        # Every day from the 1st to today is present, including empty ones.
        assert len(daily) == (today - month_start(today)).days + 1
        assert any(float(d["expense"]) == 0.0 for d in daily) or len(daily) == 1


class TestAnalytics:
    @pytest.fixture
    def populated(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        for amount, category, merchant in [
            ("3000.00", "Food", "Swiggy"),
            ("2000.00", "Food", "Zomato"),
            ("5000.00", "Shopping", "Amazon India"),
            ("1000.00", "Transport", "Uber India"),
        ]:
            make_transaction(
                client,
                user_a["headers"],
                amount=amount,
                merchant=merchant,
                category_id=categories[category],
                occurred_on=today - timedelta(days=2),
            )
        make_transaction(
            client,
            user_a["headers"],
            amount="60000.00",
            tx_type="income",
            merchant="Employer",
            category_id=categories["Salary"],
            occurred_on=today - timedelta(days=2),
        )
        return categories

    def test_totals(self, client: TestClient, user_a: dict, populated):
        body = client.get("/api/analytics/spending?range=30d", headers=user_a["headers"]).json()
        totals = body["totals"]
        assert float(totals["expense"]) == 11000.0
        assert float(totals["income"]) == 60000.0
        assert float(totals["savings"]) == 49000.0

    def test_category_breakdown_percentages_sum_to_100(
        self, client: TestClient, user_a: dict, populated
    ):
        body = client.get("/api/analytics/spending?range=30d", headers=user_a["headers"]).json()
        percentages = sum(c["percentage"] for c in body["by_category"])
        assert abs(percentages - 100.0) < 0.5

        food = next(c for c in body["by_category"] if c["category"] == "Food")
        assert float(food["amount"]) == 5000.0
        assert food["transaction_count"] == 2

    def test_merchant_breakdown(self, client: TestClient, user_a: dict, populated):
        body = client.get("/api/analytics/spending?range=30d", headers=user_a["headers"]).json()
        merchants = {m["merchant"]: m for m in body["by_merchant"]}
        assert float(merchants["Amazon India"]["amount"]) == 5000.0
        assert merchants["Amazon India"]["category"] == "Shopping"

    def test_stats(self, client: TestClient, user_a: dict, populated):
        body = client.get("/api/analytics/spending?range=30d", headers=user_a["headers"]).json()
        stats = body["stats"]
        assert stats["expense_count"] == 4
        assert float(stats["average_transaction"]) == 2750.0
        assert float(stats["largest_transaction"]) == 5000.0
        assert float(stats["smallest_transaction"]) == 1000.0

    def test_largest_expenses_sorted(self, client: TestClient, user_a: dict, populated):
        body = client.get("/api/analytics/spending?range=30d", headers=user_a["headers"]).json()
        amounts = [float(t["amount"]) for t in body["largest_expenses"]]
        assert amounts == sorted(amounts, reverse=True)
        assert amounts[0] == 5000.0

    @pytest.mark.parametrize("preset", ["7d", "30d", "3m", "6m", "1y", "mtd", "all"])
    def test_all_range_presets(self, client: TestClient, user_a: dict, populated, preset):
        response = client.get(f"/api/analytics/spending?range={preset}", headers=user_a["headers"])
        assert response.status_code == 200
        assert response.json()["period"]["days"] > 0

    def test_custom_range(self, client: TestClient, user_a: dict, populated):
        today = date.today()
        start = (today - timedelta(days=5)).isoformat()
        response = client.get(
            f"/api/analytics/spending?start={start}&end={today.isoformat()}",
            headers=user_a["headers"],
        )
        assert response.status_code == 200
        assert response.json()["period"]["start"] == start

    def test_comparison_period_is_equal_length(self, client: TestClient, user_a: dict, populated):
        body = client.get("/api/analytics/spending?range=30d", headers=user_a["headers"]).json()
        assert body["period"]["days"] == body["comparison_period"]["days"]
        assert body["comparison_period"]["end"] < body["period"]["start"]

    def test_recurring_detection(self, client: TestClient, user_a: dict, categories: dict):
        """A merchant charged monthly at a steady amount should be detected."""
        today = date.today()
        for offset in range(5):
            month = month_start(add_months(today, -offset))
            make_transaction(
                client,
                user_a["headers"],
                amount="649.00",
                merchant="Netflix",
                occurred_on=month.replace(day=7),
                category_id=categories["Entertainment"],
            )

        body = client.get("/api/analytics/spending?range=6m", headers=user_a["headers"]).json()
        recurring = {r["merchant"]: r for r in body["recurring"]}
        assert "Netflix" in recurring
        assert recurring["Netflix"]["cadence"] == "monthly"
        assert recurring["Netflix"]["occurrences"] >= 3
        assert recurring["Netflix"]["confidence"] > 0.5

    def test_irregular_merchant_not_marked_recurring(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        for days_ago, amount in [(2, "300"), (9, "1500"), (55, "80"), (120, "4000")]:
            make_transaction(
                client,
                user_a["headers"],
                amount=f"{amount}.00",
                merchant="Random Shop",
                occurred_on=today - timedelta(days=days_ago),
                category_id=categories["Shopping"],
            )

        body = client.get("/api/analytics/spending?range=6m", headers=user_a["headers"]).json()
        assert "Random Shop" not in {r["merchant"] for r in body["recurring"]}


class TestForecasting:
    def test_declines_below_three_months(self, client: TestClient, user_a: dict, categories: dict):
        make_transaction(
            client, user_a["headers"], amount="1000.00", category_id=categories["Food"]
        )

        body = client.get("/api/forecast", headers=user_a["headers"]).json()
        assert body["sufficient_data"] is False
        assert body["income"] is None and body["expense"] is None
        assert "3 complete months" in body["message"]
        assert body["limitations"]

    def test_forecasts_with_enough_history(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        seed_history(
            client,
            user_a["headers"],
            categories["Food"],
            months=7,
            monthly_amount=Decimal("8000"),
            per_month=2,
            today=today,
        )
        add_income(
            client,
            user_a["headers"],
            categories["Salary"],
            months=7,
            amount="60000.00",
            today=today,
        )

        body = client.get("/api/forecast?horizon=3", headers=user_a["headers"]).json()
        assert body["sufficient_data"] is True
        assert body["months_of_history"] >= 3
        assert body["expense"] is not None
        assert len(body["expense"]["forecast"]) == 3
        assert body["expense"]["method"]
        assert body["expense"]["model_detail"]

    def test_forecast_values_are_plausible(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        seed_history(
            client,
            user_a["headers"],
            categories["Food"],
            months=8,
            monthly_amount=Decimal("10000"),
            per_month=2,
            today=today,
        )

        body = client.get("/api/forecast", headers=user_a["headers"]).json()
        forecast = body["expense"]["forecast"]

        for point in forecast:
            value = float(point["value"])
            # Steady 10k/month history should forecast near 10k, never negative.
            assert 0 <= value <= 30000, value
            assert point["is_forecast"] is True
            # Interval must bracket the point estimate.
            assert float(point["lower"]) <= value <= float(point["upper"])

    def test_intervals_widen_with_horizon(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        for offset in range(8):
            month = month_start(add_months(today, -offset))
            amount = 8000 + (offset * 400)
            make_transaction(
                client,
                user_a["headers"],
                amount=f"{amount}.00",
                occurred_on=month.replace(day=10),
                category_id=categories["Food"],
            )

        body = client.get("/api/forecast?horizon=4", headers=user_a["headers"]).json()
        forecast = body["expense"]["forecast"]
        widths = [float(p["upper"]) - float(p["lower"]) for p in forecast]
        assert widths[-1] >= widths[0], "uncertainty must not shrink with distance"

    def test_limitations_are_always_stated(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        seed_history(
            client,
            user_a["headers"],
            categories["Food"],
            months=6,
            monthly_amount=Decimal("5000"),
            per_month=2,
            today=today,
        )

        body = client.get("/api/forecast", headers=user_a["headers"]).json()
        assert len(body["limitations"]) >= 3
        text = " ".join(body["limitations"]).lower()
        assert "not" in text and ("guarantee" in text or "prediction" in text)
        assert body["method_explanation"]

    def test_horizon_is_bounded(self, client: TestClient, user_a: dict):
        assert client.get("/api/forecast?horizon=99", headers=user_a["headers"]).status_code == 422

    def test_model_selection_by_series_length(self):
        """Longer history must unlock a more capable model."""
        from app.ml.forecasting import forecast_series

        short = forecast_series([100.0, 110.0, 105.0], horizon=2)
        medium = forecast_series([100.0 + i for i in range(8)], horizon=2)
        long = forecast_series([100.0 + i * 2 for i in range(14)], horizon=2)

        assert short is not None and medium is not None and long is not None
        assert short.method in {"weighted_moving_average", "simple_exponential_smoothing"}
        assert long.method in {"holt_damped_trend", "holt_winters_additive"}

    def test_too_short_series_returns_none(self):
        from app.ml.forecasting import forecast_series

        assert forecast_series([100.0], horizon=3) is None
        assert forecast_series([100.0, 110.0], horizon=3) is None

    def test_constant_series_is_handled(self):
        from app.ml.forecasting import forecast_series

        result = forecast_series([500.0] * 6, horizon=3)
        assert result is not None
        assert all(abs(v - 500.0) < 1e-6 for v in result.forecast)


class TestAnomalyDetection:
    def test_declines_without_enough_history(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        make_transaction(client, user_a["headers"], amount="500.00", category_id=categories["Food"])

        body = client.get("/api/anomalies", headers=user_a["headers"]).json()
        assert body["sufficient_data"] is False
        assert body["anomalies"] == []
        assert "12" in body["message"]

    def test_detects_a_genuine_outlier(self, client: TestClient, user_a: dict, categories: dict):
        """The spec's example: normal 200-800, then a sudden 8,500."""
        today = date.today()
        for index in range(20):
            make_transaction(
                client,
                user_a["headers"],
                amount=f"{300 + (index % 6) * 90}.00",
                merchant=f"Cafe {index % 4}",
                occurred_on=today - timedelta(days=index + 2),
                category_id=categories["Food"],
            )

        outlier = make_transaction(
            client,
            user_a["headers"],
            amount="8500.00",
            merchant="Fancy Restaurant",
            occurred_on=today,
            category_id=categories["Food"],
        )

        body = client.get("/api/anomalies", headers=user_a["headers"]).json()
        assert body["sufficient_data"] is True
        flagged = {a["transaction"]["id"] for a in body["anomalies"]}
        assert outlier["id"] in flagged

        entry = next(a for a in body["anomalies"] if a["transaction"]["id"] == outlier["id"])
        assert "8,500" in entry["reason"]
        assert entry["detail"]["category_median"] > 0
        assert entry["detail"]["times_median"] > 5
        assert entry["detail"]["detector"] in {"robust_zscore", "isolation_forest"}

    def test_normal_transactions_not_flagged(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        for index in range(20):
            make_transaction(
                client,
                user_a["headers"],
                amount=f"{400 + (index % 5) * 50}.00",
                occurred_on=today - timedelta(days=index + 1),
                category_id=categories["Food"],
            )

        body = client.get("/api/anomalies", headers=user_a["headers"]).json()
        # A tight, uniform distribution should produce few or no flags.
        assert len(body["anomalies"]) <= 2

    def test_baseline_is_from_the_users_own_data(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        for index in range(15):
            make_transaction(
                client,
                user_a["headers"],
                amount="1000.00",
                occurred_on=today - timedelta(days=index + 1),
                category_id=categories["Food"],
            )

        body = client.get("/api/anomalies", headers=user_a["headers"]).json()
        baseline = body["baseline"]
        assert baseline["transactions_analyzed"] == 15
        assert baseline["median_amount"] == 1000.0
        assert body["explanation"]

    def test_feedback_prevents_reflagging(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        for index in range(20):
            make_transaction(
                client,
                user_a["headers"],
                amount="500.00",
                occurred_on=today - timedelta(days=index + 2),
                category_id=categories["Food"],
            )
        outlier = make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=today,
            category_id=categories["Food"],
        )

        body = client.get("/api/anomalies", headers=user_a["headers"]).json()
        assert outlier["id"] in {a["transaction"]["id"] for a in body["anomalies"]}

        marked = client.post(
            f"/api/transactions/{outlier['id']}/anomaly-feedback",
            json={"status": "expected"},
            headers=user_a["headers"],
        )
        assert marked.status_code == 200
        assert marked.json()["anomaly_status"] == "expected"

        after = client.get("/api/anomalies", headers=user_a["headers"]).json()
        assert outlier["id"] not in {a["transaction"]["id"] for a in after["anomalies"]}

    def test_invalid_feedback_status_rejected(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        response = client.post(
            f"/api/transactions/{tx['id']}/anomaly-feedback",
            json={"status": "flagged"},
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_detection_is_scoped_per_user(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        today = date.today()
        for index in range(20):
            make_transaction(
                client,
                user_a["headers"],
                amount="500.00",
                occurred_on=today - timedelta(days=index + 1),
                category_id=categories["Food"],
            )
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=today,
            category_id=categories["Food"],
        )

        body = client.get("/api/anomalies", headers=user_b["headers"]).json()
        assert body["sufficient_data"] is False
        assert body["anomalies"] == []

    def test_mad_zero_fallback(self):
        """Identical amounts collapse MAD to zero; detection must still work."""
        from app.ml.anomaly import TransactionFeatures, detect

        features = [
            TransactionFeatures(
                f"t{i}", 199.0, date.today() - timedelta(days=i), "c1", "Entertainment", "Netflix"
            )
            for i in range(15)
        ]
        features.append(
            TransactionFeatures("odd", 15000.0, date.today(), "c1", "Entertainment", "Netflix")
        )

        verdicts, baseline, _ = detect(features)
        odd = next(v for v in verdicts if v.transaction_id == "odd")
        assert odd.is_anomaly is True
        assert baseline is not None


class TestHealthScore:
    def test_empty_state(self, client: TestClient, user_a: dict):
        body = client.get("/api/health-score", headers=user_a["headers"]).json()
        assert body["has_data"] is False
        assert body["score"] == 0.0
        assert body["disclaimer"]

    def test_components_and_bounds(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        add_income(
            client,
            user_a["headers"],
            categories["Salary"],
            months=3,
            amount="100000.00",
            today=today,
        )
        seed_history(
            client,
            user_a["headers"],
            categories["Food"],
            months=3,
            monthly_amount=Decimal("70000"),
            per_month=2,
            today=today,
        )

        body = client.get("/api/health-score", headers=user_a["headers"]).json()
        assert 0 <= body["score"] <= 100
        assert body["grade"] in {"A", "B", "C", "D", "E"}
        assert len(body["components"]) == 6

        for component in body["components"]:
            assert 0 <= component["score"] <= 100
            assert component["explanation"]
            assert component["impact"] in {"positive", "neutral", "negative"}
            assert isinstance(component["available"], bool)

    def test_savings_rate_drives_the_score(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        today = date.today()

        # Saver: 100k income, 30k expenses.
        add_income(
            client,
            user_a["headers"],
            categories["Salary"],
            months=3,
            amount="100000.00",
            today=today,
        )
        seed_history(
            client,
            user_a["headers"],
            categories["Food"],
            months=3,
            monthly_amount=Decimal("30000"),
            per_month=2,
            today=today,
        )

        # Overspender: 100k income, 110k expenses.
        b_categories = {
            c["name"]: c["id"]
            for c in client.get("/api/categories", headers=user_b["headers"]).json()
        }
        add_income(
            client,
            user_b["headers"],
            b_categories["Salary"],
            months=3,
            amount="100000.00",
            today=today,
        )
        seed_history(
            client,
            user_b["headers"],
            b_categories["Food"],
            months=3,
            monthly_amount=Decimal("110000"),
            per_month=2,
            today=today,
        )

        saver = client.get("/api/health-score", headers=user_a["headers"]).json()
        spender = client.get("/api/health-score", headers=user_b["headers"]).json()

        assert saver["score"] > spender["score"]
        saver_savings = next(c for c in saver["components"] if c["key"] == "savings_rate")
        spender_savings = next(c for c in spender["components"] if c["key"] == "savings_rate")
        assert saver_savings["score"] > spender_savings["score"]
        assert spender_savings["score"] == 0.0

    def test_unmeasurable_components_are_excluded_not_zeroed(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """A user with no budget must not be punished for a component we can't assess."""
        today = date.today()
        add_income(
            client,
            user_a["headers"],
            categories["Salary"],
            months=3,
            amount="100000.00",
            today=today,
        )
        seed_history(
            client,
            user_a["headers"],
            categories["Food"],
            months=3,
            monthly_amount=Decimal("20000"),
            per_month=2,
            today=today,
        )

        body = client.get("/api/health-score", headers=user_a["headers"]).json()
        budget = next(c for c in body["components"] if c["key"] == "budget_adherence")
        assert budget["available"] is False
        assert "no budget" in budget["value"].lower()

        # Excluded components carry a zero sub-score but are renormalised out,
        # so a good saver still scores well overall.
        assert body["score"] > 50

    def test_methodology_and_disclaimer_present(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        body = client.get("/api/health-score", headers=user_a["headers"]).json()
        assert "weighted average" in body["methodology"].lower()
        assert "not" in body["disclaimer"].lower()
        assert "advice" in body["disclaimer"].lower()
