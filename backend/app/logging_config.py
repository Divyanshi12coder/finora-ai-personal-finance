"""Logging setup.

Deliberately conservative about what gets written: request paths and user ids
are logged, but never passwords, tokens, Authorization headers, receipt contents
or individual transaction amounts outside of explicit anomaly/OCR diagnostics.
"""

from __future__ import annotations

import logging
import re
import sys

from app.config import settings

# Belt-and-braces redaction. Nothing in the codebase logs these, but a filter on
# the handler means a future careless log line cannot leak a credential either.
_SENSITIVE_PATTERNS = [
    (re.compile(r"(password['\"]?\s*[:=]\s*)(\S+)", re.I), r"\1[REDACTED]"),
    (re.compile(r"(bearer\s+)([A-Za-z0-9._\-]+)", re.I), r"\1[REDACTED]"),
    (re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*)(\S+)", re.I), r"\1[REDACTED]"),
    (re.compile(r"(x-api-key['\"]?\s*[:=]\s*)(\S+)", re.I), r"\1[REDACTED]"),
    (re.compile(r"(authorization['\"]?\s*[:=]\s*)(\S+)", re.I), r"\1[REDACTED]"),
    (re.compile(r"(token['\"]?\s*[:=]\s*)([A-Za-z0-9._\-]{16,})", re.I), r"\1[REDACTED]"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True

        redacted = message
        for pattern, replacement in _SENSITIVE_PATTERNS:
            redacted = pattern.sub(replacement, redacted)

        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-38s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs its own handlers; route them through ours so redaction
    # applies to access logs too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # SQLAlchemy's INFO level is full SQL echo; keep it at WARNING unless asked.
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.SQL_ECHO else logging.WARNING
    )
    # httpx logs every request line at INFO, including the AI provider URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configured at %s (environment=%s)", settings.LOG_LEVEL, settings.ENVIRONMENT
    )
