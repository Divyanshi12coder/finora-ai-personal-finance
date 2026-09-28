"""Finora API application factory.

Deliberately thin: it wires configuration, middleware, exception handlers and
routers together. All behaviour lives in the services, ml, ocr and ai packages.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.logging_config import configure_logging
from app.routers import ai, analytics, auth, budgets, goals, insights, receipts, transactions

logger = logging.getLogger(__name__)

DESCRIPTION = """
**Finora** is an AI-powered personal finance platform.

### How the AI works

Finora's backend computes every financial figure from PostgreSQL, then uses a
language model only to *explain* those verified numbers. The model never has
database access, never performs arithmetic, and is instructed never to introduce
a figure that is not in the retrieved facts. If no AI provider is configured,
the same facts are phrased by a built-in deterministic explainer - answers stay
correct, only the prose changes.

### Machine learning

* **Transaction categorisation** - TF-IDF (word 1-2 grams + character 3-5 grams)
  into multinomial Logistic Regression, trained by `python -m ml.train`. User
  corrections are logged and fed back into the next training run.
* **Unusual spending** - MAD-based modified z-score per category, plus an
  Isolation Forest over amount, category-relative size, timing, merchant
  familiarity and recency.
* **Cash-flow forecasting** - exponential smoothing, with the model variant
  chosen by how much history exists; declines to forecast below three months.
* **OCR** - OpenCV preprocessing into Tesseract, then a rule-based receipt parser
  that reports per-field confidence.

### Authentication

Call `POST /api/auth/register` or `POST /api/auth/login`, then send the returned
token as `Authorization: Bearer <token>`. Every financial endpoint is scoped to
the authenticated user.

_Finora provides educational insights from the data you enter. It is not
professional financial, investment, tax or legal advice._
"""

TAGS_METADATA = [
    {"name": "Authentication", "description": "Registration, login, profile and password reset."},
    {"name": "Transactions", "description": "Transaction CRUD, categories and ML categorisation."},
    {"name": "Budgets", "description": "Budgets with live utilisation and AI recommendations."},
    {
        "name": "Analytics",
        "description": "Dashboard, analytics, forecasting, health score, anomalies.",
    },
    {"name": "Insights", "description": "The generated insight engine."},
    {"name": "Goals", "description": "Financial goals and contributions."},
    {"name": "Receipts & OCR", "description": "Receipt upload, OCR processing and confirmation."},
    {
        "name": "AI Assistant",
        "description": "Conversational assistant over verified financial data.",
    },
    {"name": "System", "description": "Health checks and service status."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "Starting %s v%s (%s)", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT
    )

    if settings.JWT_SECRET == "dev-only-insecure-secret-change-me":
        logger.warning(
            "JWT_SECRET is still the default development value. Set a strong "
            "JWT_SECRET before deploying anywhere real."
        )

    # On the SQLite dev fallback, create tables directly so the project runs
    # without a migration step. With PostgreSQL, Alembic owns the schema.
    if settings.is_sqlite:
        from app.database import create_all

        create_all()
        logger.info("SQLite schema ensured via metadata create_all")

    # Seed the shared category set and report subsystem availability.
    try:
        from app.database import session_scope
        from app.services import category_service

        with session_scope() as session:
            category_service.ensure_system_categories(session)
    except SQLAlchemyError:
        logger.exception(
            "Could not ensure system categories - is the database reachable and migrated?"
        )

    from app.ml import categorizer
    from app.ocr import engine as ocr_engine

    model_status = categorizer.status()
    if model_status["available"]:
        logger.info(
            "Categorisation model loaded (version=%s, trained_at=%s)",
            model_status["pipeline_version"],
            model_status["trained_at"],
        )
    else:
        logger.warning(
            "Categorisation model unavailable - run `python -m ml.train`. "
            "Transactions can still be categorised manually."
        )

    ocr_info = ocr_engine.status()
    logger.info("OCR: %s", ocr_info["message"])

    from app.ai.provider import status as ai_status

    logger.info("AI: %s", ai_status()["message"])

    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description=DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    contact={"name": "Finora", "url": "https://github.com/"},
    license_info={"name": "MIT"},
)

# CORS is restricted to the configured origins - never "*", because the API is
# consumed with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    max_age=600,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and timing to every response, and log failures."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration = (time.perf_counter() - started) * 1000
        logger.exception(
            "Unhandled error [%s] %s %s after %.1fms",
            request_id,
            request.method,
            request.url.path,
            duration,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal error occurred. Please try again.",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    duration = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration:.1f}"

    if response.status_code >= 500:
        logger.error(
            "[%s] %s %s -> %s (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
    elif response.status_code >= 400:
        logger.info(
            "[%s] %s %s -> %s (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return field-level validation errors the frontend can display inline."""
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body") or "body",
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    logger.info("Validation failed for %s %s: %s", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    """Never leak SQL or schema details to the client."""
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "A database error occurred. Please try again shortly."},
    )


# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(transactions.router, prefix=settings.API_PREFIX)
app.include_router(budgets.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(insights.router, prefix=settings.API_PREFIX)
app.include_router(goals.router, prefix=settings.API_PREFIX)
app.include_router(receipts.router, prefix=settings.API_PREFIX)
app.include_router(ai.router, prefix=settings.API_PREFIX)


@app.get("/", tags=["System"], summary="Service banner")
def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": settings.APP_DESCRIPTION,
        "docs": f"{settings.API_PREFIX}/docs",
        "health": f"{settings.API_PREFIX}/health",
    }


@app.get(
    f"{settings.API_PREFIX}/health",
    tags=["System"],
    summary="Health check",
    description=(
        "Reports database connectivity plus the availability of the ML model, OCR "
        "engine and AI provider. Returns 200 whenever the database is reachable: "
        "the optional subsystems are reported, not required."
    ),
)
def health() -> JSONResponse:
    from sqlalchemy import text

    from app.ai.provider import status as ai_status
    from app.database import engine
    from app.ml import categorizer
    from app.ocr import engine as ocr_engine

    database_ok = True
    database_error: str | None = None
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        database_ok = False
        database_error = type(exc).__name__
        logger.error("Health check database failure: %s", exc)

    model = categorizer.status()
    ocr = ocr_engine.status()
    ai_info = ai_status()

    payload = {
        "status": "ok" if database_ok else "degraded",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "database": {
            "connected": database_ok,
            "engine": "sqlite" if settings.is_sqlite else "postgresql",
            "error": database_error,
        },
        "ml_categorizer": {
            "available": model["available"],
            "version": model["pipeline_version"],
            "trained_at": model["trained_at"],
        },
        "ocr": {"available": ocr["available"], "engine": ocr["engine"]},
        "ai": {"configured": ai_info["configured"], "mode": ai_info["mode"]},
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if database_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
