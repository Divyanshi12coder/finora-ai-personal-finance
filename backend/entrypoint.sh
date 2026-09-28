#!/bin/sh
# Container entrypoint: wait for the database, migrate, optionally seed, then run.
set -e

echo "[finora] waiting for the database..."
python - <<'PYWAIT'
import os
import sys
import time

from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("[finora] DATABASE_URL not set; using the SQLite fallback")
    sys.exit(0)

if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]

deadline = time.time() + 60
last_error = None
while time.time() < deadline:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("[finora] database is ready")
        sys.exit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(1.5)

print(f"[finora] database did not become ready in time: {last_error}", file=sys.stderr)
sys.exit(1)
PYWAIT

echo "[finora] applying migrations..."
alembic upgrade head

# Seed demo data on first boot when asked. `app.seed` is a no-op if the demo
# user already exists, so this is safe to leave enabled.
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "[finora] seeding demo data..."
  python -m app.seed || echo "[finora] seeding skipped or already done"
fi

echo "[finora] starting: $*"
exec "$@"
