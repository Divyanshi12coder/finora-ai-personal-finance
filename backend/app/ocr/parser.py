"""Receipt text parser.

Turns raw OCR text into structured fields. This is deliberately a rule-based
parser rather than a model: receipts are semi-structured, the rules are
auditable, and every extraction reports its own confidence so the UI can tell
the user exactly which fields to check.

Strategy per field:

* **total**   - search for keyword-anchored amounts ("total", "grand total",
                "amount payable"), preferring the last/largest match, since
                receipts print subtotal then tax then total. Falls back to the
                largest amount on the receipt.
* **tax**     - keyword-anchored ("gst", "cgst", "sgst", "igst", "vat", "tax"),
                summing split GST components as Indian receipts print them.
* **subtotal**- keyword-anchored, else total minus tax.
* **date**    - a battery of date formats, preferring dates that are plausible
                (not in the future, not absurdly old).
* **merchant**- the first substantial line that is not an address, phone number,
                GSTIN, or generic receipt boilerplate.
* **items**   - lines matching "<description> <optional qty> <amount>", excluding
                any line that looks like a total/tax/payment row.

Nothing here invents data: a field that cannot be found is ``None`` and gets a
warning attached.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# --- Amount patterns ---------------------------------------------------------
# Indian/UK number format: 1,23,456.78 or 1,234.50 or 1923.60 or 450.
#
# The lookbehind/lookahead are essential: without them the grouped alternative
# matches a *prefix* of a long digit run ("1923.60" -> "192" then "3.60"),
# which silently turns a 1,923.60 total into 3.60. The grouped alternative also
# requires at least one comma, so plain runs of digits can only be matched by
# the second alternative, in full. The two lookbehinds reject a start that
# is mid-number (preceded by a digit, or by a decimal point that follows a
# digit) while still allowing an 'Rs.' prefix, which also ends in a dot.
_AMOUNT = (
    r"(?:₹|rs\.?|inr)?\s*"
    r"(?<!\d)(?<!\d\.)(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?!\d)"
)

TOTAL_KEYWORDS = [
    "grand total",
    "nett total",
    "net total",
    "net payable",
    "amount payable",
    "total payable",
    "bill amount",
    "invoice total",
    "total amount",
    "balance due",
    "you pay",
    "total due",
    "total",
]
TAX_KEYWORDS = ["cgst", "sgst", "igst", "gst", "vat", "service tax", "tax"]
SUBTOTAL_KEYWORDS = ["sub total", "subtotal", "sub-total", "taxable value", "gross amount"]

# Lines that are never items.
NON_ITEM_KEYWORDS = [
    *TOTAL_KEYWORDS,
    *TAX_KEYWORDS,
    *SUBTOTAL_KEYWORDS,
    "change",
    "cash",
    "card",
    "upi",
    "paid",
    "tender",
    "rounding",
    "round off",
    "discount",
    "savings",
    "thank",
    "visit",
    "gstin",
    "invoice",
    "bill no",
    "receipt",
    "table",
    "server",
    "cashier",
    "date",
    "time",
    "qty",
    "description",
    "customer",
    "phone",
    "tel",
    "mobile",
    "address",
    "terms",
    "signature",
    "balance",
    "due",
    "payment",
    "mode",
    "ref",
    "auth",
    "batch",
    "tid",
    "mid",
]

# Lines that are never the merchant name.
NON_MERCHANT_PATTERNS = [
    re.compile(r"^\s*[\d\W]+\s*$"),  # digits/punctuation only
    re.compile(r"\b(?:gstin|gst no|tin|pan|cin)\b", re.I),
    re.compile(r"\b(?:tel|phone|mobile|ph)\b[\s:.]*\d", re.I),
    re.compile(r"\b\d{6}\b"),  # PIN code
    re.compile(r"(?:invoice|receipt|bill)\s*(?:no|#|number)", re.I),
    re.compile(r"\b(?:tax invoice|cash memo|retail invoice|duplicate)\b", re.I),
    re.compile(r"^\s*(?:date|time)\b", re.I),
    re.compile(r"@|https?://|www\.", re.I),
]

MERCHANT_MIN_LENGTH = 3
MERCHANT_MAX_LENGTH = 60

DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d.%m.%y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
    "%d %b %y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %b, %Y",
    "%b %d, %Y",
]

_DATE_CANDIDATE = re.compile(
    r"\b("
    r"\d{1,4}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{1,2}[\s-]+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,-]+\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s-]+\d{1,2}[\s,-]+\d{2,4}"
    r")\b",
    re.I,
)

# Receipts older than this are almost certainly a misparse.
MAX_AGE_DAYS = 365 * 3
MAX_PLAUSIBLE_TOTAL = Decimal("10000000")


@dataclass
class ParsedItem:
    name: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total_price: Decimal | None = None


@dataclass
class ParsedReceipt:
    merchant: str | None = None
    receipt_date: date | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str = "INR"
    items: list[ParsedItem] = field(default_factory=list)
    # Per-field confidence in 0..1, so the UI can highlight weak extractions.
    field_confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings) or self.total is None


def _to_decimal(raw: str) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None
    if value < 0 or value > MAX_PLAUSIBLE_TOTAL:
        return None
    return value


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        # OCR frequently emits runs of spaces where a column gap was.
        line = re.sub(r"[ \t]{2,}", "  ", raw).strip()
        # Drop lines that are pure separator noise (----, ====, ....).
        if line and not re.fullmatch(r"[-=_*.~\s]+", line):
            lines.append(line)
    return lines


def _amounts_in(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in re.finditer(_AMOUNT, line, re.I):
        value = _to_decimal(match.group(1))
        if value is not None:
            values.append(value)
    return values


def _find_keyword_amount(
    lines: list[str], keywords: list[str], prefer: str = "last"
) -> tuple[Decimal | None, str | None]:
    """Find the amount on the line best matching one of ``keywords``."""
    matches: list[tuple[int, Decimal, str]] = []

    for line in lines:
        lowered = line.lower()
        for priority, keyword in enumerate(keywords):
            if keyword not in lowered:
                continue
            # Take the amount after the keyword where possible: "Total 450" not
            # the "2" in "Total items 2".
            position = lowered.rfind(keyword) + len(keyword)
            tail = line[position:]
            values = _amounts_in(tail) or _amounts_in(line)
            if values:
                # The rightmost number on a total line is the total.
                matches.append((priority, values[-1], line.strip()))
            break

    if not matches:
        return None, None

    # Lowest keyword priority index wins (keywords are ordered most-specific
    # first); among equals, take the largest amount.
    matches.sort(key=lambda m: (m[0], -m[1]))
    best = matches[0]
    return best[1], best[2]


def _parse_total(lines: list[str], parsed: ParsedReceipt) -> None:
    total, source = _find_keyword_amount(lines, TOTAL_KEYWORDS)
    if total is not None and total > 0:
        parsed.total = total
        parsed.field_confidence["total"] = 0.9
        return

    # Fallback: the largest amount anywhere. Weak, and flagged as such.
    all_amounts = [value for line in lines for value in _amounts_in(line)]
    if all_amounts:
        parsed.total = max(all_amounts)
        parsed.field_confidence["total"] = 0.4
        parsed.warnings.append(
            "No 'total' line was found. The largest amount on the receipt was used "
            "as the total - please verify it."
        )
    else:
        parsed.field_confidence["total"] = 0.0
        parsed.warnings.append("No amount could be read from this receipt.")


def _parse_tax(lines: list[str], parsed: ParsedReceipt) -> None:
    # Indian receipts commonly split GST into CGST + SGST; sum them.
    components: list[Decimal] = []
    for line in lines:
        lowered = line.lower()
        if re.search(r"\b(?:cgst|sgst|igst|utgst)\b", lowered):
            values = _amounts_in(line)
            if values:
                # Skip the rate ("9%") and take the money column.
                money = [v for v in values if "%" not in line or v != values[0]]
                components.append((money or values)[-1])

    if components:
        parsed.tax = sum(components, Decimal("0"))
        parsed.field_confidence["tax"] = 0.85
        return

    tax, _ = _find_keyword_amount(lines, TAX_KEYWORDS)
    if tax is not None:
        parsed.tax = tax
        parsed.field_confidence["tax"] = 0.7
    else:
        parsed.field_confidence["tax"] = 0.0


def _parse_subtotal(lines: list[str], parsed: ParsedReceipt) -> None:
    subtotal, _ = _find_keyword_amount(lines, SUBTOTAL_KEYWORDS)
    if subtotal is not None:
        parsed.subtotal = subtotal
        parsed.field_confidence["subtotal"] = 0.85
        return

    if parsed.total is not None and parsed.tax is not None and parsed.total > parsed.tax:
        parsed.subtotal = parsed.total - parsed.tax
        parsed.field_confidence["subtotal"] = 0.6
    else:
        parsed.field_confidence["subtotal"] = 0.0


def _parse_date(lines: list[str], parsed: ParsedReceipt, today: date | None = None) -> None:
    today = today or date.today()
    candidates: list[date] = []

    for line in lines:
        for match in _DATE_CANDIDATE.finditer(line):
            raw = match.group(1).strip()
            normalised = re.sub(r"\s+", " ", raw).replace(".", "/")
            for fmt in DATE_FORMATS:
                for attempt in (raw, normalised, normalised.replace("/", "-")):
                    try:
                        parsed_date = datetime.strptime(attempt, fmt).date()
                    except ValueError:
                        continue
                    # Reject implausible dates rather than trusting the parse:
                    # "12/13/2026" read as d/m/Y yields a nonsense month.
                    if parsed_date > today + timedelta(days=2):
                        continue
                    if (today - parsed_date).days > MAX_AGE_DAYS:
                        continue
                    candidates.append(parsed_date)
                    break
                else:
                    continue
                break

    if candidates:
        # Receipts print the transaction date near the top; the most recent
        # plausible candidate is the best guess.
        parsed.receipt_date = max(candidates)
        parsed.field_confidence["receipt_date"] = 0.8 if len(set(candidates)) == 1 else 0.6
        if len(set(candidates)) > 1:
            parsed.warnings.append(
                "Several dates were found on this receipt; the most recent plausible "
                "one was used. Please check it."
            )
    else:
        parsed.field_confidence["receipt_date"] = 0.0
        parsed.warnings.append(
            "No date could be read from this receipt. It defaults to today - "
            "change it if that is wrong."
        )


def _parse_merchant(lines: list[str], parsed: ParsedReceipt) -> None:
    # The merchant name is nearly always in the first few lines, in caps.
    for index, line in enumerate(lines[:8]):
        candidate = line.strip(" :*-|")
        if len(candidate) < MERCHANT_MIN_LENGTH:
            continue
        if any(pattern.search(candidate) for pattern in NON_MERCHANT_PATTERNS):
            continue
        # Reject lines that are mostly digits (amounts, phone numbers).
        letters = sum(1 for c in candidate if c.isalpha())
        if letters < len(candidate) * 0.5:
            continue
        if any(keyword in candidate.lower() for keyword in ("total", "gst", "invoice")):
            continue

        cleaned = re.sub(r"\s{2,}", " ", candidate)[:MERCHANT_MAX_LENGTH].strip()
        parsed.merchant = cleaned
        # The very first usable line is the most likely merchant.
        parsed.field_confidence["merchant"] = 0.85 if index == 0 else 0.65
        return

    parsed.field_confidence["merchant"] = 0.0
    parsed.warnings.append("The merchant name could not be identified. Please enter it manually.")


# "<description> [quantity] <amount>" anchored at end of line.
#
# The name group is lazy and deliberately permissive about digits: real product
# lines contain them ("Toor Dal 1kg", "Amul Butter 500g", "Sunflower Oil 1L").
# Anchoring the amount at "$" and leaving the name lazy makes the engine settle
# on the shortest name for which the trailing quantity/amount structure fits.
# Requiring letters in the name is enforced in code, not here.
_ITEM_LINE = re.compile(
    r"^(?P<name>.*?)\s+"
    r"(?:(?P<qty>\d{1,3})\s*(?:x|\*|nos?\.?|pcs?\.?)?\s+)?"
    r"(?:₹|rs\.?|inr)?\s*"
    r"(?<!\d)(?<!\d\.)(?P<amount>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"\s*$",
    re.I,
)

# A line must contain at least two consecutive letters to be a product name.
_HAS_WORD = re.compile(r"[A-Za-z]{2}")


def _parse_items(lines: list[str], parsed: ParsedReceipt) -> None:
    items: list[ParsedItem] = []

    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in NON_ITEM_KEYWORDS):
            continue

        match = _ITEM_LINE.match(line)
        if not match:
            continue

        name = re.sub(r"\s{2,}", " ", match.group("name")).strip(" .:-*|")
        if len(name) < 2 or not _HAS_WORD.search(name):
            continue

        amount = _to_decimal(match.group("amount"))
        if amount is None or amount <= 0:
            continue
        # An "item" equal to the total is the total row misread.
        if parsed.total is not None and amount >= parsed.total and len(lines) > 3:
            continue

        quantity = None
        if match.group("qty"):
            quantity = _to_decimal(match.group("qty"))

        unit_price = (amount / quantity) if quantity and quantity > 0 else None
        items.append(
            ParsedItem(
                name=name[:200],
                quantity=quantity,
                unit_price=unit_price.quantize(Decimal("0.01")) if unit_price else None,
                total_price=amount,
            )
        )

    parsed.items = items[:60]
    parsed.field_confidence["items"] = 0.7 if items else 0.0


def _validate(parsed: ParsedReceipt) -> None:
    """Cross-check the extracted fields and warn on inconsistencies."""
    if parsed.total is not None and parsed.items:
        items_sum = sum(
            (item.total_price for item in parsed.items if item.total_price), Decimal("0")
        )
        if items_sum > 0:
            # Allow 15% slack: discounts, rounding and unread lines are normal.
            deviation = abs(items_sum - parsed.total) / parsed.total
            if deviation > Decimal("0.15"):
                parsed.warnings.append(
                    f"The line items add up to ₹{items_sum:,.2f} but the total reads "
                    f"₹{parsed.total:,.2f}. Some lines may have been misread."
                )

    if parsed.tax is not None and parsed.total is not None:
        if parsed.tax > parsed.total:
            parsed.warnings.append(
                "The extracted tax is larger than the total, which cannot be right. "
                "Please check both values."
            )
            parsed.field_confidence["tax"] = 0.1
        elif parsed.total > 0 and parsed.tax / parsed.total > Decimal("0.40"):
            parsed.warnings.append(
                f"The tax figure (₹{parsed.tax:,.2f}) is unusually high relative to "
                "the total. Please verify it."
            )

    if parsed.subtotal is not None and parsed.total is not None and parsed.subtotal > parsed.total:
        parsed.warnings.append("The subtotal is larger than the total. Please check both values.")


def parse_receipt(text: str, today: date | None = None) -> ParsedReceipt:
    """Parse raw OCR text into structured receipt fields."""
    parsed = ParsedReceipt()

    if not text or not text.strip():
        parsed.warnings.append("The OCR output was empty - nothing could be parsed.")
        return parsed

    lines = _clean_lines(text)
    if not lines:
        parsed.warnings.append("No usable text lines were found in the OCR output.")
        return parsed

    # Order matters: total feeds tax/subtotal validation and item filtering.
    _parse_merchant(lines, parsed)
    _parse_total(lines, parsed)
    _parse_tax(lines, parsed)
    _parse_subtotal(lines, parsed)
    _parse_date(lines, parsed, today)
    _parse_items(lines, parsed)
    _validate(parsed)

    if parsed.receipt_date is None:
        parsed.receipt_date = today or date.today()

    logger.info(
        "Parsed receipt: merchant=%r total=%s items=%d warnings=%d",
        parsed.merchant,
        parsed.total,
        len(parsed.items),
        len(parsed.warnings),
    )
    return parsed
