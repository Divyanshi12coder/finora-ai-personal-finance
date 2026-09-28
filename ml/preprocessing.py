"""Text preprocessing shared by training and inference.

This module is imported by BOTH ``ml.train`` and the FastAPI backend, so the
exact same normalisation is applied when the model is fitted and when it is
used for prediction. Keeping it in a single module is what prevents the classic
train/serve skew bug.

The normalisation targets Indian bank / UPI / card narration strings, e.g.::

    "UPI/SWIGGY/428391/Food order"        -> "upi swiggy food order"
    "POS 4521XXXX7823 STARBUCKS MUMBAI"   -> "pos <cardnum> starbucks mumbai"
    "NEFT CR INFOSYS LTD SALARY SEP"      -> "neft cr infosys ltd salary sep"
"""

from __future__ import annotations

import re
import unicodedata

# Ordered list of (pattern, replacement). Order matters: the more specific
# patterns (masked card numbers, amounts) run before the generic digit rule.
_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    # Masked card numbers such as 4521XXXX7823 or 4521********7823
    (re.compile(r"\b\d{4}[x*]{2,}\d{2,4}\b", re.I), " cardnum "),
    # Currency amounts: rs.450, inr 450, ₹450.50, 450/-
    (re.compile(r"(?:₹|\brs\.?\b|\binr\b)\s*\d+(?:[.,]\d+)?", re.I), " amount "),
    (re.compile(r"\b\d+(?:[.,]\d+)?\s*/-"), " amount "),
    # Dates: 28/09/2026, 2026-09-28, 28-09-26
    (re.compile(r"\b\d{1,4}[-/]\d{1,2}[-/]\d{2,4}\b"), " date "),
    # Long reference / UTR numbers are pure noise for categorisation.
    (re.compile(r"\b\d{6,}\b"), " ref "),
]

# Narration scaffolding that appears across every category and therefore
# carries no signal. Removing it sharpens the TF-IDF weights on merchants.
_STOP_TOKENS = {
    "txn",
    "transaction",
    "ref",
    "refno",
    "no",
    "id",
    "amount",
    "date",
    "cardnum",
    "inr",
    "rs",
    "the",
    "for",
    "and",
    "via",
    "to",
    "from",
    "at",
    "on",
    "of",
    "xx",
    "xxx",
    "xxxx",
}

_NON_WORD = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str | None) -> str:
    """Return a lowercase, denoised token string ready for vectorisation."""
    if not text:
        return ""

    # Strip accents so "Café" and "Cafe" share a token.
    value = unicodedata.normalize("NFKD", str(text))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()

    for pattern, replacement in _SUBSTITUTIONS:
        value = pattern.sub(replacement, value)

    value = _NON_WORD.sub(" ", value)
    value = _WHITESPACE.sub(" ", value).strip()

    tokens = [t for t in value.split(" ") if t and t not in _STOP_TOKENS and not t.isdigit()]
    return " ".join(tokens)


def build_document(
    description: str | None = None,
    merchant: str | None = None,
    payment_method: str | None = None,
    transaction_type: str | None = None,
) -> str:
    """Compose the single text document the classifier consumes.

    The merchant is repeated twice: it is by far the strongest categorisation
    signal, and duplicating the token is a cheap, transparent way of weighting
    it inside a bag-of-words model (no custom feature union required).
    """
    parts: list[str] = []
    merchant_norm = normalize_text(merchant)
    if merchant_norm:
        parts.extend([merchant_norm, merchant_norm])
    description_norm = normalize_text(description)
    if description_norm:
        parts.append(description_norm)
    method_norm = normalize_text(payment_method)
    if method_norm:
        parts.append(f"pay_{method_norm.replace(' ', '_')}")
    type_norm = normalize_text(transaction_type)
    if type_norm:
        parts.append(f"type_{type_norm.replace(' ', '_')}")
    return " ".join(p for p in parts if p).strip()
