"""Category management.

System categories are seeded once and shared by every user. They are deliberately
kept in sync with the label set the ML model was trained on - if the model
predicts "Healthcare" there must be a category with that exact name to map it to.
"""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryKind, User
from app.schemas.transaction import CategoryCreate, CategoryUpdate

logger = logging.getLogger(__name__)

# name, kind, color, icon
# Colours follow the brand system: navy family for income/neutral flows, red
# family for discretionary spend, muted slate for the rest.
DEFAULT_CATEGORIES: list[tuple[str, CategoryKind, str, str]] = [
    ("Food", CategoryKind.EXPENSE, "#E63946", "UtensilsCrossed"),
    ("Shopping", CategoryKind.EXPENSE, "#F4766E", "ShoppingBag"),
    ("Transport", CategoryKind.EXPENSE, "#2C5282", "Car"),
    ("Bills", CategoryKind.EXPENSE, "#132B4F", "Receipt"),
    ("Entertainment", CategoryKind.EXPENSE, "#B4436C", "Clapperboard"),
    ("Healthcare", CategoryKind.EXPENSE, "#3A7CA5", "HeartPulse"),
    ("Education", CategoryKind.EXPENSE, "#4C6EF5", "GraduationCap"),
    ("Travel", CategoryKind.EXPENSE, "#2A9D8F", "Plane"),
    ("Rent", CategoryKind.EXPENSE, "#0B1F3A", "Home"),
    ("Salary", CategoryKind.INCOME, "#1B4965", "Banknote"),
    ("Investments", CategoryKind.BOTH, "#5C7C9A", "TrendingUp"),
    ("Other", CategoryKind.BOTH, "#64748B", "CircleDashed"),
]

DEFAULT_CATEGORY_NAMES = [name for name, _, _, _ in DEFAULT_CATEGORIES]


def ensure_system_categories(session: Session) -> list[Category]:
    """Create any missing system categories. Safe to call repeatedly."""
    existing = {
        c.name: c for c in session.scalars(select(Category).where(Category.user_id.is_(None))).all()
    }
    created: list[Category] = []
    for name, kind, color, icon in DEFAULT_CATEGORIES:
        if name in existing:
            continue
        category = Category(
            user_id=None, name=name, kind=kind, color=color, icon=icon, is_system=True
        )
        session.add(category)
        created.append(category)

    if created:
        session.flush()
        logger.info("Seeded %d system categories", len(created))
    return list(existing.values()) + created


def list_categories(session: Session, user: User) -> list[Category]:
    """System categories plus the user's own, alphabetically."""
    stmt = (
        select(Category)
        .where(or_(Category.user_id.is_(None), Category.user_id == user.id))
        .order_by(Category.is_system.desc(), Category.name)
    )
    return list(session.scalars(stmt).all())


def get_category_for_user(session: Session, user: User, category_id: str) -> Category | None:
    """Fetch a category the user is allowed to use.

    Authorisation lives here rather than in the router: a user may reference a
    system category or one they own, and nothing else.
    """
    stmt = select(Category).where(
        Category.id == category_id,
        or_(Category.user_id.is_(None), Category.user_id == user.id),
    )
    return session.scalars(stmt).first()


def get_by_name(session: Session, user: User, name: str) -> Category | None:
    stmt = select(Category).where(
        Category.name == name,
        or_(Category.user_id.is_(None), Category.user_id == user.id),
    )
    # Prefer the user's own override of a system name.
    results = list(session.scalars(stmt).all())
    if not results:
        return None
    results.sort(key=lambda c: c.user_id is None)
    return results[0]


def name_to_id_map(session: Session, user: User) -> dict[str, str]:
    return {c.name: c.id for c in list_categories(session, user)}


def create_category(session: Session, user: User, payload: CategoryCreate) -> Category:
    category = Category(
        user_id=user.id,
        name=payload.name,
        kind=payload.kind,
        color=payload.color,
        icon=payload.icon,
        is_system=False,
    )
    session.add(category)
    session.flush()
    return category


def update_category(session: Session, category: Category, payload: CategoryUpdate) -> Category:
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(category, field, value)
    session.flush()
    return category


def delete_category(session: Session, category: Category) -> None:
    """Delete a user category. Transactions fall back to uncategorised."""
    session.delete(category)
    session.flush()
