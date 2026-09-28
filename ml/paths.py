"""Filesystem locations used by the ML package.

Keeping these in one module means the training scripts and the FastAPI backend
always agree on where artefacts live, regardless of the current working
directory.
"""

from __future__ import annotations

import os
from pathlib import Path

ML_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = ML_DIR.parent

DATASETS_DIR: Path = ML_DIR / "datasets"
MODELS_DIR: Path = Path(os.getenv("FINORA_ML_MODELS_DIR") or (ML_DIR / "models"))

SEED_DATASET: Path = DATASETS_DIR / "seed_transactions.csv"
CORRECTIONS_DATASET: Path = DATASETS_DIR / "corrections.csv"

CATEGORIZER_MODEL: Path = MODELS_DIR / "categorizer.joblib"
CATEGORIZER_METRICS: Path = MODELS_DIR / "categorizer_metrics.json"


def ensure_dirs() -> None:
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
