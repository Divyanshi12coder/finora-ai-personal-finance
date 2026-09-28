"""Finora machine-learning package.

Contains the reproducible training pipeline for transaction categorisation:

    python -m ml.build_dataset     # regenerate the seed dataset CSV
    python -m ml.train             # train + evaluate + persist the model
    python -m ml.evaluate          # evaluate the persisted model
    python -m ml.predict "Swiggy order 450"

The FastAPI backend loads the artefact produced by ``ml.train`` and performs
inference through :mod:`backend.app.ml.categorizer`.
"""

__all__ = ["evaluate", "predict", "preprocessing", "train"]
