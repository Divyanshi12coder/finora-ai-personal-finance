"""OCR engine abstraction.

The concrete engine is behind a small interface so a cloud OCR API (Google
Vision, AWS Textract, Azure Document Intelligence) can be dropped in by adding
one class and changing one factory line - no caller changes.

Honesty rule: when no engine is installed, `extract` raises
``OCREngineUnavailable``. It never returns invented text. A receipt that cannot
be read is reported as such.
"""

from __future__ import annotations

import logging
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)


class OCREngineUnavailable(RuntimeError):
    """No usable OCR engine is installed or configured."""


class OCRProcessingError(RuntimeError):
    """The engine is available but failed on this particular image."""


@dataclass
class OCRResult:
    text: str
    confidence: float | None
    engine: str
    duration_ms: int
    # Per-word confidences are kept so the parser can weight the fields it
    # extracts, and so the UI can warn about a low-quality scan.
    word_confidences: list[float] = field(default_factory=list)
    preprocessing_notes: list[str] = field(default_factory=list)

    @property
    def is_low_quality(self) -> bool:
        return self.confidence is not None and self.confidence < 60.0


class OCREngine(ABC):
    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def version(self) -> str | None: ...

    @abstractmethod
    def extract(self, image_bytes: bytes) -> OCRResult: ...

    def languages(self) -> list[str]:
        return [lang.strip() for lang in settings.OCR_LANGUAGES.split("+") if lang.strip()]


class TesseractEngine(OCREngine):
    """pytesseract-backed engine (the default)."""

    name = "tesseract"

    def __init__(self) -> None:
        self._configured = False

    def _configure(self) -> None:
        if self._configured:
            return
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise OCREngineUnavailable("pytesseract is not installed") from exc

        # An explicit path wins; otherwise rely on PATH discovery.
        if settings.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        self._configured = True

    def is_available(self) -> bool:
        try:
            self._configure()
            import pytesseract

            command = pytesseract.pytesseract.tesseract_cmd
            if command and command != "tesseract":
                from pathlib import Path

                if not Path(command).exists():
                    return False
            elif shutil.which("tesseract") is None:
                return False

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def version(self) -> str | None:
        try:
            self._configure()
            import pytesseract

            return str(pytesseract.get_tesseract_version())
        except Exception:
            return None

    def extract(self, image_bytes: bytes) -> OCRResult:
        if not self.is_available():
            raise OCREngineUnavailable(
                "The Tesseract OCR binary was not found. Install Tesseract and "
                "either add it to PATH or set TESSERACT_CMD in your environment. "
                "Receipt scanning is unavailable until then; every other Finora "
                "feature works normally."
            )

        import io

        import pytesseract
        from PIL import Image

        from app.ocr.preprocess import preprocess

        started = time.perf_counter()
        processed, notes = preprocess(image_bytes)

        try:
            with Image.open(io.BytesIO(processed)) as image:
                # PSM 6 = "assume a single uniform block of text", which matches
                # a receipt far better than the default page-segmentation mode.
                config = "--oem 3 --psm 6"
                language = settings.OCR_LANGUAGES or "eng"

                text = pytesseract.image_to_string(image, lang=language, config=config)
                data = pytesseract.image_to_data(
                    image,
                    lang=language,
                    config=config,
                    output_type=pytesseract.Output.DICT,
                )
        except pytesseract.TesseractError as exc:
            raise OCRProcessingError(f"Tesseract failed to process the image: {exc}") from exc
        except Exception as exc:
            raise OCRProcessingError(f"OCR failed: {exc}") from exc

        confidences = [
            float(c)
            for c in data.get("conf", [])
            if str(c).strip() not in {"", "-1"} and float(c) >= 0
        ]
        mean_confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
        duration_ms = int((time.perf_counter() - started) * 1000)

        if not text.strip():
            raise OCRProcessingError(
                "No text could be read from this image. Try a sharper, better-lit "
                "photo with the whole receipt in frame."
            )

        logger.info(
            "OCR completed in %dms, mean confidence %s, %d chars",
            duration_ms,
            mean_confidence,
            len(text),
        )
        return OCRResult(
            text=text,
            confidence=mean_confidence,
            engine=self.name,
            duration_ms=duration_ms,
            word_confidences=confidences,
            preprocessing_notes=notes,
        )


class NullEngine(OCREngine):
    """Placeholder used when nothing is installed.

    It exists so `/receipts/ocr-status` can report an accurate, actionable
    message instead of the API 500-ing - and it never fabricates a result.
    """

    name = "unavailable"

    def is_available(self) -> bool:
        return False

    def version(self) -> str | None:
        return None

    def extract(self, image_bytes: bytes) -> OCRResult:
        raise OCREngineUnavailable(
            "No OCR engine is installed. Install Tesseract (see the README OCR "
            "setup section) or configure a cloud OCR provider."
        )


_engine: OCREngine | None = None


def get_engine(refresh: bool = False) -> OCREngine:
    """Return the active engine.

    To add a cloud provider: implement ``OCREngine`` and select it here based on
    a settings value (e.g. ``settings.OCR_PROVIDER``).
    """
    global _engine
    if _engine is None or refresh:
        tesseract = TesseractEngine()
        _engine = tesseract if tesseract.is_available() else NullEngine()
        logger.info("OCR engine selected: %s", _engine.name)
    return _engine


def status() -> dict:
    engine = get_engine(refresh=True)
    available = engine.is_available()
    if available:
        return {
            "available": True,
            "engine": engine.name,
            "version": engine.version(),
            "languages": engine.languages(),
            "message": f"Tesseract {engine.version()} is ready.",
            "install_hint": None,
        }
    return {
        "available": False,
        "engine": "unavailable",
        "version": None,
        "languages": [],
        "message": (
            "Receipt scanning is unavailable because the Tesseract OCR binary was "
            "not found. Every other Finora feature works normally - you can still "
            "add transactions manually."
        ),
        "install_hint": (
            "Windows: install from https://github.com/UB-Mannheim/tesseract/wiki "
            "then set TESSERACT_CMD to tesseract.exe. "
            "macOS: brew install tesseract. "
            "Debian/Ubuntu: sudo apt-get install tesseract-ocr. "
            "Docker: already included in the backend image."
        ),
    }
