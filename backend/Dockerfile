# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Finora backend
#
# Tesseract and the OpenCV runtime libraries are installed here, which is why
# receipt OCR works out of the box in Docker even when it is unavailable on the
# host machine.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # The `ml` package lives at the image root alongside `app`.
    PYTHONPATH=/srv

WORKDIR /srv

# System packages:
#   tesseract-ocr        - the OCR engine
#   tesseract-ocr-eng    - English language data
#   libgl1, libglib2.0-0 - OpenCV runtime dependencies
#   curl                 - container healthcheck
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so application edits do not invalidate the layer.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code and the shared ML package.
COPY backend/ ./
COPY ml/ ./ml/

# Train the categorisation model at build time so the image ships ready to
# predict. The dataset is regenerated first, so the artefact always matches the
# committed generator rather than whatever happened to be in the build context.
RUN python -m ml.build_dataset && python -m ml.train --no-cv

# Run as a non-root user.
RUN useradd --create-home --uid 10001 finora \
    && mkdir -p /srv/uploads \
    && chown -R finora:finora /srv
USER finora

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# entrypoint.sh waits for PostgreSQL, applies migrations, then starts the API.
COPY --chown=finora:finora backend/entrypoint.sh /srv/entrypoint.sh
ENTRYPOINT ["/bin/sh", "/srv/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
