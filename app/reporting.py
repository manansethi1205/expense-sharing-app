"""SQL consumption and cash-flow reports, called within a read-only MVCC snapshot."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select
from sqlalchemy.sql.selectable import CTE

from app.domain.money import format_money
from app.errors import DomainError
from app.models import Expense, Group, Member, Settlement, Share, User
from app.services import date_bounds, filter_dates, require_group, require_user

DEFINITIONS = {
    "spending": "User: allocated personal shares. Group: expenses counted once. Settlements excluded.",
    "paid": "Expense amounts paid during this period; user payer only in personal reports.",
    "settlements_sent": "Recorded reimbursements sent during this period, not new spending.",
    "settlements_received": "Recorded reimbursements received during this period, not new spending.",
    "net_cash_outflow": "paid + settlements_sent - settlements_received; group internal settlements cancel.",
    "balances": "Current balances are lifetime values available from the balances endpoint, not period spending.",
}


@dataclass
class ReportScope:
    user_id: int | None
    group_id: int | None
    timezone: str
    low: datetime | None
    high: datetime | None
    expenses: CTE
    spending: CTE
    groups: Select


def report_scope(session, user_id=None, group_id=None, start=None, end=None, timezone=None):
    if user_id is not None:
        require_user(session, user_id)
    group = require_group(session, group_id) if group_id is not None else None
    if group and user_id is not None and session.get(Member, (group_id, user_id)) is None:
        raise DomainError(409, "user_not_member", "User does not belong to this group")
    timezone = timezone or (group.timezone if group else "Asia/Kolkata")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DomainError(422, "invalid_timezone", "Unknown IANA timezone") from exc
    low, high = date_bounds(start, end, timezone)
    groups = (
        select(Group.id).where(Group.id == group_id)
        if group_id is not None
        else select(Member.group_id).where(Member.user_id == user_id)
    )
    expenses = filter_dates(
        select(Expense).where(Expense.group_id.in_(groups)), Expense.occurred_at, low, high
    ).cte("report_expenses")
    amount = Share.amount_minor if user_id is not None else expenses.c.amount_minor
    spending = select(
        expenses.c.id.label("expense_id"),
        expenses.c.group_id,
        expenses.c.paid_by,
        expenses.c.description,
        expenses.c.category,
        expenses.c.occurred_at,
        expenses.c.amount_minor.label("expense_amount_minor"),
        amount.label("amount_minor"),
    )
    if user_id is not None:
        spending = spending.join(Share, Share.expense_id == expenses.c.id).where(
            Share.user_id == user_id
        )
    return ReportScope(
        user_id, group_id, timezone, low, high, expenses, spending.cte("report_spending"), groups
    )


def breakdown(session, statement, total):
    return [
        {
            "key": str(key),
            "label": label,
            "amount": format_money(amount),
            "percentage": f"{Decimal(amount) * 100 / total:.2f}" if total else "0.00",
        }
        for key, label, amount in session.execute(statement)
    ]


def expense_rows(session, spending, sort, limit, offset):
    order = (
        (spending.c.amount_minor.desc(), spending.c.expense_id)
        if sort == "amount_desc"
        else (spending.c.occurred_at.desc(), spending.c.expense_id.desc())
    )
    rows = session.execute(
        select(spending, Group.name.label("group_name"), User.name.label("payer_name"))
        .join(Group, Group.id == spending.c.group_id)
        .join(User, User.id == spending.c.paid_by)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    ).mappings()
    return [
        {
            "expense_id": row["expense_id"],
            "group": {"id": row["group_id"], "name": row["group_name"]},
            "paid_by": {"id": row["paid_by"], "name": row["payer_name"]},
            "description": row["description"],
            "category": row["category"],
            "occurred_at": row["occurred_at"],
            "amount": format_money(row["amount_minor"]),
            "expense_amount": format_money(row["expense_amount_minor"]),
        }
        for row in rows
    ]


def summarize(
    session: Session, *, user_id=None, group_id=None, start=None, end=None, timezone=None
):
    scope = report_scope(session, user_id, group_id, start, end, timezone)
    expenses, spending = scope.expenses, scope.spending
    total = session.scalar(select(func.coalesce(func.sum(spending.c.amount_minor), 0)))
    paid_query = select(func.coalesce(func.sum(expenses.c.amount_minor), 0))
    if user_id is not None:
        paid_query = paid_query.where(expenses.c.paid_by == user_id)
    paid = session.scalar(paid_query)
    payment_query = filter_dates(
        select(Settlement).where(Settlement.group_id.in_(scope.groups)),
        Settlement.occurred_at,
        scope.low,
        scope.high,
    ).cte("report_payments")
    sent_query = select(func.coalesce(func.sum(payment_query.c.amount_minor), 0))
    received_query = select(func.coalesce(func.sum(payment_query.c.amount_minor), 0))
    if user_id is not None:
        sent_query = sent_query.where(payment_query.c.from_user_id == user_id)
        received_query = received_query.where(payment_query.c.to_user_id == user_id)
    sent, received = session.scalar(sent_query), session.scalar(received_query)
    category = spending.c.category
    categories = breakdown(
        session,
        select(category, func.initcap(category), func.sum(spending.c.amount_minor))
        .group_by(category)
        .order_by(category),
        total,
    )
    month = func.to_char(func.timezone(scope.timezone, spending.c.occurred_at), "YYYY-MM")
    months = breakdown(
        session,
        select(month, month, func.sum(spending.c.amount_minor)).group_by(month).order_by(month),
        total,
    )
    groups = breakdown(
        session,
        select(Group.id, Group.name, func.sum(spending.c.amount_minor))
        .join(spending, spending.c.group_id == Group.id)
        .group_by(Group.id, Group.name)
        .order_by(Group.id),
        total,
    )
    members = []
    if user_id is None:
        members = breakdown(
            session,
            select(User.id, User.name, func.sum(Share.amount_minor))
            .join(Share, Share.user_id == User.id)
            .join(expenses, expenses.c.id == Share.expense_id)
            .group_by(User.id, User.name)
            .order_by(User.id),
            total,
        )
    prefix = (
        f"/api/v1/users/{user_id}/analytics/expenses"
        if user_id is not None
        else f"/api/v1/groups/{group_id}/analytics/expenses"
    )
    filters = {"timezone": scope.timezone}
    if start:
        filters["from"] = start.isoformat()
    if end:
        filters["to"] = end.isoformat()
    if group_id is not None and user_id is not None:
        filters["group_id"] = group_id
    return {
        "scope": "user" if user_id is not None else "group",
        "id": user_id if user_id is not None else group_id,
        "timezone": scope.timezone,
        "from_date": start.isoformat() if start else None,
        "to_date": end.isoformat() if end else None,
        "totals": {
            key: format_money(value)
            for key, value in {
                "spending": total,
                "paid": paid,
                "settlements_sent": sent,
                "settlements_received": received,
                "net_cash_outflow": paid + sent - received,
            }.items()
        },
        "categories": categories,
        "months": months,
        "groups": groups,
        "members": members,
        "largest_expenses": expense_rows(session, spending, "amount_desc", 5, 0),
        "drilldown_path": prefix + "?" + urlencode(filters),
        "metric_definitions": DEFINITIONS,
    }


def expense_drilldown(
    session: Session,
    *,
    user_id=None,
    group_id=None,
    start=None,
    end=None,
    timezone=None,
    category=None,
    sort="amount_desc",
    limit=20,
    offset=0,
):
    scope = report_scope(session, user_id, group_id, start, end, timezone)
    spending = scope.spending
    if category is not None:
        spending = select(spending).where(spending.c.category == category).cte("filtered_spending")
    total = session.scalar(select(func.count()).select_from(spending))
    return {
        "items": expense_rows(session, spending, sort, limit, offset),
        "total": total,
        "limit": limit,
        "offset": offset,
    }
