"""Seed synthetic data atomically. Re-running does not duplicate the demo group."""

import json

from sqlalchemy import select

from app.config import get_settings
from app.db import session_factory
from app.domain.categories import classify_description
from app.domain.splits import equal_shares
from app.models import Expense, Group, Member, Share, User

DEMO_GROUP = "Goa Trip (demo)"


def seed():
    engine, sessions = session_factory(get_settings().database_url)
    try:
        with sessions.begin() as session:
            # Prevent concurrent seed invocations from creating duplicate demo groups.
            from sqlalchemy import text

            session.execute(text("SELECT pg_advisory_xact_lock(528741)"))
            existing = session.scalar(select(Group).where(Group.name == DEMO_GROUP))
            if existing:
                return {"group_id": existing.id, "created": False}
            users = [User(name=name) for name in ("Mohit", "Rahul", "Ankit")]
            group = Group(name=DEMO_GROUP)
            session.add_all([*users, group])
            session.flush()
            session.add_all(Member(group_id=group.id, user_id=user.id) for user in users)
            session.flush()
            for description, amount, payer in (
                ("Dinner", 120000, users[0]),
                ("Taxi to beach", 60000, users[1]),
                ("Hotel stay", 300000, users[0]),
            ):
                category = classify_description(description)
                expense = Expense(
                    group_id=group.id,
                    paid_by=payer.id,
                    amount_minor=amount,
                    description=description,
                    split_type="equal",
                    category=category.category,
                    category_source=category.source,
                    category_rule=category.rule,
                )
                session.add(expense)
                session.flush()
                session.add_all(
                    Share(
                        expense_id=expense.id, group_id=group.id, user_id=user, amount_minor=amount
                    )
                    for user, amount in equal_shares(amount, [user.id for user in users]).items()
                )
            return {
                "group_id": group.id,
                "users": [{"id": user.id, "name": user.name} for user in users],
                "created": True,
            }
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(seed(), indent=2))
