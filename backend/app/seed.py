"""Demo data seeding.

    python -m app.seed                 # create/refresh the demo user
    python -m app.seed --months 12     # more history
    python -m app.seed --reset         # delete the demo user first
    python -m app.seed --email me@x.com --password 'Secret123'

What this does and does not do
------------------------------
Every transaction is created through ``transaction_service.create_transaction``,
the same function the API uses - so demo rows go through Pydantic validation,
ML categorisation and the regular persistence path. There is no separate
"fake data" code path, and nothing is written to the frontend.

The one deliberate difference: per-transaction anomaly scoring is deferred.
Scoring each row as it is inserted would re-run detection over the whole history
once per row (O(n^2) on ~1,000 rows). Instead the identical detector runs once
as a full sweep at the end, which is also how a production batch job would do it.

The data is fictional but realistic: real Indian merchant names, plausible
amounts, salary on the 1st, rent on the 2nd, subscriptions on fixed days,
weekend-weighted discretionary spending, festive-season uplift in Oct/Nov, and a
handful of genuine outliers so anomaly detection has something real to find.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.database import create_all, session_scope
from app.models import (
    Budget,
    BudgetItem,
    FinancialGoal,
    GoalContribution,
    GoalStatus,
    TransactionSource,
    TransactionType,
)
from app.schemas.auth import RegisterRequest
from app.schemas.transaction import TransactionCreate
from app.services import (
    anomaly_service,
    auth_service,
    budget_service,
    category_service,
    insight_service,
    transaction_service,
)
from app.utils.dates import add_months, month_start
from app.utils.security import hash_password

logger = logging.getLogger(__name__)

RANDOM_SEED = 20260928
DEFAULT_MONTHS = 9

MONTHLY_INCOME = Decimal("145000")
MONTHLY_RENT = Decimal("32000")


@dataclass(frozen=True)
class Recurring:
    """A fixed charge that lands on the same day each month."""

    merchant: str
    category: str
    amount: Decimal
    day: int
    payment_method: str
    description: str
    jitter: Decimal = Decimal("0")


RECURRING: tuple[Recurring, ...] = (
    Recurring(
        "House Rent Payment",
        "Rent",
        MONTHLY_RENT,
        2,
        "Bank Transfer",
        "Monthly house rent transfer",
    ),
    Recurring(
        "Society Maintenance", "Bills", Decimal("3500"), 5, "UPI", "Apartment maintenance charges"
    ),
    Recurring(
        "BESCOM Electricity",
        "Bills",
        Decimal("2400"),
        8,
        "Net Banking",
        "Electricity bill payment",
        Decimal("900"),
    ),
    Recurring("Jio Fiber", "Bills", Decimal("1177"), 6, "Auto Debit", "Broadband monthly plan"),
    Recurring("Airtel Postpaid", "Bills", Decimal("799"), 12, "Auto Debit", "Mobile postpaid bill"),
    Recurring(
        "Mahanagar Gas", "Bills", Decimal("860"), 14, "UPI", "Piped gas bill", Decimal("250")
    ),
    Recurring(
        "Netflix", "Entertainment", Decimal("649"), 7, "Credit Card", "Netflix monthly subscription"
    ),
    Recurring(
        "Spotify India", "Entertainment", Decimal("119"), 11, "Auto Debit", "Spotify Premium"
    ),
    Recurring(
        "Amazon Prime Video", "Entertainment", Decimal("299"), 19, "Credit Card", "Prime membership"
    ),
    Recurring("Cult Fit", "Healthcare", Decimal("1499"), 3, "UPI", "Gym membership monthly"),
    Recurring(
        "HDFC Mutual Fund",
        "Investments",
        Decimal("15000"),
        5,
        "Auto Debit",
        "SIP installment - index fund",
    ),
    Recurring(
        "Axis Bluechip SIP",
        "Investments",
        Decimal("7500"),
        15,
        "Auto Debit",
        "SIP installment - bluechip fund",
    ),
    Recurring("LIC Premium", "Bills", Decimal("2150"), 21, "Net Banking", "Life insurance premium"),
)

# Variable spending: (merchant, category, min, max, payments_per_month,
#                     weekend_weighted, payment methods)
VARIABLE: tuple[tuple[str, str, int, int, int, bool, tuple[str, ...]], ...] = (
    ("Swiggy", "Food", 220, 780, 7, True, ("UPI", "Credit Card")),
    ("Zomato", "Food", 200, 650, 4, True, ("UPI", "Credit Card")),
    ("Blinkit", "Food", 180, 900, 5, False, ("UPI",)),
    ("Bigbasket", "Food", 900, 2800, 2, False, ("UPI", "Debit Card")),
    ("Starbucks Coffee", "Food", 220, 520, 3, True, ("Credit Card",)),
    ("Third Wave Coffee", "Food", 180, 420, 2, True, ("UPI",)),
    ("Reliance Fresh", "Food", 400, 1400, 3, False, ("Debit Card", "UPI")),
    ("Uber India", "Transport", 120, 520, 8, False, ("UPI", "Credit Card")),
    ("Ola Cabs", "Transport", 110, 460, 3, False, ("UPI",)),
    ("Rapido", "Transport", 45, 160, 4, False, ("UPI",)),
    ("Indian Oil Petrol Pump", "Transport", 1500, 3200, 2, False, ("Credit Card",)),
    ("Namma Metro", "Transport", 60, 220, 5, False, ("UPI",)),
    ("Amazon India", "Shopping", 350, 4200, 4, False, ("Credit Card", "UPI")),
    ("Flipkart", "Shopping", 400, 3500, 2, False, ("Credit Card",)),
    ("Myntra", "Shopping", 700, 3800, 2, False, ("Credit Card",)),
    ("Nykaa", "Shopping", 500, 2200, 1, False, ("UPI",)),
    ("Decathlon", "Shopping", 800, 4500, 1, False, ("Debit Card",)),
    ("BookMyShow", "Entertainment", 350, 1200, 2, True, ("Credit Card", "UPI")),
    ("PVR Cinemas", "Entertainment", 400, 1400, 1, True, ("Credit Card",)),
    ("Apollo Pharmacy", "Healthcare", 200, 1600, 2, False, ("UPI", "Debit Card")),
    ("PharmEasy", "Healthcare", 300, 1800, 1, False, ("UPI",)),
    ("Practo Consultation", "Healthcare", 500, 1200, 1, False, ("UPI",)),
    ("Udemy", "Education", 449, 3499, 1, False, ("Credit Card",)),
    ("Amazon Kindle Books", "Education", 199, 899, 1, False, ("Credit Card",)),
    ("Urban Company", "Other", 400, 2200, 1, False, ("UPI",)),
    ("Cash Withdrawal ATM", "Other", 1000, 5000, 1, False, ("Cash",)),
)

# Occasional larger spends, by month offset from the start.
OCCASIONAL: tuple[tuple[str, str, int, int, str], ...] = (
    ("MakeMyTrip", "Travel", 8500, 28000, "Flight booking for weekend trip"),
    ("IRCTC Rail Connect", "Travel", 800, 3200, "Train ticket booking"),
    ("OYO Rooms", "Travel", 2200, 7500, "Hotel stay"),
    ("Croma Retail", "Shopping", 4500, 22000, "Electronics purchase"),
    ("Manipal Hospital", "Healthcare", 2500, 12000, "Health checkup and tests"),
    ("Taj Hotels", "Travel", 6000, 18000, "Anniversary dinner and stay"),
)

# Deliberate outliers so unusual-spending detection has real signal. These are
# genuinely unusual relative to the surrounding distribution; the detector is
# not told about them.
#
# The month offset is explicit and deliberately spread out. Somebody earning
# ~₹1.5L a month does not buy a laptop, have emergency dental work and throw a
# large dinner in three consecutive months - and stacking them would drag the
# 3-month savings rate negative, making the demo look broken rather than
# realistic. The two recent ones sit inside the 90-day anomaly window so they
# are still flagged; the oldest is simply history.
#
#   merchant, category, amount, description, months_ago
OUTLIERS: tuple[tuple[str, str, Decimal, str, int], ...] = (
    ("Swiggy", "Food", Decimal("8450"), "Large group order - team celebration", 1),
    ("Croma Retail", "Shopping", Decimal("64990"), "Laptop purchase - work replacement", 2),
    ("Manipal Hospital", "Healthcare", Decimal("38500"), "Emergency dental procedure", 5),
)

FESTIVE_MONTHS = {10, 11}  # Diwali/festive uplift
FESTIVE_MULTIPLIER = Decimal("1.35")


def _money(rng: random.Random, low: int, high: int) -> Decimal:
    """A plausible amount: round-ish numbers, occasional paise."""
    value = Decimal(rng.randint(low, high))
    if rng.random() < 0.55:
        value = (value / 10).to_integral_value() * 10
    else:
        value += Decimal(rng.randint(0, 99)) / 100
    return value.quantize(Decimal("0.01"))


def _spread_days(rng: random.Random, month: date, count: int, weekend_weighted: bool) -> list[date]:
    """Pick ``count`` distinct days in the month, optionally weekend-heavy."""
    from app.utils.dates import month_end

    last = month_end(month).day
    weights = []
    for day in range(1, last + 1):
        current = month.replace(day=day)
        weight = 1.0
        if weekend_weighted and current.weekday() >= 4:  # Fri-Sun
            weight = 2.4
        weights.append(weight)

    days = rng.choices(range(1, last + 1), weights=weights, k=min(count, last))
    return [month.replace(day=day) for day in sorted(set(days))]


def _delete_user(session: Session, email: str) -> bool:
    user = auth_service.get_by_email(session, email)
    if user is None:
        return False
    session.delete(user)
    session.flush()
    logger.info("Deleted existing user %s", email)
    return True


def seed(
    email: str = "",
    password: str = "",
    full_name: str = "",
    months: int = DEFAULT_MONTHS,
    reset: bool = False,
    today: date | None = None,
) -> dict:
    email = (email or settings.DEMO_EMAIL).lower()
    password = password or settings.DEMO_PASSWORD
    full_name = full_name or settings.DEMO_NAME
    today = today or date.today()
    rng = random.Random(RANDOM_SEED)

    if settings.is_sqlite:
        create_all()

    summary: dict = {"email": email}

    with session_scope() as session:
        category_service.ensure_system_categories(session)

        if reset:
            _delete_user(session, email)

        existing = auth_service.get_by_email(session, email)
        if existing is not None:
            print(
                f"User {email} already exists (id={existing.id}). "
                "Re-run with --reset to rebuild the demo data."
            )
            return {**summary, "created": False, "user_id": existing.id}

        # --- User ---------------------------------------------------------
        user = auth_service.register(
            session,
            RegisterRequest(email=email, password=password, full_name=full_name, currency="INR"),
        )
        user.monthly_income = MONTHLY_INCOME
        user.income_source = "Salaried employment"
        user.typical_monthly_expenses = Decimal("78000")
        user.savings_goal_amount = Decimal("500000")
        user.emergency_fund_target = Decimal("470000")
        user.onboarding_completed = True
        # register() hashed the password already; this keeps the flow explicit
        # when a custom password was supplied.
        user.hashed_password = hash_password(password)
        session.flush()

        categories = category_service.name_to_id_map(session, user)
        start_month = month_start(add_months(today, -(months - 1)))
        created = 0

        def add(
            amount: Decimal,
            tx_type: TransactionType,
            occurred_on: date,
            merchant: str,
            category: str,
            description: str,
            payment_method: str,
            tags: list[str] | None = None,
        ) -> None:
            nonlocal created
            if occurred_on > today:
                return
            transaction_service.create_transaction(
                session,
                user,
                TransactionCreate(
                    amount=amount,
                    type=tx_type,
                    occurred_on=occurred_on,
                    merchant=merchant,
                    description=description,
                    payment_method=payment_method,
                    tags=tags or [],
                    category_id=categories.get(category),
                    auto_categorize=False,  # the category is known for seed rows
                ),
                source=TransactionSource.SEED,
                # Scored in one batch sweep at the end - see the module docstring.
                run_anomaly_check=False,
            )
            created += 1

        # --- Month by month ----------------------------------------------
        for offset in range(months):
            month = add_months(start_month, offset)
            festive = month.month in FESTIVE_MONTHS
            multiplier = FESTIVE_MULTIPLIER if festive else Decimal("1")

            # Salary, with a modest annual increment partway through.
            salary = MONTHLY_INCOME
            if offset >= months // 2:
                salary = (MONTHLY_INCOME * Decimal("1.08")).quantize(Decimal("0.01"))
            # Occasional bonus month.
            add(
                salary,
                TransactionType.INCOME,
                month.replace(day=1),
                "Infosys Ltd",
                "Salary",
                "Monthly salary credit",
                "Bank Transfer",
                ["salary"],
            )
            if festive:
                add(
                    (salary * Decimal("0.45")).quantize(Decimal("0.01")),
                    TransactionType.INCOME,
                    month.replace(day=18),
                    "Infosys Ltd",
                    "Salary",
                    "Festive performance bonus",
                    "Bank Transfer",
                    ["bonus"],
                )

            # A little freelance income, some months.
            if rng.random() < 0.35:
                add(
                    _money(rng, 8000, 26000),
                    TransactionType.INCOME,
                    month.replace(day=rng.randint(10, 26)),
                    "Razorpay Software",
                    "Salary",
                    "Freelance invoice payment",
                    "Bank Transfer",
                    ["freelance"],
                )

            # Recurring charges.
            for item in RECURRING:
                amount = item.amount
                if item.jitter > 0:
                    amount += Decimal(rng.randint(0, int(item.jitter)))
                try:
                    when = month.replace(day=item.day)
                except ValueError:  # pragma: no cover - day always <= 28 here
                    continue
                add(
                    amount.quantize(Decimal("0.01")),
                    TransactionType.EXPENSE,
                    when,
                    item.merchant,
                    item.category,
                    item.description,
                    item.payment_method,
                    ["recurring"],
                )

            # Variable discretionary spending.
            for merchant, category, low, high, per_month, weekend, methods in VARIABLE:
                count = max(0, per_month + rng.randint(-1, 1))
                for when in _spread_days(rng, month, count, weekend):
                    amount = (_money(rng, low, high) * multiplier).quantize(Decimal("0.01"))
                    add(
                        amount,
                        TransactionType.EXPENSE,
                        when,
                        merchant,
                        category,
                        f"{merchant} - {category.lower()} spend",
                        rng.choice(methods),
                    )

            # One or two occasional bigger purchases.
            for _ in range(rng.randint(0, 2)):
                merchant, category, low, high, description = rng.choice(OCCASIONAL)
                add(
                    _money(rng, low, high),
                    TransactionType.EXPENSE,
                    month.replace(day=rng.randint(3, 27)),
                    merchant,
                    category,
                    description,
                    rng.choice(("Credit Card", "Net Banking", "UPI")),
                )

        # --- Outliers -------------------------------------------------------
        # Placed at their declared month offsets (see OUTLIERS above), never in
        # the current month - the dashboard leads with that month, and a large
        # one-off dropped into a partial month misrepresents the picture.
        for merchant, category, amount, description, months_ago in OUTLIERS:
            month = add_months(month_start(today), -months_ago)
            when = month.replace(day=min(rng.randint(6, 24), 28))
            add(
                amount,
                TransactionType.EXPENSE,
                when,
                merchant,
                category,
                description,
                "Credit Card",
                ["large-purchase"],
            )

        session.flush()
        summary["transactions"] = created

        # --- Budgets: current month plus the previous two -----------------
        budget_limits = {
            "Food": Decimal("22000"),
            "Shopping": Decimal("12000"),
            "Transport": Decimal("9000"),
            "Bills": Decimal("12000"),
            "Entertainment": Decimal("4000"),
            "Healthcare": Decimal("5000"),
            "Rent": MONTHLY_RENT,
            "Investments": Decimal("23000"),
        }
        budgets_created = 0
        for offset in range(3):
            period = month_start(add_months(today, -offset))
            if budget_service.get_budget_for_month(session, user, period) is not None:
                continue
            budget = Budget(
                user_id=user.id,
                name=f"{period.strftime('%B %Y')} budget",
                period_month=period,
                total_limit=sum(budget_limits.values(), Decimal("0")),
                notes="Seeded demo budget - edit the limits to see utilisation change.",
            )
            session.add(budget)
            session.flush()
            for name, limit in budget_limits.items():
                category_id = categories.get(name)
                if category_id:
                    session.add(
                        BudgetItem(budget_id=budget.id, category_id=category_id, limit_amount=limit)
                    )
            budgets_created += 1
        session.flush()
        summary["budgets"] = budgets_created

        # --- Goals, with a real contribution ledger -----------------------
        goal_specs = [
            (
                "Emergency Fund",
                "emergency_fund",
                Decimal("470000"),
                Decimal("286000"),
                add_months(today, 14),
                "Shield",
                "#0B1F3A",
            ),
            (
                "Japan Trip",
                "vacation",
                Decimal("280000"),
                Decimal("97500"),
                add_months(today, 9),
                "Plane",
                "#E63946",
            ),
            (
                "MacBook Pro",
                "purchase",
                Decimal("210000"),
                Decimal("164000"),
                add_months(today, 4),
                "Laptop",
                "#132B4F",
            ),
            (
                "Higher Studies Fund",
                "education",
                Decimal("800000"),
                Decimal("142000"),
                add_months(today, 30),
                "GraduationCap",
                "#2A9D8F",
            ),
        ]
        for name, goal_type, target, current, target_date, icon, color in goal_specs:
            goal = FinancialGoal(
                user_id=user.id,
                name=name,
                goal_type=goal_type,
                target_amount=target,
                current_amount=current,
                target_date=target_date,
                icon=icon,
                color=color,
                status=GoalStatus.ACHIEVED if current >= target else GoalStatus.ACTIVE,
            )
            session.add(goal)
            session.flush()

            # Spread the balance across monthly contributions so the pace
            # projection has real data to work from.
            instalments = min(months, 8)
            per_instalment = (current / instalments).quantize(Decimal("0.01"))
            running = Decimal("0")
            for index in range(instalments):
                amount = per_instalment if index < instalments - 1 else current - running
                running += amount
                session.add(
                    GoalContribution(
                        goal_id=goal.id,
                        amount=amount,
                        occurred_on=add_months(month_start(today), -(instalments - 1 - index)),
                        note="Monthly contribution",
                    )
                )
        session.flush()
        summary["goals"] = len(goal_specs)

        # --- Run the real detectors over the seeded history ---------------
        anomaly_result = anomaly_service.run_detection(session, user, today)
        summary["anomalies_flagged"] = len(anomaly_result.get("anomalies", []))

        insights, ai_used = insight_service.generate_insights(session, user, today, use_ai=False)
        summary["insights"] = len(insights)

        summary["created"] = True
        summary["user_id"] = user.id

    return summary


def main() -> int:
    from app.logging_config import configure_logging

    parser = argparse.ArgumentParser(description="Seed Finora demo data")
    parser.add_argument("--email", default="", help=f"default: {settings.DEMO_EMAIL}")
    parser.add_argument("--password", default="", help="default: from DEMO_PASSWORD")
    parser.add_argument("--name", default="", help=f"default: {settings.DEMO_NAME}")
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_MONTHS,
        help=f"months of history (default {DEFAULT_MONTHS})",
    )
    parser.add_argument("--reset", action="store_true", help="delete the user first, then reseed")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet:
        configure_logging()

    if args.months < 1 or args.months > 36:
        print("--months must be between 1 and 36", file=sys.stderr)
        return 2

    result = seed(
        email=args.email,
        password=args.password,
        full_name=args.name,
        months=args.months,
        reset=args.reset,
    )

    if not result.get("created"):
        return 0

    print()
    print("=" * 66)
    print("  Finora demo data ready")
    print("=" * 66)
    print(f"  Email          : {result['email']}")
    print(f"  Password       : {args.password or settings.DEMO_PASSWORD}")
    print(f"  Transactions   : {result['transactions']}")
    print(f"  Budgets        : {result['budgets']}")
    print(f"  Goals          : {result['goals']}")
    print(f"  Unusual spends : {result['anomalies_flagged']} flagged")
    print(f"  Insights       : {result['insights']} generated")
    print("=" * 66)
    print("  Log in at the frontend, or try the API at /api/docs")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
