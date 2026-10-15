"""Application operations. Mutations own one transaction; reads never commit."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.domain.balances import Transfer, direct_balances, net_positions
from app.domain.categories import Classification, classify_description
from app.domain.money import format_money, to_minor
from app.domain.settlements import Plan, suggest_transfers, validate_settlement
from app.domain.splits import equal_shares, validate_custom_shares
from app.errors import DomainError
from app.models import Expense, Group, Member, Settlement, Share, User, utcnow
from app.schemas import CustomExpense, ExpenseBase, SettlementCreate


def require_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise DomainError(404, "user_not_found", "User does not exist")
    return user


def require_group(session: Session, group_id: int, *, lock=False, read=False) -> Group:
    statement = select(Group).where(Group.id == group_id)
    if lock or read:
        statement = statement.with_for_update(read=read)
    group = session.scalar(statement)
    if group is None:
        raise DomainError(404, "group_not_found", "Group does not exist")
    return group


def page(session: Session, statement, limit: int, offset: int, mapper=lambda value: value):
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = [mapper(value) for value in session.scalars(statement.limit(limit).offset(offset))]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def create_user(session: Session, name: str):
    with session.begin():
        user = User(name=name)
        session.add(user)
        session.flush()
    return user


def group_dict(session: Session, group: Group, count=None):
    if count is None:
        count = session.scalar(
            select(func.count()).select_from(Member).where(Member.group_id == group.id)
        )
    return {
        key: getattr(group, key) for key in ("id", "name", "currency", "timezone", "created_at")
    } | {"member_count": count}


def group_page(session: Session, statement, limit: int, offset: int):
    result = page(session, statement, limit, offset)
    ids = [group.id for group in result["items"]]
    counts = dict(
        session.execute(
            select(Member.group_id, func.count())
            .where(Member.group_id.in_(ids))
            .group_by(Member.group_id)
        ).all()
    )
    result["items"] = [
        group_dict(session, group, counts.get(group.id, 0)) for group in result["items"]
    ]
    return result


def create_group(session: Session, payload):
    with session.begin():
        group = Group(**payload.model_dump())
        session.add(group)
        session.flush()
        result = group_dict(session, group)
    return result


def add_member(session: Session, group_id: int, user_id: int):
    with session.begin():
        require_group(session, group_id, lock=True)
        user = require_user(session, user_id)
        member = session.get(Member, (group_id, user_id))
        created = member is None
        if created:
            member = Member(group_id=group_id, user_id=user_id)
            session.add(member)
            session.flush()
        result = {
            "id": user.id,
            "name": user.name,
            "group_id": group_id,
            "joined_at": member.joined_at,
        }
    return result, created


def member_labels(session: Session, group_id: int) -> dict[int, dict]:
    return {
        user.id: {"id": user.id, "name": user.name}
        for user in session.scalars(
            select(User)
            .join(Member, Member.user_id == User.id)
            .where(Member.group_id == group_id)
            .order_by(User.id)
        )
    }


def expense_dict(session: Session, expense: Expense, *, labels=None, shares=None):
    if labels is not None:
        return {
            **{
                key: getattr(expense, key)
                for key in (
                    "id",
                    "group_id",
                    "description",
                    "split_type",
                    "category",
                    "category_source",
                    "category_rule",
                    "occurred_at",
                    "created_at",
                )
            },
            "paid_by": labels[expense.paid_by],
            "amount": format_money(expense.amount_minor),
            "shares": [
                {"user": labels[share.user_id], "amount": format_money(share.amount_minor)}
                for share in shares
            ],
        }
    payer = require_user(session, expense.paid_by)
    rows = session.execute(
        select(Share, User)
        .join(User, Share.user_id == User.id)
        .where(Share.expense_id == expense.id)
        .order_by(User.id)
    ).all()
    return {
        **{
            key: getattr(expense, key)
            for key in (
                "id",
                "group_id",
                "description",
                "split_type",
                "category",
                "category_source",
                "category_rule",
                "occurred_at",
                "created_at",
            )
        },
        "paid_by": {"id": payer.id, "name": payer.name},
        "amount": format_money(expense.amount_minor),
        "shares": [
            {"user": {"id": user.id, "name": user.name}, "amount": format_money(share.amount_minor)}
            for share, user in rows
        ],
    }


def expense_page(session: Session, group_id: int, statement, limit: int, offset: int):
    result = page(session, statement, limit, offset)
    expenses = result["items"]
    labels = member_labels(session, group_id)
    shares = {expense.id: [] for expense in expenses}
    for share in session.scalars(
        select(Share).where(Share.expense_id.in_(shares)).order_by(Share.user_id)
    ):
        shares[share.expense_id].append(share)
    result["items"] = [
        expense_dict(session, expense, labels=labels, shares=shares[expense.id])
        for expense in expenses
    ]
    return result


def require_expense(session: Session, group_id: int, expense_id: int):
    require_group(session, group_id)
    expense = session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.group_id == group_id)
    )
    if expense is None:
        raise DomainError(404, "expense_not_found", "Expense does not exist in this group")
    return expense


def create_expense(session: Session, group_id: int, payload: ExpenseBase):
    with session.begin():
        require_group(session, group_id, lock=True)
        members = list(member_labels(session, group_id))
        if payload.paid_by not in members:
            raise DomainError(409, "payer_not_member", "Payer must belong to a nonempty group")
        amount = to_minor(payload.amount)
        try:
            shares = (
                validate_custom_shares(
                    amount, members, [(s.user_id, to_minor(s.amount)) for s in payload.splits]
                )
                if isinstance(payload, CustomExpense)
                else equal_shares(amount, members)
            )
        except ValueError as exc:
            raise DomainError(422, "invalid_splits", str(exc)) from exc
        category = (
            Classification(payload.category, "manual", None)
            if payload.category
            else classify_description(payload.description)
        )
        expense = Expense(
            group_id=group_id,
            paid_by=payload.paid_by,
            amount_minor=amount,
            description=payload.description,
            split_type=payload.split_type,
            category=category.category,
            category_source=category.source,
            category_rule=category.rule,
            occurred_at=payload.occurred_at or utcnow(),
        )
        session.add(expense)
        session.flush()
        session.add_all(
            Share(expense_id=expense.id, group_id=group_id, user_id=user, amount_minor=value)
            for user, value in shares.items()
        )
        session.flush()
        result = expense_dict(session, expense)
    return result


def correct_category(session: Session, group_id: int, expense_id: int, category: str):
    with session.begin():
        require_group(session, group_id, lock=True)
        expense = require_expense(session, group_id, expense_id)
        expense.category, expense.category_source, expense.category_rule = category, "manual", None
        session.flush()
        result = expense_dict(session, expense)
    return result


def load_ledger(session: Session, group_id: int):
    """One statement observes shares and settlements from one READ COMMITTED snapshot."""
    from sqlalchemy import literal

    obligations = (
        select(
            Share.user_id.label("sender"),
            Expense.paid_by.label("receiver"),
            Share.amount_minor.label("amount"),
            literal("expense").label("kind"),
        )
        .join(Expense, Expense.id == Share.expense_id)
        .where(Expense.group_id == group_id, Share.user_id != Expense.paid_by)
    )
    payments = select(
        Settlement.from_user_id,
        Settlement.to_user_id,
        Settlement.amount_minor,
        literal("settlement"),
    ).where(Settlement.group_id == group_id)
    debts, settled = [], []
    for sender, receiver, amount, kind in session.execute(union_all(obligations, payments)):
        (debts if kind == "expense" else settled).append(Transfer(sender, receiver, amount))
    return debts, settled


def balance_data(session: Session, group_id: int):
    # The read lock also keeps labels/membership consistent with the ledger until session close.
    require_group(session, group_id, read=True)
    labels = member_labels(session, group_id)
    debts, settled = load_ledger(session, group_id)
    return labels, net_positions(list(labels), debts, settled), direct_balances(debts, settled)


def transfer_dict(transfer: Transfer, labels: dict):
    return {
        "from_user": labels[transfer.from_user_id],
        "to_user": labels[transfer.to_user_id],
        "amount": format_money(transfer.amount_minor),
    }


def get_balances(session: Session, group_id: int, view="direct"):
    labels, positions, direct = balance_data(session, group_id)
    is_settled = not any(positions.values())
    return {
        "group_id": group_id,
        "view": view,
        "is_settled": is_settled,
        "balances": [transfer_dict(t, labels) for t in direct]
        if view == "direct"
        else [
            {"user": labels[user], "amount": format_money(amount)}
            for user, amount in positions.items()
        ],
        "explanation": "Net positions are cleared; remaining direct edges describe a historical zero-net cycle, not additional required payments."
        if is_settled and direct and view == "direct"
        else None,
    }


def preview_settlements(session: Session, group_id: int, mode: str, threshold: int):
    labels, positions, direct = balance_data(session, group_id)
    # A net-settled group never needs extra payments just to clear a historical cycle.
    plan = (
        Plan(direct if any(positions.values()) else [], "direct", "preserve_original_debts", False)
        if mode == "direct"
        else suggest_transfers(positions, threshold)
    )
    return {
        "group_id": group_id,
        "mode": mode,
        "strategy": plan.strategy,
        "objective": plan.objective,
        "optimality_guaranteed": plan.optimality_guaranteed,
        "transaction_count": len(plan.transfers),
        "transfers": [transfer_dict(t, labels) for t in plan.transfers],
        "explanation": "Advisory only; record externally completed payments separately. Exact plans minimize transfer count; direct mode preserves pairwise obligations; greedy results have no minimum-count guarantee.",
    }


def settlement_dict(session: Session, settlement: Settlement, *, labels=None):
    if labels is None:
        sender, receiver = (
            require_user(session, settlement.from_user_id),
            require_user(session, settlement.to_user_id),
        )
        labels = {user.id: {"id": user.id, "name": user.name} for user in (sender, receiver)}
    return {
        **{
            key: getattr(settlement, key)
            for key in ("id", "group_id", "mode", "note", "occurred_at", "created_at")
        },
        "from_user": labels[settlement.from_user_id],
        "to_user": labels[settlement.to_user_id],
        "amount": format_money(settlement.amount_minor),
    }


def record_settlement(session: Session, group_id: int, payload: SettlementCreate):
    with session.begin():
        require_group(session, group_id, lock=True)
        labels = member_labels(session, group_id)
        debts, settled = load_ledger(session, group_id)
        positions, direct = (
            net_positions(list(labels), debts, settled),
            direct_balances(debts, settled),
        )
        amount = to_minor(payload.amount)
        try:
            if not any(positions.values()):
                raise ValueError("Group is already net-settled")
            validate_settlement(
                payload.mode, payload.from_user_id, payload.to_user_id, amount, positions, direct
            )
        except ValueError as exc:
            raise DomainError(409, "invalid_settlement", str(exc)) from exc
        settlement = Settlement(
            **payload.model_dump(exclude={"amount", "occurred_at"}),
            group_id=group_id,
            amount_minor=amount,
            occurred_at=payload.occurred_at or utcnow(),
        )
        session.add(settlement)
        session.flush()
        result = settlement_dict(session, settlement)
    return result


def date_bounds(start: date | None, end: date | None, timezone: str):
    if start and end and start >= end:
        raise DomainError(422, "invalid_date_range", "from must be earlier than to (exclusive)")
    zone = ZoneInfo(timezone)
    return tuple(
        datetime.combine(value, time.min, zone).astimezone(UTC) if value else None
        for value in (start, end)
    )


def filter_dates(statement, column, start, end):
    if start:
        statement = statement.where(column >= start)
    if end:
        statement = statement.where(column < end)
    return statement
