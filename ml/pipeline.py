"""The scikit-learn pipeline used for transaction categorisation.

Defined in one place so that ``ml.train`` fits exactly the estimator that the
backend later loads, and so the architecture is documented in code rather than
only in the README.

    word TF-IDF (1-2 grams)  ─┐
                              ├─ FeatureUnion ─> Logistic Regression (multinomial)
    char TF-IDF (3-5 grams)  ─┘

Why these two vectorisers:

* **Word n-grams** capture merchant names and narration phrases
  ("swiggy", "sip installment", "salary credit").
* **Character n-grams** make the model robust to the spelling noise that is
  everywhere in bank narrations - truncated merchant names, missing spaces,
  "AMAZONIN" vs "Amazon India". A pure word model fails on unseen spellings.

Logistic Regression is chosen over a heavier model on purpose: it trains in
under a second, exposes calibrated ``predict_proba`` values (which the UI shows
as a confidence score), and its coefficients are inspectable, so a prediction
can be explained by the tokens that drove it.
"""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

# Model artefact format version. Bumped when the pipeline structure changes so
# the backend can refuse to load an incompatible artefact.
PIPELINE_VERSION = "1.0.0"


def build_pipeline(random_state: int = 42) -> Pipeline:
    """Construct an unfitted categorisation pipeline."""
    word_vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
        lowercase=False,  # text is normalised by ml.preprocessing beforehand
    )
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        sublinear_tf=True,
        min_df=2,
        lowercase=False,
    )

    features = FeatureUnion(
        [("word", word_vectorizer), ("char", char_vectorizer)],
        transformer_weights={"word": 1.0, "char": 0.6},
    )

    classifier = LogisticRegression(
        C=4.0,
        max_iter=2000,
        class_weight="balanced",
        random_state=random_state,
    )

    return Pipeline([("features", features), ("classifier", classifier)])
