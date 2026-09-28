"""Receipt upload and OCR endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import bad_request, get_current_user, not_found
from app.models import User
from app.ocr import engine as ocr_engine
from app.schemas.common import Message
from app.schemas.receipt import (
    OCRStatusResponse,
    ReceiptConfirmRequest,
    ReceiptOut,
    ReceiptUpdate,
)
from app.schemas.transaction import TransactionOut
from app.services import receipt_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/receipts", tags=["Receipts & OCR"])


@router.get(
    "/ocr-status",
    response_model=OCRStatusResponse,
    summary="OCR engine availability",
    description=(
        "Reports whether a working OCR engine is installed, with an actionable "
        "install hint when it is not. The client uses this to disable the scanner "
        "with a useful message rather than failing on upload."
    ),
)
def ocr_status() -> OCRStatusResponse:
    return OCRStatusResponse.model_validate(ocr_engine.status())


@router.get("", response_model=list[ReceiptOut], summary="List uploaded receipts")
def list_receipts(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[ReceiptOut]:
    return [
        ReceiptOut.model_validate(receipt_service.to_response_dict(r))
        for r in receipt_service.list_receipts(session, user, limit)
    ]


@router.post(
    "/upload",
    response_model=ReceiptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a receipt image",
    description=(
        "Validates the file by declared type, size limit and magic bytes (the "
        "actual bytes win over the client's content type), stores it under a "
        "server-generated filename, and creates a Receipt row with status "
        "'uploaded'. Call /receipts/{id}/process to run OCR."
    ),
)
async def upload_receipt(
    file: UploadFile = File(..., description="Receipt photo (PNG, JPEG, WebP, BMP, TIFF)"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ReceiptOut:
    content = await file.read()
    try:
        receipt = receipt_service.store_upload(
            session, user, file.filename or "receipt", file.content_type or "", content
        )
        session.commit()
    except receipt_service.ReceiptError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(receipt)
    return ReceiptOut.model_validate(receipt_service.to_response_dict(receipt))


@router.post(
    "/{receipt_id}/process",
    response_model=ReceiptOut,
    summary="Run OCR and parse the receipt",
    description=(
        "Preprocesses the image (grayscale, upscale, denoise, deskew, adaptive "
        "threshold), runs Tesseract, then parses merchant, date, subtotal, tax, "
        "total and line items. Per-field confidence scores and warnings are "
        "returned so the user knows which values to verify. Raw OCR text is kept "
        "for debugging. Fails with a clear message if no OCR engine is installed - "
        "it never fabricates a result."
    ),
)
def process_receipt(
    receipt_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ReceiptOut:
    receipt = receipt_service.get_receipt(session, user, receipt_id)
    if receipt is None:
        raise not_found("Receipt")

    try:
        processed = receipt_service.process_receipt(session, user, receipt)
        session.commit()
    except receipt_service.ReceiptError as exc:
        # The failure reason is persisted on the row before we raise.
        session.commit()
        raise bad_request(str(exc)) from exc

    session.refresh(processed)
    return ReceiptOut.model_validate(receipt_service.to_response_dict(processed))


@router.get("/{receipt_id}", response_model=ReceiptOut, summary="Get one receipt")
def get_receipt(
    receipt_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ReceiptOut:
    receipt = receipt_service.get_receipt(session, user, receipt_id)
    if receipt is None:
        raise not_found("Receipt")
    return ReceiptOut.model_validate(receipt_service.to_response_dict(receipt))


@router.get(
    "/{receipt_id}/image",
    summary="Download the receipt image",
    description=(
        "Serves the stored image. Authorised per user: the path is resolved from "
        "the database row, never from client input, so one user cannot read "
        "another's upload."
    ),
    response_class=FileResponse,
)
def receipt_image(
    receipt_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> FileResponse:
    receipt = receipt_service.get_receipt(session, user, receipt_id)
    if receipt is None:
        raise not_found("Receipt")

    path = receipt_service.file_path(receipt)
    if not path.exists():
        raise not_found("Receipt image")

    return FileResponse(path, media_type=receipt.content_type, filename=receipt.original_filename)


@router.patch(
    "/{receipt_id}",
    response_model=ReceiptOut,
    summary="Correct extracted fields",
    description=(
        "Applies the user's corrections to the OCR output before it becomes a "
        "transaction. Every extracted field is editable."
    ),
)
def update_receipt(
    receipt_id: str,
    payload: ReceiptUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ReceiptOut:
    receipt = receipt_service.get_receipt(session, user, receipt_id)
    if receipt is None:
        raise not_found("Receipt")

    updated = receipt_service.update_receipt(session, receipt, payload)
    session.commit()
    session.refresh(updated)
    return ReceiptOut.model_validate(receipt_service.to_response_dict(updated))


@router.post(
    "/{receipt_id}/confirm",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Save the receipt as a transaction",
    description=(
        "Creates a real transaction from the verified receipt fields. The "
        "transaction goes through exactly the same service path as a manual entry, "
        "including ML categorisation and anomaly scoring."
    ),
)
def confirm_receipt(
    receipt_id: str,
    payload: ReceiptConfirmRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TransactionOut:
    receipt = receipt_service.get_receipt(session, user, receipt_id)
    if receipt is None:
        raise not_found("Receipt")

    try:
        transaction = receipt_service.confirm_receipt(session, user, receipt, payload)
        session.commit()
    except receipt_service.ReceiptError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(transaction)
    return TransactionOut.model_validate(transaction)


@router.delete("/{receipt_id}", response_model=Message, summary="Delete a receipt")
def delete_receipt(
    receipt_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    receipt = receipt_service.get_receipt(session, user, receipt_id)
    if receipt is None:
        raise not_found("Receipt")

    receipt_service.delete_receipt(session, receipt)
    session.commit()
    return Message(detail="Receipt deleted")
