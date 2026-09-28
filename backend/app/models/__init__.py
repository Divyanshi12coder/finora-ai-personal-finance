"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata``, which is what
Alembic autogenerate and ``database.create_all`` rely on.
"""

from app.models.ai import AIConversation, AIMessage
from app.models.budget import Budget, BudgetItem
from app.models.category import Category
from app.models.enums import (
    AnomalyStatus,
    BudgetingPreference,
    CategoryKind,
    GoalStatus,
    InsightSeverity,
    InsightType,
    MessageRole,
    ReceiptStatus,
    TransactionSource,
    TransactionType,
)
from app.models.goal import FinancialGoal, GoalContribution
from app.models.insight import Insight
from app.models.ml_prediction import MLPrediction
from app.models.receipt import Receipt, ReceiptItem
from app.models.transaction import Transaction
from app.models.user import User

__all__ = [
    "AIConversation",
    "AIMessage",
    "AnomalyStatus",
    "Budget",
    "BudgetItem",
    "BudgetingPreference",
    "Category",
    "CategoryKind",
    "FinancialGoal",
    "GoalContribution",
    "GoalStatus",
    "Insight",
    "InsightSeverity",
    "InsightType",
    "MLPrediction",
    "MessageRole",
    "Receipt",
    "ReceiptItem",
    "ReceiptStatus",
    "Transaction",
    "TransactionSource",
    "TransactionType",
    "User",
]
