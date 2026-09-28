"""Deterministically build the seed training dataset for categorisation.

    python -m ml.build_dataset

IMPORTANT / HONESTY NOTE
------------------------
This is a *demonstration* dataset. It is not scraped from real bank statements
(those are private data). It is composed from curated, real-world merchant names
crossed with the narration templates Indian banks/UPI apps actually emit. The
merchants are real brands; the transactions themselves are fictional.

Because the generator is seeded, the CSV is reproducible: anyone can re-run this
script and obtain the committed dataset. Model metrics reported in the README
therefore correspond to a dataset that can be regenerated and audited.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass

from ml.paths import SEED_DATASET, ensure_dirs

RANDOM_SEED = 20260928

# --- Narration templates observed in Indian statements -----------------------
# {m} = merchant, {ref} = numeric reference, {card} = masked card, {city} = city.
EXPENSE_TEMPLATES = [
    "UPI/{m}/{ref}/Payment",
    "UPI-{m}-{ref}@okhdfcbank",
    "POS {card} {m} {city}",
    "{m}",
    "{m} {city}",
    "PAYTM-{m}-{ref}",
    "DEBIT CARD PURCHASE {m}",
    "IMPS/{ref}/{m}",
    "NEFT DR {m} {ref}",
    "{m} online order",
    "Card payment to {m}",
    "BHIM UPI/{m}/{ref}",
]

INCOME_TEMPLATES = [
    "NEFT CR {m} SALARY",
    "SALARY CREDIT {m} {ref}",
    "{m} monthly salary",
    "ACH CR {m} PAYROLL",
    "CREDIT INTEREST {m}",
    "{m} dividend payout",
    "IMPS CR {ref} {m}",
]

CITIES = [
    "MUMBAI",
    "BENGALURU",
    "PUNE",
    "DELHI",
    "HYDERABAD",
    "CHENNAI",
    "KOLKATA",
    "JAIPUR",
    "INDORE",
    "NOIDA",
    "GURUGRAM",
    "KOCHI",
]


@dataclass(frozen=True)
class CategorySpec:
    category: str
    kind: str  # "expense" | "income"
    merchants: tuple[str, ...]
    descriptions: tuple[str, ...]
    payment_methods: tuple[str, ...]


UPI_CARD = ("UPI", "Debit Card", "Credit Card", "Net Banking")
BANK = ("Bank Transfer", "Net Banking")

SPECS: tuple[CategorySpec, ...] = (
    CategorySpec(
        "Food",
        "expense",
        (
            "Swiggy",
            "Zomato",
            "Swiggy Instamart",
            "Dominos Pizza",
            "Starbucks Coffee",
            "Cafe Coffee Day",
            "Chaayos",
            "Burger King",
            "KFC India",
            "Third Wave Coffee",
            "Haldirams Sweets",
            "Barbeque Nation",
            "Blinkit",
            "Zepto",
            "Bigbasket",
            "Reliance Fresh",
            "DMart Grocery",
            "Licious",
            "Faasos",
            "Behrouz Biryani",
            "McDonalds",
            "Subway",
            "Theobroma",
            "Wow Momo",
            "Naturals Ice Cream",
        ),
        (
            "food order",
            "dinner delivery",
            "lunch order",
            "grocery basket",
            "coffee",
            "snacks",
            "weekly groceries",
            "team lunch",
            "breakfast order",
            "dessert",
            "milk and eggs",
            "vegetables and fruits",
            "restaurant bill",
        ),
        UPI_CARD,
    ),
    CategorySpec(
        "Shopping",
        "expense",
        (
            "Amazon India",
            "Flipkart",
            "Myntra",
            "Ajio",
            "Nykaa",
            "Meesho",
            "Croma Retail",
            "Reliance Digital",
            "Decathlon",
            "IKEA India",
            "H&M India",
            "Zara India",
            "Tata Cliq",
            "Lenskart",
            "Pepperfry",
            "Boat Lifestyle",
            "Westside",
            "Shoppers Stop",
            "FirstCry",
            "Titan World",
        ),
        (
            "online purchase",
            "clothing order",
            "electronics order",
            "home decor",
            "footwear",
            "skincare order",
            "headphones",
            "kitchen appliance",
            "sports gear",
            "furniture",
            "gift purchase",
            "accessories",
        ),
        UPI_CARD,
    ),
    CategorySpec(
        "Transport",
        "expense",
        (
            "Uber India",
            "Ola Cabs",
            "Rapido",
            "Indian Oil Petrol Pump",
            "HP Petrol Pump",
            "Shell Fuel Station",
            "Bharat Petroleum",
            "Namma Metro",
            "Delhi Metro Rail",
            "BMTC Bus",
            "FASTag Recharge",
            "Park Plus Parking",
            "Blu Smart",
            "Yulu Bikes",
            "Zoomcar",
            "Royal Auto Service",
        ),
        (
            "cab ride",
            "auto ride",
            "fuel refill",
            "petrol",
            "metro recharge",
            "bus pass",
            "toll recharge",
            "parking fee",
            "bike rental",
            "car service",
            "airport drop",
            "office commute",
        ),
        UPI_CARD,
    ),
    CategorySpec(
        "Bills",
        "expense",
        (
            "BESCOM Electricity",
            "Tata Power",
            "Adani Electricity",
            "MSEDCL Power",
            "Airtel Postpaid",
            "Jio Fiber",
            "ACT Fibernet",
            "Vodafone Idea",
            "Mahanagar Gas",
            "Indane Gas",
            "BWSSB Water",
            "Bharat Gas",
            "LIC Premium",
            "HDFC Ergo Insurance",
            "Society Maintenance",
        ),
        (
            "electricity bill",
            "broadband bill",
            "mobile recharge",
            "postpaid bill",
            "gas cylinder booking",
            "water bill",
            "insurance premium",
            "piped gas bill",
            "maintenance charges",
            "utility payment",
        ),
        ("UPI", "Net Banking", "Auto Debit", "Credit Card"),
    ),
    CategorySpec(
        "Entertainment",
        "expense",
        (
            "Netflix",
            "Spotify India",
            "Amazon Prime Video",
            "Disney Plus Hotstar",
            "JioCinema",
            "BookMyShow",
            "PVR Cinemas",
            "INOX Movies",
            "Sony LIV",
            "YouTube Premium",
            "Steam Games",
            "Audible India",
            "Zee5",
            "Apple Music",
        ),
        (
            "subscription renewal",
            "movie tickets",
            "monthly plan",
            "annual plan",
            "concert tickets",
            "game purchase",
            "audiobook",
            "streaming plan",
            "weekend movie",
            "music subscription",
        ),
        ("UPI", "Credit Card", "Debit Card", "Auto Debit"),
    ),
    CategorySpec(
        "Healthcare",
        "expense",
        (
            "Apollo Pharmacy",
            "PharmEasy",
            "1mg Tata",
            "Practo Consultation",
            "Manipal Hospital",
            "Fortis Healthcare",
            "Dr Lal PathLabs",
            "Thyrocare",
            "MedPlus",
            "Cult Fit",
            "Netmeds",
            "Max Healthcare",
            "Clove Dental",
            "Wellness Forever",
        ),
        (
            "medicines",
            "doctor consultation",
            "lab test",
            "health checkup",
            "dental visit",
            "physiotherapy session",
            "gym membership",
            "vitamins order",
            "vaccination",
            "eye checkup",
        ),
        UPI_CARD,
    ),
    CategorySpec(
        "Education",
        "expense",
        (
            "Udemy",
            "Coursera",
            "BYJUS Learning",
            "Unacademy",
            "Vedantu",
            "upGrad",
            "Great Learning",
            "Scaler Academy",
            "Amazon Kindle Books",
            "Crossword Bookstore",
            "NPTEL Certification",
            "Duolingo Plus",
            "Cambridge Assessment",
            "Physics Wallah",
        ),
        (
            "course fee",
            "certification exam",
            "tuition fee",
            "study material",
            "textbooks",
            "online class",
            "workshop registration",
            "subscription for learning",
            "semester fee",
            "coaching fee",
        ),
        ("UPI", "Net Banking", "Credit Card", "Debit Card"),
    ),
    CategorySpec(
        "Travel",
        "expense",
        (
            "MakeMyTrip",
            "Goibibo",
            "IRCTC Rail Connect",
            "IndiGo Airlines",
            "Air India",
            "Vistara",
            "OYO Rooms",
            "Airbnb India",
            "Yatra Online",
            "Cleartrip",
            "Taj Hotels",
            "Treebo Hotels",
            "RedBus",
            "EaseMyTrip",
        ),
        (
            "flight booking",
            "train ticket",
            "hotel stay",
            "holiday package",
            "bus booking",
            "resort booking",
            "visa fee",
            "travel insurance",
            "weekend trip",
            "airport lounge",
        ),
        ("Credit Card", "Debit Card", "Net Banking", "UPI"),
    ),
    CategorySpec(
        "Rent",
        "expense",
        (
            "Nestaway Rent",
            "Landlord Rent Transfer",
            "Colive Rent",
            "Stanza Living",
            "Zolo Stays",
            "House Rent Payment",
            "NoBroker Pay",
            "Property Rent",
        ),
        (
            "monthly house rent",
            "flat rent",
            "pg rent",
            "rent transfer",
            "apartment rent",
            "co-living rent",
            "rent via nobroker",
        ),
        ("Bank Transfer", "UPI", "Net Banking"),
    ),
    CategorySpec(
        "Salary",
        "income",
        (
            "Infosys Ltd",
            "Tata Consultancy Services",
            "Wipro Ltd",
            "HCL Technologies",
            "Accenture India",
            "Zoho Corp",
            "Freshworks Inc",
            "Razorpay Software",
            "Flipkart Internet",
            "Swiggy Bundl Technologies",
            "Deloitte India",
            "Cognizant Technology",
        ),
        (
            "monthly salary credit",
            "payroll credit",
            "salary for september",
            "net pay",
            "monthly remuneration",
            "consulting retainer",
            "freelance invoice payment",
            "performance bonus",
        ),
        BANK,
    ),
    CategorySpec(
        "Investments",
        "expense",
        (
            "Zerodha Kite",
            "Groww Invest",
            "Upstox",
            "Kuvera SIP",
            "HDFC Mutual Fund",
            "SBI Mutual Fund",
            "ICICI Prudential SIP",
            "Axis Bluechip SIP",
            "Public Provident Fund",
            "National Pension Scheme",
            "INDmoney",
            "Paytm Money",
            "Nippon India SIP",
        ),
        (
            "sip installment",
            "mutual fund purchase",
            "equity purchase",
            "recurring deposit",
            "ppf contribution",
            "nps contribution",
            "index fund investment",
            "gold bond purchase",
            "portfolio top up",
        ),
        ("Net Banking", "Auto Debit", "UPI", "Bank Transfer"),
    ),
    CategorySpec(
        "Other",
        "expense",
        (
            "Cash Withdrawal ATM",
            "Bank Service Charge",
            "Cheque Payment",
            "Donation GiveIndia",
            "Courier Bluedart",
            "Urban Company",
            "Post Office",
            "Municipal Tax",
            "Locksmith Service",
            "NGO Contribution",
            "Miscellaneous Payment",
            "Passport Seva",
        ),
        (
            "cash withdrawal",
            "bank charges",
            "donation",
            "courier charges",
            "home service",
            "government fee",
            "misc payment",
            "handyman",
            "annual fee",
            "penalty payment",
            "unclassified spend",
        ),
        ("Cash", "UPI", "Debit Card", "Net Banking"),
    ),
)

ROWS_PER_CATEGORY = 120

# --- Genuinely ambiguous merchants ------------------------------------------
# A single merchant that legitimately maps to several categories depending on
# WHAT was bought. These rows are what stop the model from degenerating into a
# merchant lookup table: the merchant token alone cannot decide the label, so
# the classifier has to learn from the description too. They are also the rows
# where the confidence score earns its keep - the UI surfaces low-confidence
# predictions for review rather than applying them silently.
AMBIGUOUS: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    (
        "Amazon India",
        (
            ("Shopping", ("order for home goods", "electronics order", "apparel order")),
            ("Entertainment", ("prime video subscription", "prime membership renewal")),
            ("Education", ("kindle ebook purchase", "textbook order", "exam guide")),
            ("Food", ("amazon fresh groceries", "pantry staples order")),
        ),
    ),
    (
        "Swiggy",
        (
            ("Food", ("dinner delivery", "restaurant order", "late night food")),
            ("Shopping", ("instamart household items", "instamart cleaning supplies")),
        ),
    ),
    (
        "Reliance Digital",
        (
            ("Shopping", ("laptop purchase", "television purchase", "appliance")),
            ("Bills", ("mobile bill payment counter", "dth recharge")),
        ),
    ),
    (
        "Paytm Wallet",
        (
            ("Bills", ("electricity bill payment", "mobile recharge", "dth bill")),
            ("Transport", ("metro card recharge", "fastag topup", "cab fare")),
            ("Entertainment", ("movie ticket booking", "event booking")),
            ("Other", ("wallet topup", "money transfer to contact")),
        ),
    ),
    (
        "DMart",
        (
            ("Food", ("monthly groceries", "vegetables and staples", "dairy items")),
            ("Shopping", ("kitchenware purchase", "clothing section", "home essentials")),
        ),
    ),
    (
        "Apollo Pharmacy",
        (
            ("Healthcare", ("prescription medicines", "diabetes strips", "first aid")),
            ("Shopping", ("toiletries and cosmetics", "baby care products")),
        ),
    ),
    (
        "Indian Oil",
        (
            ("Transport", ("petrol refill", "diesel refill", "fuel topup")),
            ("Food", ("highway convenience store snacks",)),
        ),
    ),
    (
        "BookMyShow",
        (
            ("Entertainment", ("movie tickets", "stand up comedy show", "concert")),
            ("Travel", ("event travel package", "out of town event booking")),
        ),
    ),
    (
        "Croma",
        (
            ("Shopping", ("headphones", "smart watch", "home appliance")),
            ("Education", ("tablet for online classes", "e reader purchase")),
        ),
    ),
    (
        "HDFC Bank",
        (
            ("Bills", ("credit card bill payment", "loan emi debit")),
            ("Investments", ("recurring deposit debit", "mutual fund sip debit")),
            ("Other", ("annual card fee", "service charge")),
        ),
    ),
    (
        "Urban Company",
        (
            ("Other", ("home cleaning service", "appliance repair")),
            ("Healthcare", ("salon and wellness at home", "massage therapy session")),
        ),
    ),
    (
        "Blinkit",
        (
            ("Food", ("groceries in ten minutes", "milk bread eggs")),
            ("Healthcare", ("otc medicines delivery", "sanitiser and masks")),
        ),
    ),
)

AMBIGUOUS_ROWS_PER_MERCHANT = 34

# Payment methods usable for any ambiguous row.
GENERIC_METHODS = ("UPI", "Debit Card", "Credit Card", "Net Banking")


def _card_mask(rng: random.Random) -> str:
    return f"{rng.randint(4000, 5999)}XXXX{rng.randint(1000, 9999)}"


def _garble(merchant: str, rng: random.Random) -> str:
    """Mangle a merchant name the way a real card network truncates it.

    Real statements contain "AMAZONIN", "SWIGGYBANGALORE", "STARBUCK" and other
    truncations. Training on clean names only would make the model brittle
    exactly where production data is messiest - this is what the character
    n-gram branch of the pipeline is there to absorb.
    """
    style = rng.random()
    compact = merchant.replace(" ", "")
    if style < 0.35:
        return compact.upper()[: rng.randint(8, 14)]
    if style < 0.6:
        return merchant.split(" ")[0].upper()
    if style < 0.8:
        # Drop internal vowels, as some acquirers do to fit field widths.
        head = compact[:2]
        tail = "".join(ch for ch in compact[2:] if ch.lower() not in "aeiou")
        return (head + tail).upper()[:14]
    return compact.upper()


def build_rows() -> list[dict[str, str]]:
    rng = random.Random(RANDOM_SEED)
    rows: list[dict[str, str]] = []

    def emit(
        merchant: str,
        description_pool: tuple[str, ...],
        kind: str,
        category: str,
        payment_methods: tuple[str, ...],
    ) -> None:
        templates = INCOME_TEMPLATES if kind == "income" else EXPENSE_TEMPLATES
        template = rng.choice(templates)
        upper_style = "POS" in template or "NEFT" in template or "ACH" in template

        # ~22% of rows carry a garbled merchant name in the narration.
        narration_merchant = (
            _garble(merchant, rng)
            if rng.random() < 0.22
            else (merchant.upper() if upper_style else merchant)
        )
        narration = template.format(
            m=narration_merchant,
            ref=rng.randint(100000, 999999),
            card=_card_mask(rng),
            city=rng.choice(CITIES),
        )
        description = rng.choice(description_pool)

        # ~40% of rows are raw narration only, as arrives from a bank feed.
        if rng.random() < 0.40:
            description_field = narration
        else:
            description_field = f"{narration} - {description}"

        # ~18% of rows have no structured merchant field at all: plenty of real
        # feeds give you nothing but the narration string.
        merchant_field = "" if rng.random() < 0.18 else merchant

        rows.append(
            {
                "description": description_field,
                "merchant": merchant_field,
                "payment_method": rng.choice(payment_methods),
                "transaction_type": kind,
                "category": category,
            }
        )

    for spec in SPECS:
        for _ in range(ROWS_PER_CATEGORY):
            emit(
                merchant=rng.choice(spec.merchants),
                description_pool=spec.descriptions,
                kind=spec.kind,
                category=spec.category,
                payment_methods=spec.payment_methods,
            )

    for merchant, options in AMBIGUOUS:
        for _ in range(AMBIGUOUS_ROWS_PER_MERCHANT):
            category, description_pool = rng.choice(options)
            emit(
                merchant=merchant,
                description_pool=description_pool,
                kind="expense",
                category=category,
                payment_methods=GENERIC_METHODS,
            )

    rng.shuffle(rows)
    return rows


def main() -> None:
    ensure_dirs()
    rows = build_rows()
    fieldnames = ["description", "merchant", "payment_method", "transaction_type", "category"]
    with SEED_DATASET.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {SEED_DATASET}")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    for category in sorted(counts):
        print(f"  {category:<14} {counts[category]}")


if __name__ == "__main__":
    main()
