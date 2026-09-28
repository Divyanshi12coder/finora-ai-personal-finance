"""Receipt OCR: parser, upload validation and the processing endpoint.

The parser is tested exhaustively against realistic receipt layouts, because it
is pure text-in/fields-out logic and therefore fully testable without Tesseract.
Tests that need the OCR binary skip cleanly when it is not installed.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.ocr.parser import parse_receipt

STARBUCKS = """
STARBUCKS COFFEE INDIA
Forum Mall, Koramangala
Bengaluru 560095
GSTIN: 29AABCS1429B1ZW
Tel: 080-41234567
--------------------------------
Tax Invoice
Bill No: 4417822
Date: 28/09/2026   Time: 14:32
--------------------------------
Cappuccino Grande    1     250.00
Chicken Sandwich     1     320.00
Blueberry Muffin     1     180.00
--------------------------------
Sub Total                  750.00
CGST 2.5%                   18.75
SGST 2.5%                   18.75
Round Off                    0.50
GRAND TOTAL                788.00
--------------------------------
Paid by UPI
Thank you, visit again!
"""

DMART = """
DMART
Avenue Supermarts Ltd
Whitefield, Bengaluru
GST NO 29AACCA1234M1ZP
Invoice No: 88213/2026
Date 15-09-2026
Toor Dal 1kg            2   320.00
Amul Butter 500g        1   285.00
Basmati Rice 5kg        1   649.00
Colgate Toothpaste      3   180.00
Sunflower Oil 1L        2   398.00
SUBTOTAL                   1832.00
GST                         91.60
TOTAL                     1923.60
CASH                      2000.00
CHANGE                      76.40
"""

MINIMAL = """
LOCAL KIRANA STORE
Total 450
"""

NO_TOTAL_KEYWORD = """
CORNER CHAAT SHOP
Samosa            40.00
Pav Bhaji        120.00
Lassi             60.00
220.00
"""

GARBAGE = """
||| ~~~~ ??? ###
-----
"""


class TestReceiptParser:
    def test_extracts_all_fields(self):
        parsed = parse_receipt(STARBUCKS)
        assert parsed.merchant == "STARBUCKS COFFEE INDIA"
        assert parsed.receipt_date == date(2026, 9, 28)
        assert parsed.subtotal == Decimal("750.00")
        assert parsed.total == Decimal("788.00")
        assert parsed.warnings == []

    def test_sums_split_gst_components(self):
        """Indian receipts print CGST and SGST separately; both must be counted."""
        parsed = parse_receipt(STARBUCKS)
        assert parsed.tax == Decimal("37.50")

    def test_extracts_line_items(self):
        parsed = parse_receipt(STARBUCKS)
        names = [item.name for item in parsed.items]
        assert "Cappuccino Grande" in names
        assert "Chicken Sandwich" in names
        assert "Blueberry Muffin" in names

        cappuccino = next(i for i in parsed.items if i.name == "Cappuccino Grande")
        assert cappuccino.total_price == Decimal("250.00")
        assert cappuccino.quantity == Decimal("1")

    def test_excludes_total_and_tax_rows_from_items(self):
        parsed = parse_receipt(STARBUCKS)
        names = " ".join(item.name.lower() for item in parsed.items)
        for banned in ("total", "cgst", "sgst", "round off", "gstin", "bill no"):
            assert banned not in names

    def test_handles_quantities_above_one(self):
        parsed = parse_receipt(DMART)
        dal = next((i for i in parsed.items if "Toor Dal" in i.name), None)
        assert dal is not None
        assert dal.quantity == Decimal("2")
        assert dal.total_price == Decimal("320.00")
        # Unit price is derived, not guessed.
        assert dal.unit_price == Decimal("160.00")

    def test_excludes_cash_and_change_rows(self):
        parsed = parse_receipt(DMART)
        names = " ".join(item.name.lower() for item in parsed.items)
        assert "cash" not in names
        assert "change" not in names
        assert parsed.total == Decimal("1923.60")

    def test_alternate_date_format(self):
        parsed = parse_receipt(DMART)
        assert parsed.receipt_date == date(2026, 9, 15)

    def test_minimal_receipt(self):
        parsed = parse_receipt(MINIMAL)
        assert parsed.merchant == "LOCAL KIRANA STORE"
        assert parsed.total == Decimal("450")

    def test_missing_total_keyword_falls_back_and_warns(self):
        parsed = parse_receipt(NO_TOTAL_KEYWORD)
        assert parsed.total == Decimal("220.00")
        assert parsed.field_confidence["total"] < 0.5
        assert any("largest amount" in w for w in parsed.warnings)

    def test_missing_date_defaults_to_today_and_warns(self):
        parsed = parse_receipt(MINIMAL)
        assert parsed.receipt_date == date.today()
        assert any("no date" in w.lower() for w in parsed.warnings)

    def test_unreadable_text_produces_warnings_not_crash(self):
        parsed = parse_receipt(GARBAGE)
        assert parsed.total is None or parsed.total == Decimal("0")
        assert parsed.warnings
        assert parsed.needs_review is True

    @pytest.mark.parametrize("text", ["", "   ", "\n\n\n"])
    def test_empty_input(self, text: str):
        parsed = parse_receipt(text)
        assert parsed.merchant is None
        assert parsed.total is None
        assert parsed.warnings

    def test_merchant_skips_address_and_gstin_lines(self):
        text = """
        12/34 MG Road
        GSTIN: 29AABCS1429B1ZW
        REAL MERCHANT NAME
        Total 100
        """
        parsed = parse_receipt(text)
        assert parsed.merchant == "REAL MERCHANT NAME"

    def test_future_date_is_rejected(self):
        text = """
        SOME SHOP
        Date: 01/01/2099
        Total 500
        """
        parsed = parse_receipt(text)
        # An implausible future date is not trusted; it falls back to today.
        assert parsed.receipt_date == date.today()

    def test_tax_exceeding_total_is_flagged(self):
        text = """
        BROKEN SCAN SHOP
        Total 100.00
        GST 500.00
        """
        parsed = parse_receipt(text)
        assert any("larger than the total" in w for w in parsed.warnings)

    def test_items_not_summing_to_total_is_flagged(self):
        text = """
        MISMATCH STORE
        Widget A         100.00
        Widget B         100.00
        TOTAL           5000.00
        """
        parsed = parse_receipt(text)
        assert any("add up to" in w for w in parsed.warnings)

    def test_field_confidence_is_reported_per_field(self):
        parsed = parse_receipt(STARBUCKS)
        for field in ("merchant", "total", "tax", "subtotal", "receipt_date", "items"):
            assert field in parsed.field_confidence
            assert 0.0 <= parsed.field_confidence[field] <= 1.0

    def test_currency_symbols_are_tolerated(self):
        text = """
        SYMBOL CAFE
        Latte            Rs.250.00
        GRAND TOTAL      Rs.250.00
        """
        parsed = parse_receipt(text)
        assert parsed.total == Decimal("250.00")

    def test_thousands_separators_parsed(self):
        text = """
        BIG STORE
        TOTAL AMOUNT    1,23,456.78
        """
        parsed = parse_receipt(text)
        assert parsed.total == Decimal("123456.78")

    def test_absurd_amounts_rejected(self):
        text = """
        GLITCH STORE
        TOTAL 99999999999999
        """
        parsed = parse_receipt(text)
        assert parsed.total is None or parsed.total < Decimal("10000000")


class TestUploadValidation:
    """File validation must not trust the client's content type."""

    PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 200

    def test_accepts_valid_png(self):
        from app.services.receipt_service import validate_upload

        assert validate_upload("r.png", "image/png", self.PNG_HEADER) == "image/png"

    def test_accepts_valid_jpeg(self):
        from app.services.receipt_service import validate_upload

        assert validate_upload("r.jpg", "image/jpeg", self.JPEG_HEADER) == "image/jpeg"

    def test_rejects_disguised_executable(self):
        """A .exe renamed to .png with an image content type must be refused."""
        from app.services.receipt_service import ReceiptError, validate_upload

        with pytest.raises(ReceiptError, match="does not look like a valid image"):
            validate_upload("evil.png", "image/png", b"MZ\x90\x00" + b"\x00" * 200)

    def test_rejects_pdf_masquerading_as_image(self):
        from app.services.receipt_service import ReceiptError, validate_upload

        with pytest.raises(ReceiptError):
            validate_upload("doc.png", "image/png", b"%PDF-1.7" + b"\x00" * 200)

    def test_rejects_disallowed_content_type(self):
        from app.services.receipt_service import ReceiptError, validate_upload

        with pytest.raises(ReceiptError, match="Unsupported file type"):
            validate_upload("s.svg", "image/svg+xml", b"<svg></svg>")

    def test_rejects_empty_file(self):
        from app.services.receipt_service import ReceiptError, validate_upload

        with pytest.raises(ReceiptError, match="empty"):
            validate_upload("r.png", "image/png", b"")

    def test_rejects_oversized_file(self):
        from app.config import settings
        from app.services.receipt_service import ReceiptError, validate_upload

        oversized = self.PNG_HEADER + b"\x00" * (settings.max_upload_bytes + 1)
        with pytest.raises(ReceiptError, match="too large"):
            validate_upload("big.png", "image/png", oversized)

    def test_stored_filename_never_uses_user_input(self):
        """No path traversal, no collisions, no attacker-chosen extension."""
        from app.services.receipt_service import _safe_stored_name

        for hostile in [
            "../../../../etc/passwd",
            "..\\..\\windows\\system32\\cmd.exe",
            "receipt.png\x00.exe",
            "a" * 500 + ".png",
        ]:
            stored = _safe_stored_name(hostile)
            assert ".." not in stored
            assert "/" not in stored and "\\" not in stored
            assert "\x00" not in stored
            assert stored.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"))

        # Two uploads of the same name must not collide.
        assert _safe_stored_name("r.png") != _safe_stored_name("r.png")


class TestReceiptEndpoints:
    PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def test_ocr_status_is_always_answerable(self, client: TestClient, user_a: dict):
        response = client.get("/api/receipts/ocr-status", headers=user_a["headers"])
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["available"], bool)
        assert body["message"]
        if not body["available"]:
            # An unavailable engine must say how to fix it.
            assert body["install_hint"]
            assert "tesseract" in body["install_hint"].lower()

    def test_upload_creates_a_receipt_row(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/receipts/upload",
            files={"file": ("receipt.png", io.BytesIO(self.PNG), "image/png")},
            headers=user_a["headers"],
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "uploaded"
        assert body["original_filename"] == "receipt.png"
        assert body["image_url"].endswith("/image")

    def test_upload_rejects_non_image(self, client: TestClient, user_a: dict):
        response = client.post(
            "/api/receipts/upload",
            files={"file": ("evil.png", io.BytesIO(b"MZ\x90\x00" * 50), "image/png")},
            headers=user_a["headers"],
        )
        assert response.status_code == 400

    def test_upload_requires_authentication(self, client: TestClient):
        response = client.post(
            "/api/receipts/upload",
            files={"file": ("r.png", io.BytesIO(self.PNG), "image/png")},
        )
        assert response.status_code == 401

    def test_receipts_are_user_scoped(self, client: TestClient, user_a: dict, user_b: dict):
        receipt = client.post(
            "/api/receipts/upload",
            files={"file": ("a.png", io.BytesIO(self.PNG), "image/png")},
            headers=user_a["headers"],
        ).json()

        assert (
            client.get(f"/api/receipts/{receipt['id']}", headers=user_b["headers"]).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/receipts/{receipt['id']}/image", headers=user_b["headers"]
            ).status_code
            == 404
        )
        assert (
            client.delete(f"/api/receipts/{receipt['id']}", headers=user_b["headers"]).status_code
            == 404
        )
        assert client.get("/api/receipts", headers=user_b["headers"]).json() == []

    def test_processing_without_ocr_engine_fails_clearly(self, client: TestClient, user_a: dict):
        """No OCR engine must produce an explanatory 400, never a fake result."""
        from app.ocr import engine as ocr_engine

        receipt = client.post(
            "/api/receipts/upload",
            files={"file": ("r.png", io.BytesIO(self.PNG), "image/png")},
            headers=user_a["headers"],
        ).json()

        response = client.post(f"/api/receipts/{receipt['id']}/process", headers=user_a["headers"])

        if ocr_engine.get_engine().is_available():
            # A 1x1 transparent PNG has no text, so a real engine reports that.
            assert response.status_code == 400
            assert "text" in response.json()["detail"].lower()
        else:
            assert response.status_code == 400
            assert "ocr" in response.json()["detail"].lower()

        # Either way the failure is recorded, and no fields were invented.
        stored = client.get(f"/api/receipts/{receipt['id']}", headers=user_a["headers"]).json()
        assert stored["status"] == "failed"
        assert stored["error_message"]
        assert stored["total"] is None
        assert stored["merchant"] is None

    def test_manual_correction_and_confirmation_creates_a_transaction(
        self, client: TestClient, user_a: dict, categories: dict
    ):
        """The user can always correct fields and save, even if OCR failed."""
        receipt = client.post(
            "/api/receipts/upload",
            files={"file": ("r.png", io.BytesIO(self.PNG), "image/png")},
            headers=user_a["headers"],
        ).json()

        corrected = client.patch(
            f"/api/receipts/{receipt['id']}",
            json={
                "merchant": "Starbucks Coffee",
                "receipt_date": "2026-09-28",
                "total": "570.00",
                "tax": "27.14",
                "items": [
                    {"name": "Coffee", "quantity": "1", "total_price": "250.00"},
                    {"name": "Sandwich", "quantity": "1", "total_price": "320.00"},
                ],
            },
            headers=user_a["headers"],
        )
        assert corrected.status_code == 200
        assert corrected.json()["merchant"] == "Starbucks Coffee"
        assert len(corrected.json()["items"]) == 2

        confirmed = client.post(
            f"/api/receipts/{receipt['id']}/confirm",
            json={
                "merchant": "Starbucks Coffee",
                "total": "570.00",
                "occurred_on": "2026-09-28",
                "category_id": categories["Food"],
                "payment_method": "UPI",
            },
            headers=user_a["headers"],
        )
        assert confirmed.status_code == 201
        transaction = confirmed.json()
        assert float(transaction["amount"]) == 570.0
        assert transaction["category"]["name"] == "Food"
        assert transaction["source"] == "receipt"
        assert "Coffee" in transaction["description"]

        # It is a real transaction in the ledger.
        listed = client.get("/api/transactions", headers=user_a["headers"]).json()
        assert listed["total"] == 1

        # And the receipt is linked, so it cannot be saved twice.
        again = client.post(
            f"/api/receipts/{receipt['id']}/confirm",
            json={"merchant": "X", "total": "1.00", "occurred_on": "2026-09-28"},
            headers=user_a["headers"],
        )
        assert again.status_code == 400

    def test_delete_removes_receipt(self, client: TestClient, user_a: dict):
        receipt = client.post(
            "/api/receipts/upload",
            files={"file": ("r.png", io.BytesIO(self.PNG), "image/png")},
            headers=user_a["headers"],
        ).json()
        assert (
            client.delete(f"/api/receipts/{receipt['id']}", headers=user_a["headers"]).status_code
            == 200
        )
        assert (
            client.get(f"/api/receipts/{receipt['id']}", headers=user_a["headers"]).status_code
            == 404
        )


class TestImagePreprocessing:
    def test_preprocessing_returns_bytes_and_notes(self):
        """Preprocessing must degrade gracefully, never raise."""
        from app.ocr.preprocess import preprocess

        png = TestReceiptEndpoints.PNG
        processed, notes = preprocess(png)
        assert isinstance(processed, bytes)
        assert len(processed) > 0
        assert isinstance(notes, list)

    def test_preprocessing_survives_corrupt_input(self):
        from app.ocr.preprocess import preprocess

        processed, notes = preprocess(b"not an image at all")
        # Falls back to returning the original rather than crashing the upload.
        assert isinstance(processed, bytes)
        assert isinstance(notes, list)
