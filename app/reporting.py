"""Read-only spending reports with explicit consumption/cash-flow semantics."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.money import format_money
from app.errors import DomainError
from app.models import Expense, Member, Settlement, Share
from app.services import date_bounds, filter_dates, require_group, require_user

DEFINITIONS = {
    "spending": "User: allocated personal shares. Group: expenses counted once. Settlements excluded.",
    "paid": "Expense amounts paid during this period; user payer only in personal reports.",
    "settlements_sent": "Recorded reimbursements sent during this period, not new spending.",
    "settlements_received": "Recorded reimbursements received during this period, not new spending.",
    "net_cash_outflow": "paid + settlements_sent - settlements_received; group internal settlements cancel.",
    "balances": "Current balances are lifetime values available from the balances endpoint, not period spending.",
}


def breakdown(values, total):
    return [
        {
            "key": str(key),
            "amount": format_money(amount),
            "percentage": f"{Decimal(amount) * 100 / total:.2f}" if total else "0.00",
        }
        for key, amount in sorted(values.items())
    ]


def summarize(
    session: Session,
    *,
    user_id: int | None = None,
    group_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    timezone: str | None = None,
):
    if user_id is not None:
        require_user(session, user_id)
        group_ids = list(
            session.scalars(
                select(Member.group_id).where(Member.user_id == user_id).order_by(Member.group_id)
            )
        )
        if group_id is not None:
            require_group(session, group_id)
            if group_id not in group_ids:
                raise DomainError(409, "user_not_member", "User does not belong to this group")
            group_ids = [group_id]
    else:
        require_group(session, group_id)
        group_ids = [group_id]
    # Shared locks in ID order make all related reads stable without blocking other reports.
    groups = [require_group(session, identifier, read=True) for identifier in sorted(group_ids)]
    timezone = timezone or (
        groups[0].timezone if group_id is not None and groups else "Asia/Kolkata"
    )
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise DomainError(422, "invalid_timezone", "Unknown IANA timezone") from exc
    low, high = date_bounds(start, end, timezone)
    expenses = list(
        session.scalars(
            filter_dates(
                select(Expense).where(Expense.group_id.in_(group_ids)),
                Expense.occurred_at,
                low,
                high,
            )
        )
    )
    expense_ids = [expense.id for expense in expenses]
    share_rows = list(session.scalars(select(Share).where(Share.expense_id.in_(expense_ids))))
    own_shares = {
        share.expense_id: share.amount_minor for share in share_rows if share.user_id == user_id
    }
    payments = list(
        session.scalars(
            filter_dates(
                select(Settlement).where(Settlement.group_id.in_(group_ids)),
                Settlement.occurred_at,
                low,
                high,
            )
        )
    )
    categories, months, by_group, by_member = (defaultdict(int) for _ in range(4))
    spending, paid, largest = 0, 0, []
    for expense in expenses:
        amount = own_shares.get(expense.id, 0) if user_id is not None else expense.amount_minor
        spending += amount
        if user_id is None or expense.paid_by == user_id:
            paid += expense.amount_minor
        # Do not include pre-join expenses as zero-value personal drill-down entries.
        if user_id is not None and expense.id not in own_shares:
            continue
        categories[expense.category] += amount
        months[expense.occurred_at.astimezone(zone).strftime("%Y-%m")] += amount
        by_group[str(expense.group_id)] += amount
        largest.append(
            {
                "expense_id": expense.id,
                "group_id": expense.group_id,
                "description": expense.description,
                "amount": format_money(amount),
                "expense_amount": format_money(expense.amount_minor),
                "_minor": amount,
            }
        )
    if user_id is None:
        for share in share_rows:
            by_member[str(share.user_id)] += share.amount_minor
    sent = sum(p.amount_minor for p in payments if user_id is None or p.from_user_id == user_id)
    received = sum(p.amount_minor for p in payments if user_id is None or p.to_user_id == user_id)
    largest.sort(key=lambda row: (-row["_minor"], row["expense_id"]))
    largest = [{key: value for key, value in row.items() if key != "_minor"} for row in largest[:5]]
    return {
        "scope": "user" if user_id is not None else "group",
        "id": user_id if user_id is not None else group_id,
        "timezone": timezone,
        "from_date": start.isoformat() if start else None,
        "to_date": end.isoformat() if end else None,
        "totals": {
            key: format_money(value)
            for key, value in {
                "spending": spending,
                "paid": paid,
                "settlements_sent": sent,
                "settlements_received": received,
                "net_cash_outflow": paid + sent - received,
            }.items()
        },
        "categories": breakdown(categories, spending),
        "months": breakdown(months, spending),
        "groups": breakdown(by_group, spending),
        "members": breakdown(by_member, spending),
        "largest_expenses": largest,
        "metric_definitions": DEFINITIONS,
    }
