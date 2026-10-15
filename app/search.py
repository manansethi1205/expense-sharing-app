"""Typed, globally ranked search over SQL entities and a finite feature directory."""

from sqlalchemy import String, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import Expense, Group, Member, User
from app.services import require_group, require_user

FEATURES = (
    (
        "users",
        "Create and list users",
        "create user|add user|list users|user details|user management|people|friends",
        "/api/v1/users",
    ),
    (
        "membership",
        "Add group members",
        "add member|add user to group|list members|membership|group members",
        "/api/v1/groups/{group_id}/members/{user_id}",
    ),
    (
        "equal-split",
        "Equal expense split",
        "equal split|shared expense|add expense|record expense",
        "/api/v1/groups/{group_id}/expenses",
    ),
    (
        "custom-split",
        "Custom unequal splits",
        "custom split|unequal split|custom allocation|unequal expense split",
        "/api/v1/groups/{group_id}/expenses",
    ),
    (
        "group-analytics",
        "Group spending analytics",
        "group report|group spending|member breakdown",
        "/api/v1/groups/{group_id}/analytics",
    ),
    (
        "drilldown",
        "Spending expense drill-down",
        "drill down|drilldown|spending details|personal expenses",
        "/api/v1/users/{user_id}/analytics/expenses",
    ),
    (
        "category-correction",
        "Correct expense category",
        "change category|manual category|correct category",
        "/api/v1/groups/{group_id}/expenses/{expense_id}/category",
    ),
    ("search", "Search everything", "search|find|feature discovery", "/api/v1/search"),
    (
        "settlements",
        "Settle balances",
        "settle|repayment|reimburse|payment|record settlement|settlement history",
        "/api/v1/groups/{group_id}/settlements",
    ),
    (
        "suggestions",
        "Settlement suggestions",
        "optimize optimal minimum transfers debts",
        "/api/v1/groups/{group_id}/settlement-suggestions",
    ),
    (
        "analytics",
        "Spending analytics",
        "reports monthly categories spent statistics",
        "/api/v1/users/{user_id}/analytics",
    ),
    (
        "expenses",
        "Expense history",
        "expense history|list expenses|expense details|transactions|dinner|records",
        "/api/v1/groups/{group_id}/expenses",
    ),
    (
        "groups",
        "Groups",
        "create group|list groups|group details|trip|friends|members",
        "/api/v1/groups",
    ),
    (
        "balances",
        "Balances",
        "user balances|group balances|owes|owed|debts|positions",
        "/api/v1/groups/{group_id}/balances",
    ),
    (
        "categories",
        "Expense categories",
        "travel food accommodation classification",
        "/api/v1/categories",
    ),
)
TYPES = {"users", "groups", "expenses", "features"}


def rank(column, query):
    lowered = func.lower(column)
    return case((lowered == query, 0), (lowered.startswith(query, autoescape=True), 1), else_=2)


def entity_query(kind, model, label, field, query, path_prefix, path_suffix=""):
    return select(
        literal(kind).label("type"),
        cast(model.id, String).label("id"),
        label.label("label"),
        literal(field).label("match_field"),
        (literal(path_prefix) + cast(model.id, String) + literal(path_suffix)).label("api_path"),
        rank(label, query).label("rank"),
        model.id.label("sort_id"),
    ).where(func.lower(label).contains(query, autoescape=True))


def search(session: Session, query: str, types: str, group_id, user_id, limit, offset):
    query = query.strip().lower()
    if not query or len(query) > 100:
        raise DomainError(
            422, "invalid_search", "Trimmed search query must contain 1-100 characters"
        )
    selected = set(types.split(","))
    if not selected or not selected <= TYPES:
        raise DomainError(
            422,
            "invalid_search_types",
            "types must be comma-separated users,groups,expenses,features",
        )
    scope = None
    if user_id is not None:
        require_user(session, user_id)
        scope = select(Member.group_id).where(Member.user_id == user_id)
    if group_id is not None:
        require_group(session, group_id)
        scope = select(Group.id).where(
            Group.id == group_id, Group.id.in_(scope) if scope is not None else literal(True)
        )
    statements = []
    if "users" in selected:
        statement = entity_query("users", User, User.name, "name", query, "/api/v1/users/")
        if scope is not None:
            peer_ids = select(Member.user_id).where(Member.group_id.in_(scope))
            # Own record is included only if no conflicting explicit group filter applies.
            own = User.id == user_id if user_id is not None and group_id is None else literal(False)
            statement = statement.where(or_(User.id.in_(peer_ids), own))
        statements.append(statement)
    if "groups" in selected:
        statement = entity_query("groups", Group, Group.name, "name", query, "/api/v1/groups/")
        statements.append(statement.where(Group.id.in_(scope)) if scope is not None else statement)
    if "expenses" in selected:
        label = Expense.description
        statement = select(
            literal("expenses").label("type"),
            cast(Expense.id, String).label("id"),
            label.label("label"),
            case(
                (func.lower(label).contains(query, autoescape=True), "description"),
                else_="category",
            ).label("match_field"),
            (
                literal("/api/v1/groups/")
                + cast(Expense.group_id, String)
                + literal("/expenses/")
                + cast(Expense.id, String)
            ).label("api_path"),
            func.least(rank(label, query), rank(Expense.category, query)).label("rank"),
            Expense.id.label("sort_id"),
        ).where(
            or_(
                func.lower(label).contains(query, autoescape=True),
                Expense.category.contains(query, autoescape=True),
            )
        )
        statements.append(
            statement.where(Expense.group_id.in_(scope)) if scope is not None else statement
        )
    candidates, total = [], 0
    if statements:
        combined = union_all(*statements).subquery()
        total = session.scalar(select(func.count()).select_from(combined))
        rows = session.execute(
            select(combined)
            .order_by(combined.c.rank, combined.c.type, combined.c.sort_id)
            .limit(offset + limit)
        ).mappings()
        candidates.extend(dict(row) for row in rows)
    if "features" in selected:
        for identifier, label, aliases, path in FEATURES:
            # Pipe separates multiword aliases; older single-word alias lists remain valid.
            words = [label.lower(), *(aliases.split("|") if "|" in aliases else aliases.split())]
            matches = [word for word in words if query in word]
            if matches:
                score = min(
                    0 if word == query else 1 if word.startswith(query) else 2 for word in matches
                )
                candidates.append(
                    {
                        "type": "features",
                        "id": identifier,
                        "label": label,
                        "match_field": "label" if query in label.lower() else "aliases",
                        "api_path": path,
                        "rank": score,
                        "sort_id": identifier,
                    }
                )
                total += 1
    candidates.sort(key=lambda row: (row["rank"], row["type"], row["sort_id"]))
    items = []
    for row in candidates[offset : offset + limit]:
        item = {key: value for key, value in row.items() if key not in {"rank", "sort_id"}}
        if item["type"] != "features":
            item["id"] = int(item["id"])
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
