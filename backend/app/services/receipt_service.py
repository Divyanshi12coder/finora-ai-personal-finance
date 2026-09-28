"""Receipt upload, OCR processing and conversion into a transaction.

Upload path:

    file -> validate (type, size, magic bytes) -> store under a generated name
         -> Receipt row (status=uploaded)

Processing path:

    stored file -> preprocess -> OCR -> parse -> suggest category (ML)
                -> persist fields + raw text (status=processed)

Confirmation path:

    user-corrected fields -> Transaction (source=receipt) -> status=confirmed

The user can edit every extracted field before confirming; nothing is written to
the transaction ledger until they do.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import (
    Receipt,
    ReceiptItem,
    ReceiptStatus,
    TransactionSource,
    TransactionType,
    User,
)
from app.ocr import engine as ocr_engine
from app.ocr.engine import OCREngineUnavailable, OCRProcessingError
from app.ocr.parser import parse_receipt
from app.schemas.receipt import ReceiptConfirmRequest, ReceiptUpdate
from app.schemas.transaction import TransactionCreate
from app.services import categorization_service, transaction_service

logger = logging.getLogger(__name__)

# Magic-byte signatures. Trusting the client-supplied content type alone would
# let an arbitrary file through with an image/png header.
_MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]


class ReceiptError(Exception):
    """Validation or processing failure; routers map this to a 400."""


def validate_upload(filename: str, content_type: str, content: bytes) -> str:
    """Validate an uploaded image. Returns the verified content type."""
    if not content:
        raise ReceiptError("The uploaded file is empty.")

    if len(content) > settings.max_upload_bytes:
        raise ReceiptError(
            f"File is too large ({len(content) / 1024 / 1024:.1f} MB). "
            f"The limit is {settings.MAX_UPLOAD_MB} MB."
        )

    declared = (content_type or "").lower().split(";")[0].strip()
    if declared not in settings.allowed_upload_types:
        raise ReceiptError(
            f"Unsupported file type '{declared or 'unknown'}'. "
            f"Allowed types: {', '.join(sorted(settings.allowed_upload_types))}."
        )

    # WebP has a split signature: RIFF....WEBP
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected = "image/webp"
    else:
        detected = next(
            (mime for signature, mime in _MAGIC_SIGNATURES if content.startswith(signature)),
            None,
        )

    if detected is None:
        raise ReceiptError(
            "This file does not look like a valid image. Please upload a PNG, "
            "JPEG, WebP, BMP or TIFF photo of the receipt."
        )

    # image/jpg is a common (technically wrong) alias for image/jpeg.
    normalised_declared = "image/jpeg" if declared == "image/jpg" else declared
    if detected != normalised_declared:
        logger.warning(
            "Upload content type mismatch: declared=%s detected=%s (%s)",
            declared,
            detected,
            filename,
        )
        # The real bytes win.
    return detected


def _safe_stored_name(original: str) -> str:
    """Generate a server-side filename.

    The user's filename is never used on disk - it is the simplest way to be
    certain no path traversal or overwrite is possible.
    """
    suffix = Path(original or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        suffix = ".png"
    return f"{uuid.uuid4().hex}{suffix}"


def store_upload(
    session: Session, user: User, filename: str, content_type: str, content: bytes
) -> Receipt:
    verified_type = validate_upload(filename, content_type, content)

    stored_name = _safe_stored_name(filename)
    destination = settings.upload_path / stored_name
    destination.write_bytes(content)

    receipt = Receipt(
        user_id=user.id,
        original_filename=(filename or "receipt")[:255],
        stored_filename=stored_name,
        content_type=verified_type,
        file_size=len(content),
        status=ReceiptStatus.UPLOADED,
        currency=user.currency,
    )
    session.add(receipt)
    session.flush()
    logger.info("Receipt %s uploaded by user %s (%d bytes)", receipt.id, user.id, len(content))
    return receipt


def list_receipts(session: Session, user: User, limit: int = 50) -> list[Receipt]:
    stmt = (
        select(Receipt)
        .where(Receipt.user_id == user.id)
        .options(joinedload(Receipt.items), joinedload(Receipt.suggested_category))
        .order_by(Receipt.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).unique().all())


def get_receipt(session: Session, user: User, receipt_id: str) -> Receipt | None:
    stmt = (
        select(Receipt)
        .where(Receipt.id == receipt_id, Receipt.user_id == user.id)
        .options(joinedload(Receipt.items), joinedload(Receipt.suggested_category))
    )
    return session.scalars(stmt).unique().first()


def file_path(receipt: Receipt) -> Path:
    return settings.upload_path / receipt.stored_filename


def process_receipt(session: Session, user: User, receipt: Receipt) -> Receipt:
    """Run the OCR + parsing pipeline over a stored receipt."""
    path = file_path(receipt)
    if not path.exists():
        receipt.status = ReceiptStatus.FAILED
        receipt.error_message = "The stored image file is missing on the server."
        session.flush()
        raise ReceiptError(receipt.error_message)

    receipt.status = ReceiptStatus.PROCESSING
    session.flush()

    engine = ocr_engine.get_engine()
    try:
        result = engine.extract(path.read_bytes())
    except OCREngineUnavailable as exc:
        receipt.status = ReceiptStatus.FAILED
        receipt.error_message = str(exc)
        session.flush()
        logger.warning("OCR unavailable for receipt %s: %s", receipt.id, exc)
        raise ReceiptError(str(exc)) from exc
    except OCRProcessingError as exc:
        receipt.status = ReceiptStatus.FAILED
        receipt.error_message = str(exc)
        session.flush()
        logger.warning("OCR failed for receipt %s: %s", receipt.id, exc)
        raise ReceiptError(str(exc)) from exc

    parsed = parse_receipt(result.text)

    receipt.raw_text = result.text
    receipt.ocr_engine = result.engine
    receipt.ocr_confidence = result.confidence
    receipt.processing_ms = result.duration_ms
    receipt.merchant = parsed.merchant
    receipt.receipt_date = parsed.receipt_date
    receipt.subtotal = parsed.subtotal
    receipt.tax = parsed.tax
    receipt.total = parsed.total
    receipt.field_confidence = parsed.field_confidence

    warnings = list(parsed.warnings)
    if result.is_low_quality:
        warnings.insert(
            0,
            f"The scan quality was low (mean OCR confidence {result.confidence:.0f}%). "
            "Some fields may be wrong - please check each one before saving.",
        )
    if result.preprocessing_notes:
        logger.debug("Preprocessing applied: %s", ", ".join(result.preprocessing_notes))
    receipt.warnings = warnings

    # Replace any items from a previous processing run.
    for existing in list(receipt.items):
        session.delete(existing)
    session.flush()

    for index, item in enumerate(parsed.items):
        session.add(
            ReceiptItem(
                receipt_id=receipt.id,
                line_number=index + 1,
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
            )
        )

    # --- Category suggestion via the ML model ----------------------------
    # The receipt text is the model's input, exactly as for a manual transaction.
    suggestion_text = " ".join(
        filter(None, [parsed.merchant, " ".join(i.name for i in parsed.items[:6])])
    )
    if suggestion_text.strip():
        _, category = categorization_service.predict_for_transaction(
            session,
            user,
            description=suggestion_text,
            merchant=parsed.merchant,
            payment_method=None,
            transaction_type=TransactionType.EXPENSE.value,
        )
        receipt.suggested_category_id = category.id if category else None

    receipt.status = ReceiptStatus.PROCESSED
    receipt.processed_at = datetime.now(UTC)
    receipt.error_message = None
    session.flush()
    session.refresh(receipt)

    logger.info(
        "Receipt %s processed: merchant=%r total=%s items=%d warnings=%d",
        receipt.id,
        receipt.merchant,
        receipt.total,
        len(parsed.items),
        len(warnings),
    )
    return receipt


def update_receipt(session: Session, receipt: Receipt, payload: ReceiptUpdate) -> Receipt:
    """Apply the user's corrections to the extracted fields."""
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)

    for field_name, value in data.items():
        setattr(receipt, field_name, value)

    if items is not None:
        for existing in list(receipt.items):
            session.delete(existing)
        session.flush()
        for index, item in enumerate(payload.items or []):
            session.add(
                ReceiptItem(
                    receipt_id=receipt.id,
                    line_number=index + 1,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                )
            )

    # Corrected fields are the user's, so the extraction warnings no longer apply.
    if data or items is not None:
        receipt.warnings = []

    session.flush()
    session.refresh(receipt)
    return receipt


def confirm_receipt(session: Session, user: User, receipt: Receipt, payload: ReceiptConfirmRequest):
    """Create the transaction from a (possibly corrected) receipt."""
    if receipt.transaction_id:
        raise ReceiptError("This receipt has already been saved as a transaction.")

    # Persist any last edits made on the confirmation screen.
    receipt.merchant = payload.merchant
    receipt.total = payload.total
    receipt.receipt_date = payload.occurred_on
    if payload.tax is not None:
        receipt.tax = payload.tax
    if payload.items is not None:
        for existing in list(receipt.items):
            session.delete(existing)
        session.flush()
        for index, item in enumerate(payload.items):
            session.add(
                ReceiptItem(
                    receipt_id=receipt.id,
                    line_number=index + 1,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                )
            )

    item_names = ", ".join(item.name for item in receipt.items[:6])
    description = f"Receipt: {payload.merchant}"
    if item_names:
        description += f" ({item_names})"

    transaction = transaction_service.create_transaction(
        session,
        user,
        TransactionCreate(
            amount=payload.total,
            type=TransactionType.EXPENSE,
            occurred_on=payload.occurred_on,
            merchant=payload.merchant,
            description=description,
            payment_method=payload.payment_method,
            notes=payload.notes,
            tags=["receipt"],
            category_id=payload.category_id or receipt.suggested_category_id,
            auto_categorize=True,
            receipt_id=receipt.id,
        ),
        source=TransactionSource.RECEIPT,
    )

    receipt.transaction_id = transaction.id
    receipt.status = ReceiptStatus.CONFIRMED
    session.flush()
    logger.info("Receipt %s confirmed as transaction %s", receipt.id, transaction.id)
    return transaction


def delete_receipt(session: Session, receipt: Receipt) -> None:
    path = file_path(receipt)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        # A missing or locked file must not block deleting the record.
        logger.warning("Could not delete receipt file %s", path, exc_info=True)
    session.delete(receipt)
    session.flush()


def to_response_dict(receipt: Receipt) -> dict:
    """Shape a Receipt for the API, adding the image URL."""
    return {
        "id": receipt.id,
        "original_filename": receipt.original_filename,
        "content_type": receipt.content_type,
        "file_size": receipt.file_size,
        "status": receipt.status,
        "error_message": receipt.error_message,
        "merchant": receipt.merchant,
        "receipt_date": receipt.receipt_date,
        "subtotal": receipt.subtotal,
        "tax": receipt.tax,
        "total": receipt.total,
        "currency": receipt.currency,
        "ocr_engine": receipt.ocr_engine,
        "ocr_confidence": receipt.ocr_confidence,
        "processing_ms": receipt.processing_ms,
        "field_confidence": receipt.field_confidence or {},
        "warnings": receipt.warnings or [],
        "items": sorted(receipt.items, key=lambda i: i.line_number),
        "suggested_category": receipt.suggested_category,
        "transaction_id": receipt.transaction_id,
        "raw_text": receipt.raw_text,
        "created_at": receipt.created_at,
        "processed_at": receipt.processed_at,
        "image_url": f"{settings.API_PREFIX}/receipts/{receipt.id}/image",
    }
