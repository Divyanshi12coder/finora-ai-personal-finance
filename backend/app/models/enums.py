"""Enumerations shared by models and schemas.

All SQLAlchemy ``Enum`` columns are declared with ``native_enum=False`` so they
are stored as VARCHAR with a CHECK constraint. That keeps PostgreSQL and the
SQLite dev fallback behaving identically and makes adding a value a plain
migration instead of an ALTER TYPE dance.
"""

from __future__ import annotations

from enum import Enum


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class CategoryKind(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    BOTH = "both"


class TransactionSource(str, Enum):
    MANUAL = "manual"
    RECEIPT = "receipt"
    SEED = "seed"
    IMPORT = "import"


class AnomalyStatus(str, Enum):
    NONE = "none"
    FLAGGED = "flagged"
    CONFIRMED = "confirmed"
    EXPECTED = "expected"
    IGNORED = "ignored"


class ReceiptStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    CONFIRMED = "confirmed"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    PAUSED = "paused"
    ARCHIVED = "archived"


class InsightType(str, Enum):
    SPENDING_INCREASE = "spending_increase"
    SPENDING_DECREASE = "spending_decrease"
    BUDGET_RISK = "budget_risk"
    BUDGET_EXCEEDED = "budget_exceeded"
    ANOMALY = "anomaly"
    RECURRING_EXPENSE = "recurring_expense"
    SAVINGS_OPPORTUNITY = "savings_opportunity"
    SAVINGS_RATE = "savings_rate"
    GOAL_PROGRESS = "goal_progress"
    CASHFLOW_RISK = "cashflow_risk"
    NEW_MERCHANT = "new_merchant"


class InsightSeverity(str, Enum):
    POSITIVE = "positive"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class BudgetingPreference(str, Enum):
    STRICT = "strict"
    BALANCED = "balanced"
    FLEXIBLE = "flexible"
