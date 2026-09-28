"""Goals, the insight engine and the AI assistant's data-retrieval layer."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from tests.conftest import make_transaction

from app.utils.dates import add_months, month_key, month_start


class TestGoals:
    def test_create_and_compute_progress(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/goals",
            json={
                "name": "Emergency Fund",
                "target_amount": "300000",
                "current_amount": "75000",
                "goal_type": "emergency_fund",
                "target_date": (date.today() + timedelta(days=365)).isoformat(),
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 201
        body = response.json()
        assert body["progress_pct"] == 25.0
        assert float(body["remaining"]) == 225000.0
        assert body["status"] == "active"

    def test_suggested_monthly_contribution(self, client: TestClient, user_a: dict):
        target_date = add_months(date.today(), 10)
        body = client.post(
            "/api/goals",
            json={
                "name": "Laptop",
                "target_amount": "100000",
                "current_amount": "0",
                "target_date": target_date.isoformat(),
            },
            headers=user_a["headers"],
        ).json()

        assert body["months_remaining"] == 10
        assert float(body["suggested_monthly_contribution"]) == 10000.0

    def test_contribution_updates_balance_and_ledger(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Trip", "target_amount": "50000", "current_amount": "0"},
            headers=user_a["headers"],
        ).json()

        updated = client.post(
            f"/api/goals/{goal['id']}/contributions",
            json={"amount": "12500", "note": "Salary transfer"},
            headers=user_a["headers"],
        ).json()

        assert float(updated["current_amount"]) == 12500.0
        assert updated["progress_pct"] == 25.0
        assert len(updated["contributions"]) == 1
        assert updated["contributions"][0]["note"] == "Salary transfer"

    def test_withdrawal_allowed_within_balance(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Flex", "target_amount": "50000", "current_amount": "20000"},
            headers=user_a["headers"],
        ).json()

        updated = client.post(
            f"/api/goals/{goal['id']}/contributions",
            json={"amount": "-5000", "note": "Needed it"},
            headers=user_a["headers"],
        ).json()
        assert float(updated["current_amount"]) == 15000.0

    def test_cannot_withdraw_below_zero(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Small", "target_amount": "50000", "current_amount": "1000"},
            headers=user_a["headers"],
        ).json()

        response = client.post(
            f"/api/goals/{goal['id']}/contributions",
            json={"amount": "-5000"},
            headers=user_a["headers"],
        )
        assert response.status_code == 400
        assert "below zero" in response.json()["detail"]

    def test_zero_contribution_rejected(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "G", "target_amount": "1000"},
            headers=user_a["headers"],
        ).json()
        assert (
            client.post(
                f"/api/goals/{goal['id']}/contributions",
                json={"amount": "0"},
                headers=user_a["headers"],
            ).status_code
            == 422
        )

    def test_goal_marked_achieved_on_target(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Nearly", "target_amount": "10000", "current_amount": "9000"},
            headers=user_a["headers"],
        ).json()

        updated = client.post(
            f"/api/goals/{goal['id']}/contributions",
            json={"amount": "1000"},
            headers=user_a["headers"],
        ).json()

        assert updated["status"] == "achieved"
        assert updated["progress_pct"] == 100.0
        assert "reached" in updated["pace_note"].lower()

    def test_raising_target_reopens_an_achieved_goal(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Done", "target_amount": "1000", "current_amount": "1000"},
            headers=user_a["headers"],
        ).json()
        assert goal["status"] == "achieved"

        updated = client.put(
            f"/api/goals/{goal['id']}",
            json={"target_amount": "5000"},
            headers=user_a["headers"],
        ).json()
        assert updated["status"] == "active"

    def test_projection_from_actual_pace(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={
                "name": "Paced",
                "target_amount": "60000",
                "current_amount": "0",
                "target_date": add_months(date.today(), 12).isoformat(),
            },
            headers=user_a["headers"],
        ).json()

        for offset in range(3):
            client.post(
                f"/api/goals/{goal['id']}/contributions",
                json={
                    "amount": "5000",
                    "occurred_on": month_start(add_months(date.today(), -offset)).isoformat(),
                },
                headers=user_a["headers"],
            )

        body = client.get(f"/api/goals/{goal['id']}", headers=user_a["headers"]).json()
        assert body["projected_completion"] is not None
        assert body["on_track"] is not None
        assert "month" in body["pace_note"].lower()

    def test_no_pace_yet_says_so(self, client: TestClient, user_a: dict):
        body = client.post(
            "/api/goals",
            json={"name": "Fresh", "target_amount": "10000", "current_amount": "0"},
            headers=user_a["headers"],
        ).json()
        assert body["projected_completion"] is None
        assert body["pace_note"]

    def test_past_target_date_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/goals",
            json={
                "name": "Past",
                "target_amount": "1000",
                "target_date": (date.today() - timedelta(days=1)).isoformat(),
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_summary(self, client: TestClient, user_a: dict):
        client.post(
            "/api/goals",
            json={"name": "A", "target_amount": "10000", "current_amount": "5000"},
            headers=user_a["headers"],
        )
        client.post(
            "/api/goals",
            json={"name": "B", "target_amount": "10000", "current_amount": "2500"},
            headers=user_a["headers"],
        )

        summary = client.get("/api/goals/summary", headers=user_a["headers"]).json()
        assert summary["total_goals"] == 2
        assert summary["active_goals"] == 2
        assert float(summary["total_saved"]) == 7500.0
        assert summary["overall_progress"] == 37.5

    def test_delete(self, client: TestClient, user_a: dict):
        goal = client.post(
            "/api/goals",
            json={"name": "Temp", "target_amount": "1000"},
            headers=user_a["headers"],
        ).json()
        assert (
            client.delete(f"/api/goals/{goal['id']}", headers=user_a["headers"]).status_code == 200
        )
        assert client.get(f"/api/goals/{goal['id']}", headers=user_a["headers"]).status_code == 404


class TestInsightEngine:
    def test_no_insights_without_data(self, client: TestClient, user_a: dict):
        body = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        assert body["generated"] == 0
        assert body["note"]

    def test_detects_category_spending_increase(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        last_month = month_start(add_months(today, -1))

        # Spend more this month than the same stretch of last month.
        make_transaction(
            client,
            user_a["headers"],
            amount="4000.00",
            occurred_on=last_month,
            category_id=categories["Food"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        increases = [i for i in body["insights"] if i["type"] == "spending_increase"]
        assert increases

        insight = increases[0]
        assert insight["data"]["category"] == "Food"
        assert float(insight["data"]["current_amount"]) == 9000.0
        assert float(insight["data"]["previous_amount"]) == 4000.0
        assert insight["data"]["change_percentage"] == 125.0
        assert insight["why_it_matters"]
        assert insight["suggested_action"]

    def test_small_changes_are_not_reported(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """A tiny absolute change is noise, not an insight."""
        today = date.today()
        last_month = month_start(add_months(today, -1))
        make_transaction(
            client,
            user_a["headers"],
            amount="100.00",
            occurred_on=last_month,
            category_id=categories["Food"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="180.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        assert not [
            i
            for i in body["insights"]
            if i["type"] == "spending_increase" and i["data"]["category"] == "Food"
        ]

    def test_detects_budget_exceeded(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        client.post(
            "/api/budgets",
            json={
                "name": "Tight",
                "period_month": month_key(today),
                "items": [{"category_id": categories["Food"], "limit_amount": "5000"}],
            },
            headers=user_a["headers"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="7000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        exceeded = [i for i in body["insights"] if i["type"] == "budget_exceeded"]
        assert exceeded
        assert exceeded[0]["severity"] == "critical"
        assert float(exceeded[0]["data"]["spent"]) == 7000.0
        assert float(exceeded[0]["data"]["limit"]) == 5000.0

    def test_insight_numbers_come_from_the_database(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """Every figure in an insight must be traceable to stored rows."""
        today = date.today()
        last_month = month_start(add_months(today, -1))
        make_transaction(
            client,
            user_a["headers"],
            amount="3000.00",
            occurred_on=last_month,
            category_id=categories["Shopping"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="8000.00",
            occurred_on=month_start(today),
            category_id=categories["Shopping"],
        )

        body = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        shopping = next(
            i
            for i in body["insights"]
            if i["data"].get("category") == "Shopping" and i["type"] == "spending_increase"
        )

        analytics = client.get(
            "/api/analytics/spending?range=mtd", headers=user_a["headers"]
        ).json()
        actual = next(c for c in analytics["by_category"] if c["category"] == "Shopping")
        assert float(shopping["data"]["current_amount"]) == float(actual["amount"])

    def test_generation_is_idempotent(self, client: TestClient, user_a: dict, categories: dict):
        """Re-running must refresh findings, not duplicate them."""
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="4000.00",
            occurred_on=month_start(add_months(today, -1)),
            category_id=categories["Food"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        first = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        second = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        assert first["generated"] == second["generated"]

        listed = client.get("/api/insights", headers=user_a["headers"]).json()
        fingerprints = [i["id"] for i in listed]
        assert len(fingerprints) == len(set(fingerprints))

    def test_works_without_ai_configured(self, client: TestClient, user_a: dict, categories: dict):
        """No API key must not mean no insights."""
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="4000.00",
            occurred_on=month_start(add_months(today, -1)),
            category_id=categories["Food"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.post("/api/insights/generate", headers=user_a["headers"]).json()
        assert body["ai_enabled"] is False
        assert body["generated"] > 0
        for insight in body["insights"]:
            assert insight["summary"]
            assert insight["ai_explanation"] is None

    def test_read_and_dismiss(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="4000.00",
            occurred_on=month_start(add_months(today, -1)),
            category_id=categories["Food"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )
        client.post("/api/insights/generate", headers=user_a["headers"])

        insights = client.get("/api/insights", headers=user_a["headers"]).json()
        assert insights
        target = insights[0]

        assert (
            client.post(f"/api/insights/{target['id']}/read", headers=user_a["headers"]).json()[
                "is_read"
            ]
            is True
        )
        assert (
            client.post(
                f"/api/insights/{target['id']}/dismiss", headers=user_a["headers"]
            ).status_code
            == 200
        )

        remaining = client.get("/api/insights", headers=user_a["headers"]).json()
        assert target["id"] not in {i["id"] for i in remaining}

    def test_insights_are_user_scoped(
        self, client: TestClient, user_a: dict, user_b: dict, categories: dict
    ):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="4000.00",
            occurred_on=month_start(add_months(today, -1)),
            category_id=categories["Food"],
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="9000.00",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )
        client.post("/api/insights/generate", headers=user_a["headers"])

        assert client.get("/api/insights", headers=user_b["headers"]).json() == []


class TestAIAssistant:
    def test_status_reports_deterministic_mode(self, client: TestClient, user_a: dict):
        body = client.get("/api/ai/status", headers=user_a["headers"]).json()
        assert body["configured"] is False
        assert body["mode"] == "deterministic"
        assert len(body["available_tools"]) >= 10
        assert "built-in" in body["message"] or "built in" in body["message"]

    def test_chat_runs_data_tools(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="6250.00",
            merchant="Swiggy",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.post(
            "/api/ai/chat",
            json={"message": "How much did I spend on food this month?"},
            headers=user_a["headers"],
        ).json()

        assert body["tools_used"]
        assert "get_category_spending" in {t["name"] for t in body["tools_used"]}
        assert body["generation_mode"] == "deterministic"

    def test_answer_uses_real_figures(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="6250.00",
            merchant="Swiggy",
            occurred_on=month_start(today),
            category_id=categories["Food"],
        )

        body = client.post(
            "/api/ai/chat",
            json={"message": "How much did I spend on food this month?"},
            headers=user_a["headers"],
        ).json()

        assert "6,250" in body["message"]["content"]
        facts = body["message"]["retrieved_facts"]
        assert facts["get_category_spending"]["total"] == 6250.0

    def test_says_so_when_data_is_missing(self, client: TestClient, user_a: dict):
        body = client.post(
            "/api/ai/chat",
            json={"message": "How much did I spend on travel last month?"},
            headers=user_a["headers"],
        ).json()

        content = body["message"]["content"].lower()
        assert any(phrase in content for phrase in ("no ", "not", "couldn't", "recorded", "add "))

    def test_does_not_invent_unavailable_information(self, client: TestClient, user_a: dict):
        """A question about data Finora does not hold must not be answered."""
        body = client.post(
            "/api/ai/chat",
            json={"message": "What is the balance of my HDFC savings account?"},
            headers=user_a["headers"],
        ).json()

        content = body["message"]["content"]
        # Only tool-retrieved facts may appear; no account numbers or balances.
        for tool in body["tools_used"]:
            assert tool["name"] in {
                t["name"]
                for t in client.get("/api/ai/status", headers=user_a["headers"]).json()[
                    "available_tools"
                ]
            }
        assert "HDFC" not in content

    @pytest.mark.parametrize(
        "question,expected_tool",
        [
            ("What is my financial health score?", "get_financial_health"),
            ("What does my cash flow look like next month?", "get_forecast"),
            ("How am I doing against my budget?", "get_budget_status"),
            ("Are there any unusual transactions?", "get_anomalies"),
            ("Where did I spend the most this month?", "get_category_spending"),
            ("Why are my expenses higher this month?", "compare_periods"),
        ],
    )
    def test_routing_picks_relevant_tools(
        self, client: TestClient, user_a: dict, question: str, expected_tool: str
    ):
        body = client.post(
            "/api/ai/chat", json={"message": question}, headers=user_a["headers"]
        ).json()
        assert expected_tool in {t["name"] for t in body["tools_used"]}

    def test_savings_simulation_arithmetic_is_backend_computed(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="10000.00",
            merchant="Amazon India",
            occurred_on=month_start(today),
            category_id=categories["Shopping"],
        )

        body = client.post(
            "/api/ai/chat",
            json={"message": "How much can I save if I cut shopping by 20%?"},
            headers=user_a["headers"],
        ).json()

        facts = body["message"]["retrieved_facts"]
        simulation = facts.get("get_savings_simulation")
        assert simulation is not None
        assert simulation["reduction_pct"] == 20.0
        assert simulation["current_spend"] == 10000.0
        assert simulation["saving_over_period"] == 2000.0

    def test_conversation_is_persisted(self, client: TestClient, user_a: dict):
        first = client.post(
            "/api/ai/chat",
            json={"message": "What did I spend this month?"},
            headers=user_a["headers"],
        ).json()
        conversation_id = first["conversation_id"]

        second = client.post(
            "/api/ai/chat",
            json={"message": "And last month?", "conversation_id": conversation_id},
            headers=user_a["headers"],
        ).json()
        assert second["conversation_id"] == conversation_id

        detail = client.get(
            f"/api/ai/conversations/{conversation_id}", headers=user_a["headers"]
        ).json()
        assert len(detail["messages"]) == 4  # two exchanges
        roles = [m["role"] for m in detail["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_conversations_are_user_scoped(self, client: TestClient, user_a: dict, user_b: dict):
        conversation_id = client.post(
            "/api/ai/chat", json={"message": "Hello"}, headers=user_a["headers"]
        ).json()["conversation_id"]

        assert (
            client.get(
                f"/api/ai/conversations/{conversation_id}", headers=user_b["headers"]
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/ai/chat",
                json={"message": "Sneaky", "conversation_id": conversation_id},
                headers=user_b["headers"],
            ).status_code
            == 404
        )
        assert client.get("/api/ai/conversations", headers=user_b["headers"]).json() == []

    def test_empty_message_rejected(self, client: TestClient, user_a: dict):
        assert (
            client.post("/api/ai/chat", json={"message": ""}, headers=user_a["headers"]).status_code
            == 422
        )

    def test_overlong_message_rejected(self, client: TestClient, user_a: dict):
        assert (
            client.post(
                "/api/ai/chat", json={"message": "x" * 5000}, headers=user_a["headers"]
            ).status_code
            == 422
        )

    def test_delete_conversation(self, client: TestClient, user_a: dict):
        conversation_id = client.post(
            "/api/ai/chat", json={"message": "Hi"}, headers=user_a["headers"]
        ).json()["conversation_id"]

        assert (
            client.delete(
                f"/api/ai/conversations/{conversation_id}", headers=user_a["headers"]
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/ai/conversations/{conversation_id}", headers=user_a["headers"]
            ).status_code
            == 404
        )

    def test_provider_failure_falls_back_gracefully(
        self, client: TestClient, user_a: dict, categories: dict, monkeypatch
    ):
        """An LLM outage must degrade phrasing, never correctness."""
        from app.ai import assistant
        from app.ai.provider import LLMError, LLMProvider

        class BrokenProvider(LLMProvider):
            name = "broken"

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                raise LLMError("provider is down")

        monkeypatch.setattr(assistant, "get_provider", lambda: BrokenProvider())

        make_transaction(
            client,
            user_a["headers"],
            amount="6250.00",
            occurred_on=month_start(date.today()),
            category_id=categories["Food"],
        )

        body = client.post(
            "/api/ai/chat",
            json={"message": "How much did I spend on food this month?"},
            headers=user_a["headers"],
        ).json()

        assert body["generation_mode"] == "deterministic"
        assert "6,250" in body["message"]["content"]

    def test_period_parsing(self):
        from app.ai.tools import parse_period

        today = date(2026, 9, 28)

        this_month, label = parse_period("how much this month", today)
        assert this_month.start == date(2026, 9, 1)
        assert label == "this month"

        last_month, label = parse_period("what about last month", today)
        assert last_month.start == date(2026, 8, 1)
        assert last_month.end == date(2026, 8, 31)

        named, label = parse_period("spending in August", today)
        assert named.start == date(2026, 8, 1)

        week, label = parse_period("last week spending", today)
        assert week.days == 7

    def test_category_extraction_handles_synonyms(self, client: TestClient, user_a: dict, session):
        from app.ai.tools import extract_category
        from app.services import auth_service

        user = auth_service.get_by_email(session, "alice@finora.app")
        assert extract_category(session, user, "how much on dining out") == "Food"
        assert extract_category(session, user, "my uber costs") == "Transport"
        assert extract_category(session, user, "netflix and streaming") == "Entertainment"
        assert extract_category(session, user, "random gibberish") is None
