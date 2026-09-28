"""Command-line inference against the persisted model.

    python -m ml.predict "Swiggy order 450"
    python -m ml.predict "UPI/UBER/8823/ride" --merchant "Uber India" --explain

Useful for sanity-checking the model without booting the API.
"""

from __future__ import annotations

import argparse
import json
import sys

from ml.model_store import get_categorizer
from ml.preprocessing import build_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Predict a transaction category")
    parser.add_argument("description", help="Raw transaction description / narration")
    parser.add_argument("--merchant", default=None)
    parser.add_argument("--payment-method", default=None)
    parser.add_argument("--type", dest="transaction_type", default="expense")
    parser.add_argument("--explain", action="store_true", help="Show driving tokens")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    model = get_categorizer()
    if not model.is_available:
        print(f"ERROR: {model.error}", file=sys.stderr)
        return 1

    prediction = model.predict(
        description=args.description,
        merchant=args.merchant,
        payment_method=args.payment_method,
        transaction_type=args.transaction_type,
    )
    if prediction is None:
        print("ERROR: not enough text to categorise", file=sys.stderr)
        return 1

    payload = prediction.as_dict()
    if args.explain:
        document = build_document(
            description=args.description,
            merchant=args.merchant,
            payment_method=args.payment_method,
            transaction_type=args.transaction_type,
        )
        payload["explanation"] = [
            {"token": token, "contribution": round(value, 4)}
            for token, value in model.explain(document)
        ]

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"category   : {payload['category']}")
    print(f"confidence : {payload['confidence']:.2%}")
    if payload["alternatives"]:
        alts = ", ".join(
            f"{a['category']} ({a['confidence']:.1%})" for a in payload["alternatives"]
        )
        print(f"runners-up : {alts}")
    if args.explain:
        print("driving tokens:")
        for item in payload["explanation"]:
            print(f"  {item['token']:<28} {item['contribution']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
