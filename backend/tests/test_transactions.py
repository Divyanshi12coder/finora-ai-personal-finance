"""Transaction CRUD, validation, filtering and the ML feedback loop."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from tests.conftest import make_transaction


class TestTransactionCrud:
    def test_create_and_persist(self, client: TestClient, user_a: dict, categories: dict):
        created = make_transaction(
            client,
            user_a["headers"],
            amount="1234.56",
            merchant="Swiggy",
            category_id=categories["Food"],
        )
        assert float(created["amount"]) == 1234.56
        assert created["category"]["name"] == "Food"

        # Re-fetch proves it is in the database, not just the response.
        fetched = client.get(f"/api/transactions/{created['id']}", headers=user_a["headers"])
        assert fetched.status_code == 200
        assert fetched.json()["id"] == created["id"]
        assert float(fetched.json()["amount"]) == 1234.56

    def test_update(self, client: TestClient, user_a: dict, categories: dict):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        response = client.put(
            f"/api/transactions/{tx['id']}",
            json={"amount": "999.99", "merchant": "Zomato", "notes": "changed"},
            headers=user_a["headers"],
        )
        assert response.status_code == 200
        body = response.json()
        assert float(body["amount"]) == 999.99
        assert body["merchant"] == "Zomato"
        assert body["notes"] == "changed"

    def test_delete(self, client: TestClient, user_a: dict, categories: dict):
        tx = make_transaction(client, user_a["headers"], category_id=categories["Food"])
        assert (
            client.delete(f"/api/transactions/{tx['id']}", headers=user_a["headers"]).status_code
            == 200
        )
        assert (
            client.get(f"/api/transactions/{tx['id']}", headers=user_a["headers"]).status_code
            == 404
        )

    def test_bulk_delete(self, client: TestClient, user_a: dict, categories: dict):
        ids = [
            make_transaction(client, user_a["headers"], category_id=categories["Food"])["id"]
            for _ in range(3)
        ]
        response = client.post(
            "/api/transactions/bulk-delete", json={"ids": ids}, headers=user_a["headers"]
        )
        assert response.status_code == 200
        assert "3 transaction" in response.json()["detail"]
        assert client.get("/api/transactions", headers=user_a["headers"]).json()["total"] == 0

    def test_missing_transaction_returns_404(self, client: TestClient, user_a: dict):
        assert (
            client.get("/api/transactions/does-not-exist", headers=user_a["headers"]).status_code
            == 404
        )

    def test_unknown_category_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/transactions",
            json={
                "amount": "100.00",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "category_id": "no-such-category",
                "auto_categorize": False,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 400


class TestTransactionValidation:
    @pytest.mark.parametrize("amount", ["0", "-100", "-0.01"])
    def test_non_positive_amount_rejected(self, client: TestClient, user_a: dict, amount: str):
        response = client.post(
            "/api/transactions",
            json={
                "amount": amount,
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "auto_categorize": False,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_absurd_amount_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/transactions",
            json={
                "amount": "999999999999",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "auto_categorize": False,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_invalid_type_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/transactions",
            json={
                "amount": "100",
                "type": "withdrawal",
                "occurred_on": date.today().isoformat(),
                "auto_categorize": False,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_far_future_date_rejected(self, client: TestClient, user_a: dict):
        far = (date.today() + timedelta(days=400)).isoformat()
        response = client.post(
            "/api/transactions",
            json={"amount": "100", "type": "expense", "occurred_on": far, "auto_categorize": False},
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_near_future_date_allowed(self, client: TestClient, user_a: dict):
        """Scheduled payments are legitimate."""
        soon = (date.today() + timedelta(days=5)).isoformat()
        response = client.post(
            "/api/transactions",
            json={
                "amount": "100",
                "type": "expense",
                "occurred_on": soon,
                "auto_categorize": False,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 201

    def test_tags_deduplicated_and_trimmed(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/transactions",
            json={
                "amount": "100",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "tags": ["  food  ", "food", "treat", ""],
                "auto_categorize": False,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 201
        assert response.json()["tags"] == ["food", "treat"]

    def test_invalid_sort_field_rejected(self, client: TestClient, user_a: dict):
        response = client.get(
            "/api/transactions?sort_by=amount);DROP TABLE users;--",
            headers=user_a["headers"],
        )
        assert response.status_code == 400

    def test_page_size_capped(self, client: TestClient, user_a: dict):
        assert (
            client.get("/api/transactions?page_size=5000", headers=user_a["headers"]).status_code
            == 422
        )


class TestFiltersAndPagination:
    @pytest.fixture
    def populated(self, client: TestClient, user_a: dict, categories: dict):
        today = date.today()
        make_transaction(
            client,
            user_a["headers"],
            amount="100.00",
            merchant="Swiggy",
            category_id=categories["Food"],
            occurred_on=today,
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="2000.00",
            merchant="Amazon India",
            category_id=categories["Shopping"],
            occurred_on=today - timedelta(days=5),
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="500.00",
            merchant="Uber India",
            category_id=categories["Transport"],
            occurred_on=today - timedelta(days=40),
        )
        make_transaction(
            client,
            user_a["headers"],
            amount="50000.00",
            tx_type="income",
            merchant="Employer",
            category_id=categories["Salary"],
            occurred_on=today,
        )
        return categories

    def test_filter_by_type(self, client: TestClient, user_a: dict, populated):
        income = client.get("/api/transactions?type=income", headers=user_a["headers"]).json()
        assert income["total"] == 1
        assert income["items"][0]["type"] == "income"

    def test_filter_by_category(self, client: TestClient, user_a: dict, populated):
        response = client.get(
            f"/api/transactions?category_id={populated['Food']}", headers=user_a["headers"]
        ).json()
        assert response["total"] == 1
        assert response["items"][0]["category"]["name"] == "Food"

    def test_filter_by_date_range(self, client: TestClient, user_a: dict, populated):
        start = (date.today() - timedelta(days=10)).isoformat()
        response = client.get(f"/api/transactions?start={start}", headers=user_a["headers"]).json()
        assert response["total"] == 3  # the 40-day-old one is excluded

    def test_filter_by_amount_range(self, client: TestClient, user_a: dict, populated):
        response = client.get(
            "/api/transactions?min_amount=400&max_amount=3000", headers=user_a["headers"]
        ).json()
        amounts = sorted(float(i["amount"]) for i in response["items"])
        assert amounts == [500.0, 2000.0]

    def test_search_matches_merchant(self, client: TestClient, user_a: dict, populated):
        response = client.get("/api/transactions?search=swig", headers=user_a["headers"]).json()
        assert response["total"] == 1
        assert response["items"][0]["merchant"] == "Swiggy"

    def test_search_is_parameterised(self, client: TestClient, user_a: dict, populated):
        """A SQL metacharacter in search must be treated as a literal."""
        response = client.get("/api/transactions?search=' OR 1=1 --", headers=user_a["headers"])
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_sorting(self, client: TestClient, user_a: dict, populated):
        asc = client.get(
            "/api/transactions?sort_by=amount&sort_dir=asc", headers=user_a["headers"]
        ).json()
        amounts = [float(i["amount"]) for i in asc["items"]]
        assert amounts == sorted(amounts)

    def test_pagination(self, client: TestClient, user_a: dict, populated):
        page1 = client.get("/api/transactions?page=1&page_size=2", headers=user_a["headers"]).json()
        page2 = client.get("/api/transactions?page=2&page_size=2", headers=user_a["headers"]).json()

        assert page1["total"] == page2["total"] == 4
        assert page1["pages"] == 2
        assert len(page1["items"]) == len(page2["items"]) == 2
        # No overlap between pages.
        assert not ({i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]})

    def test_payment_methods_endpoint(self, client: TestClient, user_a: dict, populated):
        methods = client.get("/api/transactions/payment-methods", headers=user_a["headers"]).json()
        assert "UPI" in methods


class TestCategories:
    def test_system_categories_seeded(self, client: TestClient, user_a: dict):
        categories = client.get("/api/categories", headers=user_a["headers"]).json()
        names = {c["name"] for c in categories}
        expected = {
            "Food",
            "Shopping",
            "Transport",
            "Bills",
            "Entertainment",
            "Healthcare",
            "Education",
            "Travel",
            "Rent",
            "Salary",
            "Investments",
            "Other",
        }
        assert expected <= names
        assert all(c["is_system"] for c in categories if c["name"] in expected)

    def test_create_custom_category(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/categories",
            json={"name": "Pet Care", "kind": "expense", "color": "#123456"},
            headers=user_a["headers"],
        )
        assert response.status_code == 201
        assert response.json()["is_system"] is False
        assert response.json()["color"] == "#123456"

    def test_duplicate_custom_category_rejected(self, client: TestClient, user_a: dict):
        client.post("/api/categories", json={"name": "Hobbies"}, headers=user_a["headers"])
        response = client.post(
            "/api/categories", json={"name": "Hobbies"}, headers=user_a["headers"]
        )
        assert response.status_code == 400

    def test_two_users_may_share_a_custom_name(
        self, client: TestClient, user_a: dict, user_b: dict
    ):
        assert (
            client.post(
                "/api/categories", json={"name": "Side Project"}, headers=user_a["headers"]
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/categories", json={"name": "Side Project"}, headers=user_b["headers"]
            ).status_code
            == 201
        )

    def test_system_category_cannot_be_edited_or_deleted(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        food = categories["Food"]
        assert (
            client.patch(
                f"/api/categories/{food}", json={"name": "Nope"}, headers=user_a["headers"]
            ).status_code
            == 400
        )
        assert (
            client.delete(f"/api/categories/{food}", headers=user_a["headers"]).status_code == 400
        )

    def test_invalid_colour_rejected(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/categories",
            json={"name": "Bad Colour", "color": "not-a-colour"},
            headers=user_a["headers"],
        )
        assert response.status_code == 422

    def test_deleting_custom_category_orphans_not_deletes_transactions(
        self, client: TestClient, user_a: dict
    ):
        custom = client.post(
            "/api/categories", json={"name": "Temporary"}, headers=user_a["headers"]
        ).json()
        tx = make_transaction(client, user_a["headers"], category_id=custom["id"])

        assert (
            client.delete(f"/api/categories/{custom['id']}", headers=user_a["headers"]).status_code
            == 200
        )

        refetched = client.get(f"/api/transactions/{tx['id']}", headers=user_a["headers"]).json()
        assert refetched["category"] is None


class TestMLFeedbackLoop:
    def test_auto_categorization_applies_a_category(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/transactions",
            json={
                "amount": "450.00",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "merchant": "Swiggy",
                "description": "Swiggy dinner order",
                "payment_method": "UPI",
                "auto_categorize": True,
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 201
        body = response.json()
        assert body["ai_categorized"] is True
        assert body["category"]["name"] == "Food"
        assert 0 < body["ai_confidence"] <= 1

    def test_explicit_category_beats_the_model(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        response = client.post(
            "/api/transactions",
            json={
                "amount": "450.00",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "merchant": "Swiggy",
                "description": "Swiggy order",
                "category_id": categories["Shopping"],
                "auto_categorize": True,
            },
            headers=user_a["headers"],
        )
        assert response.json()["category"]["name"] == "Shopping"
        assert response.json()["ai_categorized"] is False

    def test_correction_is_recorded_for_retraining(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        tx = client.post(
            "/api/transactions",
            json={
                "amount": "450.00",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "merchant": "Swiggy",
                "description": "Swiggy order",
                "auto_categorize": True,
            },
            headers=user_a["headers"],
        ).json()
        assert tx["ai_categorized"] is True

        corrected = client.put(
            f"/api/transactions/{tx['id']}",
            json={"category_id": categories["Shopping"]},
            headers=user_a["headers"],
        ).json()
        assert corrected["category"]["name"] == "Shopping"
        # A human owns this label now, so the AI badge is removed.
        assert corrected["ai_categorized"] is False

        stats = client.get("/api/ml/categorizer-status", headers=user_a["headers"]).json()
        assert stats["corrected"] >= 1
        assert stats["pending_training_examples"] >= 1

    def test_corrections_export_as_training_rows(
        self, client: TestClient, user_a: dict, categories: dict, session
    ):
        tx = client.post(
            "/api/transactions",
            json={
                "amount": "450.00",
                "type": "expense",
                "occurred_on": date.today().isoformat(),
                "merchant": "Swiggy",
                "description": "Swiggy order",
                "auto_categorize": True,
            },
            headers=user_a["headers"],
        ).json()
        client.put(
            f"/api/transactions/{tx['id']}",
            json={"category_id": categories["Shopping"]},
            headers=user_a["headers"],
        )

        from app.services.categorization_service import collect_training_corrections

        rows = collect_training_corrections(session)
        assert len(rows) >= 1
        row = rows[0]
        assert row["category"] == "Shopping"
        assert row["merchant"] == "Swiggy"
        # The export must not carry amounts or user identifiers.
        assert set(row) == {
            "description",
            "merchant",
            "payment_method",
            "transaction_type",
            "category",
        }

    def test_categorize_preview_does_not_write(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/transactions/categorize-preview",
            json={
                "description": "Uber ride to airport",
                "merchant": "Uber India",
                "type": "expense",
            },
            headers=user_a["headers"],
        )
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["category"] == "Transport"
        assert body["explanation"]  # driving tokens returned
        assert client.get("/api/transactions", headers=user_a["headers"]).json()["total"] == 0

    def test_preview_returns_alternatives(self, client: TestClient, user_a: dict):
        body = client.post(
            "/api/transactions/categorize-preview",
            json={"description": "Amazon order", "merchant": "Amazon India", "type": "expense"},
            headers=user_a["headers"],
        ).json()
        assert len(body["alternatives"]) >= 1
        # Confidences must be sorted descending and each below the winner.
        scores = [a["confidence"] for a in body["alternatives"]]
        assert scores == sorted(scores, reverse=True)
        assert all(s <= body["confidence"] for s in scores)
