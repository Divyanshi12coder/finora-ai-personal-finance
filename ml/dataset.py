"""Dataset loading for the categorisation model.

Two sources are combined:

1. ``ml/datasets/seed_transactions.csv`` - the reproducible demonstration set
   produced by ``python -m ml.build_dataset``.
2. ``ml/datasets/corrections.csv`` - real user corrections exported from the
   application database by ``python -m ml.export_corrections``.

Corrections are the feedback loop: when a user overrides a prediction in the UI
the backend stores the correction, and the next training run treats it as a
labelled example. Corrections are duplicated ``CORRECTION_WEIGHT`` times so that
a handful of real labels can outweigh the synthetic seed rows.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ml.paths import CORRECTIONS_DATASET, SEED_DATASET
from ml.preprocessing import build_document

CORRECTION_WEIGHT = 3

REQUIRED_COLUMNS = {"description", "merchant", "payment_method", "transaction_type", "category"}


@dataclass(frozen=True)
class Dataset:
    documents: list[str]
    labels: list[str]
    sources: list[str]

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.documents)

    @property
    def seed_count(self) -> int:
        return sum(1 for s in self.sources if s == "seed")

    @property
    def correction_count(self) -> int:
        return sum(1 for s in self.sources if s == "correction")


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path.name} is missing required columns: {sorted(missing)}")
        return list(reader)


def _rows_to_examples(rows: list[dict[str, str]], source: str, repeat: int = 1) -> Dataset:
    documents: list[str] = []
    labels: list[str] = []
    sources: list[str] = []
    for row in rows:
        label = (row.get("category") or "").strip()
        if not label:
            continue
        document = build_document(
            description=row.get("description"),
            merchant=row.get("merchant"),
            payment_method=row.get("payment_method"),
            transaction_type=row.get("transaction_type"),
        )
        if not document:
            continue
        for _ in range(repeat):
            documents.append(document)
            labels.append(label)
            sources.append(source)
    return Dataset(documents=documents, labels=labels, sources=sources)


def load_dataset(
    seed_path: Path = SEED_DATASET,
    corrections_path: Path = CORRECTIONS_DATASET,
    include_corrections: bool = True,
) -> Dataset:
    """Load the combined training dataset."""
    if not seed_path.exists():
        raise FileNotFoundError(
            f"Seed dataset not found at {seed_path}. Run `python -m ml.build_dataset` first."
        )

    seed = _rows_to_examples(_read_csv(seed_path), source="seed")
    documents = list(seed.documents)
    labels = list(seed.labels)
    sources = list(seed.sources)

    if include_corrections:
        corrections = _rows_to_examples(
            _read_csv(corrections_path), source="correction", repeat=CORRECTION_WEIGHT
        )
        documents.extend(corrections.documents)
        labels.extend(corrections.labels)
        sources.extend(corrections.sources)

    return Dataset(documents=documents, labels=labels, sources=sources)
