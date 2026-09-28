"""The ML package: preprocessing, dataset, pipeline, training and inference."""

from __future__ import annotations

import csv

import pytest

from ml import preprocessing
from ml.dataset import load_dataset
from ml.model_store import get_categorizer
from ml.paths import SEED_DATASET
from ml.pipeline import build_pipeline


class TestPreprocessing:
    def test_normalises_case_and_punctuation(self):
        assert preprocessing.normalize_text("UPI/SWIGGY/428391/Food order") == (
            "upi swiggy food order"
        )

    def test_masks_card_numbers(self):
        result = preprocessing.normalize_text("POS 4521XXXX7823 STARBUCKS MUMBAI")
        assert "4521" not in result
        assert "starbucks" in result
        assert "mumbai" in result

    def test_strips_amounts(self):
        result = preprocessing.normalize_text("Swiggy order Rs.450.50")
        assert "450" not in result
        assert "swiggy" in result

    def test_strips_dates(self):
        result = preprocessing.normalize_text("Paid on 28/09/2026 to Zomato")
        assert "2026" not in result
        assert "zomato" in result

    def test_strips_long_reference_numbers(self):
        result = preprocessing.normalize_text("IMPS/998877665544/Uber")
        assert "998877665544" not in result
        assert "uber" in result

    def test_removes_accents(self):
        assert preprocessing.normalize_text("Café Coffee Day") == "cafe coffee day"

    @pytest.mark.parametrize("value", [None, "", "   ", "12345", "###"])
    def test_empty_and_noise_inputs(self, value):
        assert preprocessing.normalize_text(value) == ""

    def test_merchant_is_weighted_twice(self):
        document = preprocessing.build_document(
            description="dinner", merchant="Swiggy", transaction_type="expense"
        )
        assert document.split().count("swiggy") == 2

    def test_document_includes_typed_features(self):
        document = preprocessing.build_document(
            description="order",
            merchant="Zomato",
            payment_method="Credit Card",
            transaction_type="expense",
        )
        assert "pay_credit_card" in document
        assert "type_expense" in document

    def test_document_empty_when_nothing_usable(self):
        assert preprocessing.build_document(description="", merchant="") == ""

    def test_train_serve_consistency(self):
        """The same inputs must always produce the same document."""
        args = {
            "description": "UPI/UBER/123456/ride",
            "merchant": "Uber India",
            "payment_method": "UPI",
            "transaction_type": "expense",
        }
        assert preprocessing.build_document(**args) == preprocessing.build_document(**args)


class TestDataset:
    def test_seed_dataset_exists_and_is_wellformed(self):
        assert SEED_DATASET.exists(), "Run `python -m ml.build_dataset`"
        with SEED_DATASET.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        assert len(rows) > 500
        required = {"description", "merchant", "payment_method", "transaction_type", "category"}
        assert required <= set(rows[0])
        assert all(row["category"] for row in rows)

    def test_dataset_loads_into_documents_and_labels(self):
        dataset = load_dataset(include_corrections=False)
        assert len(dataset.documents) == len(dataset.labels)
        assert len(dataset) > 500
        assert all(document for document in dataset.documents)

    def test_dataset_covers_every_system_category(self):
        from app.services.category_service import DEFAULT_CATEGORY_NAMES

        dataset = load_dataset(include_corrections=False)
        labels = set(dataset.labels)
        assert set(DEFAULT_CATEGORY_NAMES) == labels

    def test_dataset_contains_ambiguous_merchants(self):
        """Ambiguity is deliberate: it stops the model being a lookup table."""
        with SEED_DATASET.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        amazon_categories = {row["category"] for row in rows if row["merchant"] == "Amazon India"}
        assert len(amazon_categories) > 1

    def test_dataset_is_reproducible(self):
        """Re-running the generator must produce identical rows."""
        from ml.build_dataset import build_rows

        first = build_rows()
        second = build_rows()
        assert first == second

    def test_missing_seed_file_raises_clear_error(self, tmp_path):
        from pathlib import Path

        with pytest.raises(FileNotFoundError, match="ml.build_dataset"):
            load_dataset(seed_path=Path(tmp_path / "nope.csv"))


class TestTraining:
    """Training is exercised on a small slice so the suite stays fast."""

    def test_pipeline_trains_and_predicts(self):
        from sklearn.model_selection import train_test_split

        dataset = load_dataset(include_corrections=False)
        X_train, X_test, y_train, y_test = train_test_split(
            dataset.documents,
            dataset.labels,
            test_size=0.25,
            random_state=0,
            stratify=dataset.labels,
        )

        pipeline = build_pipeline(random_state=0)
        pipeline.fit(X_train, y_train)

        accuracy = pipeline.score(X_test, y_test)
        # A genuinely useful classifier, but not a suspiciously perfect one: the
        # dataset deliberately contains irreducible ambiguity.
        assert 0.80 < accuracy < 1.0, f"accuracy was {accuracy}"

    def test_pipeline_exposes_probabilities(self):
        dataset = load_dataset(include_corrections=False)
        pipeline = build_pipeline(random_state=0)
        pipeline.fit(dataset.documents, dataset.labels)

        probabilities = pipeline.predict_proba(
            [preprocessing.build_document(description="Swiggy order", merchant="Swiggy")]
        )[0]
        assert abs(sum(probabilities) - 1.0) < 1e-6
        assert all(0 <= p <= 1 for p in probabilities)

    def test_corrections_are_weighted_into_the_dataset(self, tmp_path):
        corrections = tmp_path / "corrections.csv"
        with corrections.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "description",
                    "merchant",
                    "payment_method",
                    "transaction_type",
                    "category",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "description": "Weekly vegetable haul",
                    "merchant": "Local Sabzi Mandi",
                    "payment_method": "Cash",
                    "transaction_type": "expense",
                    "category": "Food",
                }
            )

        from ml.dataset import CORRECTION_WEIGHT

        baseline = load_dataset(include_corrections=False)
        combined = load_dataset(corrections_path=corrections, include_corrections=True)

        assert combined.correction_count == CORRECTION_WEIGHT
        assert len(combined) == len(baseline) + CORRECTION_WEIGHT

    def test_malformed_corrections_file_raises(self, tmp_path):
        broken = tmp_path / "corrections.csv"
        broken.write_text("wrong,headers\n1,2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required columns"):
            load_dataset(corrections_path=broken)


class TestPersistedModel:
    """These require `python -m ml.train` to have been run."""

    def test_model_artefact_loads(self):
        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained; run `python -m ml.train`")
        assert model.pipeline is not None
        assert model.pipeline_version
        assert len(model.labels) == 12

    @pytest.mark.parametrize(
        "description,merchant,expected",
        [
            ("Swiggy order dinner", "Swiggy", "Food"),
            ("Uber trip to office", "Uber India", "Transport"),
            ("Netflix monthly subscription", "Netflix", "Entertainment"),
            ("NEFT CR INFOSYS LTD SALARY", "Infosys Ltd", "Salary"),
            ("Monthly house rent transfer", "House Rent Payment", "Rent"),
            ("Electricity bill payment", "BESCOM Electricity", "Bills"),
            ("SIP installment index fund", "HDFC Mutual Fund", "Investments"),
            ("Prescription medicines", "Apollo Pharmacy", "Healthcare"),
            ("Flight booking to Goa", "MakeMyTrip", "Travel"),
            ("Course fee python certification", "Udemy", "Education"),
        ],
    )
    def test_predicts_expected_categories(self, description, merchant, expected):
        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained")

        prediction = model.predict(
            description=description, merchant=merchant, transaction_type="expense"
        )
        assert prediction is not None
        assert (
            prediction.category == expected
        ), f"{merchant!r} -> got {prediction.category} @ {prediction.confidence:.2f}"
        assert 0 < prediction.confidence <= 1

    def test_same_merchant_different_category_from_description(self):
        """The proof that this is a classifier and not a merchant lookup table."""
        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained")

        streaming = model.predict(
            description="prime video subscription renewal",
            merchant="Amazon India",
            transaction_type="expense",
        )
        goods = model.predict(
            description="order for home goods and appliance",
            merchant="Amazon India",
            transaction_type="expense",
        )
        assert streaming.category == "Entertainment"
        assert goods.category == "Shopping"

    @pytest.mark.parametrize(
        "narration,expected",
        [
            # Vowel-dropped and compacted truncations, the styles real card
            # networks emit and that the seed generator reproduces. The
            # character n-gram branch of the pipeline is what handles these.
            ("SWGGY", "Food"),
            ("STARBUCKSCOFF", "Food"),
            ("NETFLX", "Entertainment"),
            ("POS 4521XXXX8890 SWIGGY MUMBAI", "Food"),
            ("ZOMATO BENGALURU", "Food"),
        ],
    )
    def test_handles_truncated_merchant_names(self, narration, expected):
        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained")

        prediction = model.predict(description=narration, transaction_type="expense")
        assert prediction is not None
        assert (
            prediction.category == expected
        ), f"{narration!r} -> {prediction.category} @ {prediction.confidence:.2f}"

    def test_out_of_distribution_text_yields_low_confidence(self):
        """Unrecognisable text must not be confidently mislabelled.

        The model will always return *some* class, so the safeguard is the
        confidence policy: an unfamiliar narration scores below the auto-apply
        threshold and is therefore left for the user to categorise rather than
        being applied silently.
        """
        from app.ml.categorizer import AUTO_APPLY_THRESHOLD

        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained")

        prediction = model.predict(description="qwx zzptl vnmq 88", transaction_type="expense")
        assert prediction is not None
        assert prediction.confidence < AUTO_APPLY_THRESHOLD

    def test_returns_none_for_empty_input(self):
        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained")
        assert model.predict(description="", merchant="") is None

    def test_explanation_returns_driving_tokens(self):
        model = get_categorizer(refresh=True)
        if not model.is_available:
            pytest.skip("Model not trained")

        document = preprocessing.build_document(
            description="netflix monthly subscription", merchant="Netflix"
        )
        explanation = model.explain(document)
        assert explanation
        tokens = [token for token, _ in explanation]
        assert any("netflix" in token for token in tokens)
        # Contributions must be positive and ordered.
        values = [value for _, value in explanation]
        assert values == sorted(values, reverse=True)
        assert all(value > 0 for value in values)


class TestCategorizerWrapper:
    def test_confidence_policy(self):
        from app.ml.categorizer import AUTO_APPLY_THRESHOLD, CategorizationResult

        low = CategorizationResult(
            available=True, category="Food", confidence=AUTO_APPLY_THRESHOLD - 0.01
        )
        high = CategorizationResult(
            available=True, category="Food", confidence=AUTO_APPLY_THRESHOLD + 0.01
        )
        assert low.should_auto_apply is False
        assert high.should_auto_apply is True

    def test_unavailable_model_reports_actionable_message(self, monkeypatch):
        from pathlib import Path

        from app.ml import categorizer
        from ml.model_store import CategorizerModel

        monkeypatch.setattr(
            categorizer,
            "get_model",
            lambda: CategorizerModel(None, [], None, None, Path("missing"), error="gone"),
        )
        result = categorizer.categorize(description="anything", merchant="Anything")
        assert result.available is False
        assert "ml.train" in result.message

    def test_status_reports_thresholds(self):
        from app.ml.categorizer import status

        info = status()
        assert "auto_apply_threshold" in info
        assert "high_confidence_threshold" in info
        assert "available" in info
