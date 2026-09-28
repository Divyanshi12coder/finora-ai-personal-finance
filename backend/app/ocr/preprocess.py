"""Image preprocessing for receipt OCR.

Tesseract is markedly more accurate on a clean, high-contrast, upright binary
image than on a raw phone photo. This module applies the standard document
pipeline, in this order:

    load -> grayscale -> upscale (if small) -> denoise -> deskew
         -> adaptive threshold -> border pad

Each step is individually justified below. Every step degrades gracefully: if
OpenCV is unavailable the module falls back to a Pillow-only path, and if any
individual step fails the previous image is passed through rather than failing
the upload.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Tesseract's models are trained around ~300 DPI; small images are upscaled so
# that x-height lands in the range the engine expects.
MIN_WIDTH = 1200
MAX_WIDTH = 2400
# Beyond a few degrees, skew materially hurts line segmentation.
MAX_DESKEW_DEGREES = 15.0


def _opencv_available() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def preprocess(image_bytes: bytes) -> tuple[bytes, list[str]]:
    """Return ``(processed_png_bytes, notes)``.

    ``notes`` records which steps ran, so the receipt detail view can explain
    what was done to the image before OCR.
    """
    if _opencv_available():
        try:
            return _preprocess_opencv(image_bytes)
        except Exception:
            logger.exception("OpenCV preprocessing failed; falling back to Pillow")

    try:
        return _preprocess_pillow(image_bytes)
    except Exception:
        logger.exception("Pillow preprocessing failed; using the original image")
        return image_bytes, ["preprocessing skipped (error)"]


def _preprocess_opencv(image_bytes: bytes) -> tuple[bytes, list[str]]:
    import cv2
    import numpy as np

    notes: list[str] = []

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Image could not be decoded")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    notes.append("grayscale")

    # --- Scale ------------------------------------------------------------
    height, width = gray.shape[:2]
    if width < MIN_WIDTH:
        scale = MIN_WIDTH / width
        gray = cv2.resize(
            gray, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_CUBIC
        )
        notes.append(f"upscaled x{scale:.2f}")
    elif width > MAX_WIDTH:
        scale = MAX_WIDTH / width
        gray = cv2.resize(
            gray, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
        )
        notes.append(f"downscaled x{scale:.2f}")

    # --- Denoise ----------------------------------------------------------
    # Bilateral filtering smooths paper grain and JPEG noise while preserving
    # character edges, which a Gaussian blur would soften.
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=50, sigmaSpace=50)
    notes.append("bilateral denoise")

    # --- Deskew -----------------------------------------------------------
    angle = _estimate_skew(gray)
    if angle is not None and 0.3 < abs(angle) <= MAX_DESKEW_DEGREES:
        h, w = gray.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        gray = cv2.warpAffine(
            gray,
            matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        notes.append(f"deskewed {angle:.1f}deg")

    # --- Binarise ---------------------------------------------------------
    # Adaptive thresholding beats a global threshold on receipts, which are
    # commonly photographed with uneven lighting or a shadow across the paper.
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blockSize=31, C=15
    )
    notes.append("adaptive threshold")

    # Tesseract behaves better with a quiet border around the text block.
    binary = cv2.copyMakeBorder(binary, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    notes.append("padded")

    success, encoded = cv2.imencode(".png", binary)
    if not success:  # pragma: no cover - defensive
        raise ValueError("Failed to encode the processed image")
    return encoded.tobytes(), notes


def _estimate_skew(gray) -> float | None:
    """Estimate page skew from the minimum-area rectangle of the text mask."""
    import cv2
    import numpy as np

    try:
        inverted = cv2.bitwise_not(gray)
        _, mask = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        coordinates = np.column_stack(np.where(mask > 0))
        if len(coordinates) < 100:
            return None
        angle = cv2.minAreaRect(coordinates.astype(np.float32))[-1]
        # minAreaRect reports 0-90; map to the nearest small rotation.
        if angle > 45:
            angle -= 90
        return float(angle)
    except Exception:  # pragma: no cover - defensive
        logger.debug("Skew estimation failed", exc_info=True)
        return None


def _preprocess_pillow(image_bytes: bytes) -> tuple[bytes, list[str]]:
    """Pillow-only fallback: grayscale, upscale, autocontrast, sharpen."""
    from PIL import Image, ImageFilter, ImageOps

    notes: list[str] = ["pillow fallback"]
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("L")
        notes.append("grayscale")

        if image.width < MIN_WIDTH:
            scale = MIN_WIDTH / image.width
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
            )
            notes.append(f"upscaled x{scale:.2f}")

        image = ImageOps.autocontrast(image, cutoff=2)
        notes.append("autocontrast")

        image = image.filter(ImageFilter.SHARPEN)
        notes.append("sharpen")

        image = ImageOps.expand(image, border=20, fill=255)
        notes.append("padded")

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue(), notes
