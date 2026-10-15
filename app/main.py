from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import reporting, services
from app import search as search_service
from app.config import Settings, get_settings
from app.db import get_session, session_factory
from app.domain.categories import CATEGORIES, PHRASES, RULES_VERSION, WORDS
from app.errors import DomainError, register_handlers
from app.models import Expense, Group, Member, Settlement, User
from app.schemas import (
    AnalyticsRead,
    BalanceRead,
    Category,
    CategoryUpdate,
    ErrorRead,
    ExpenseCreate,
    ExpenseRead,
    GroupCreate,
    GroupRead,
    MemberRead,
    Mode,
    Page,
    PlanRead,
    SearchHit,
    SettlementCreate,
    SettlementRead,
    UserBalancesRead,
    UserCreate,
    UserRead,
)

DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]
Start = Annotated[date | None, Query(alias="from", description="Inclusive local calendar date")]
End = Annotated[date | None, Query(alias="to", description="Exclusive local calendar date")]
router = APIRouter(
    prefix="/api/v1", responses={status: {"model": ErrorRead} for status in (404, 409, 422)}
)


@router.post("/users", response_model=UserRead, status_code=201, tags=["Users"])
def create_user(payload: UserCreate, session: DB):
    return services.create_user(session, payload.name)


@router.get("/users", response_model=Page[UserRead], tags=["Users"])
def list_users(session: DB, q: str | None = None, limit: Limit = 20, offset: Offset = 0):
    statement = select(User).order_by(User.id)
    if q:
        statement = statement.where(func.lower(User.name).contains(q.lower(), autoescape=True))
    return services.page(session, statement, limit, offset)


@router.get("/users/{user_id}", response_model=UserRead, tags=["Users"])
def get_user(user_id: int, session: DB):
    return services.require_user(session, user_id)


@router.post("/groups", response_model=GroupRead, status_code=201, tags=["Groups"])
def create_group(payload: GroupCreate, session: DB):
    return services.create_group(session, payload)


@router.get("/groups", response_model=Page[GroupRead], tags=["Groups"])
def list_groups(
    session: DB,
    user_id: int | None = None,
    q: str | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    statement = select(Group).order_by(Group.id)
    if user_id is not None:
        services.require_user(session, user_id)
        statement = statement.join(Member).where(Member.user_id == user_id)
    if q:
        statement = statement.where(func.lower(Group.name).contains(q.lower(), autoescape=True))
    return services.group_page(session, statement, limit, offset)


@router.get("/groups/{group_id}", response_model=GroupRead, tags=["Groups"])
def get_group(group_id: int, session: DB):
    return services.group_dict(session, services.require_group(session, group_id))


@router.put(
    "/groups/{group_id}/members/{user_id}",
    response_model=MemberRead,
    tags=["Groups"],
    responses={201: {"model": MemberRead, "description": "Membership created"}},
)
def add_member(group_id: int, user_id: int, session: DB, response: Response):
    result, created = services.add_member(session, group_id, user_id)
    response.status_code = 201 if created else 200
    return result


@router.get("/groups/{group_id}/members", response_model=Page[MemberRead], tags=["Groups"])
def list_members(group_id: int, session: DB, limit: Limit = 20, offset: Offset = 0):
    services.require_group(session, group_id)
    total = session.scalar(
        select(func.count()).select_from(Member).where(Member.group_id == group_id)
    )
    rows = session.execute(
        select(Member, User)
        .join(User, User.id == Member.user_id)
        .where(Member.group_id == group_id)
        .order_by(User.id)
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {"id": u.id, "name": u.name, "group_id": group_id, "joined_at": m.joined_at}
            for m, u in rows
        ],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.post(
    "/groups/{group_id}/expenses", response_model=ExpenseRead, status_code=201, tags=["Expenses"]
)
def create_expense(group_id: int, payload: ExpenseCreate, session: DB):
    return services.create_expense(session, group_id, payload)


@router.get("/groups/{group_id}/expenses", response_model=Page[ExpenseRead], tags=["Expenses"])
def list_expenses(
    group_id: int,
    session: DB,
    q: str | None = None,
    category: Category | None = None,
    paid_by: int | None = None,
    start: Start = None,
    end: End = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    group = services.require_group(session, group_id, read=True)
    statement = (
        select(Expense)
        .where(Expense.group_id == group_id)
        .order_by(Expense.occurred_at.desc(), Expense.id.desc())
    )
    if q:
        statement = statement.where(
            func.lower(Expense.description).contains(q.lower(), autoescape=True)
        )
    if category:
        statement = statement.where(Expense.category == category)
    if paid_by is not None:
        statement = statement.where(Expense.paid_by == paid_by)
    low, high = services.date_bounds(start, end, group.timezone)
    return services.expense_page(
        session,
        group_id,
        services.filter_dates(statement, Expense.occurred_at, low, high),
        limit,
        offset,
    )


@router.get(
    "/groups/{group_id}/expenses/{expense_id}", response_model=ExpenseRead, tags=["Expenses"]
)
def get_expense(group_id: int, expense_id: int, session: DB):
    services.require_group(session, group_id, read=True)
    return services.expense_dict(session, services.require_expense(session, group_id, expense_id))


@router.patch(
    "/groups/{group_id}/expenses/{expense_id}/category",
    response_model=ExpenseRead,
    tags=["Expenses"],
)
def correct_category(group_id: int, expense_id: int, payload: CategoryUpdate, session: DB):
    return services.correct_category(session, group_id, expense_id, payload.category)


@router.get("/groups/{group_id}/balances", response_model=BalanceRead, tags=["Balances"])
def group_balances(group_id: int, session: DB, view: Literal["direct", "net"] = "direct"):
    return services.get_balances(session, group_id, view)


@router.get("/users/{user_id}/balances", response_model=UserBalancesRead, tags=["Balances"])
def user_balances(user_id: int, session: DB, view: Literal["direct", "net"] = "net"):
    services.require_user(session, user_id)
    group_ids = list(
        session.scalars(
            select(Member.group_id).where(Member.user_id == user_id).order_by(Member.group_id)
        )
    )
    groups = [services.get_balances(session, group_id, view) for group_id in group_ids]
    for group in groups:
        group["balances"] = [
            balance
            for balance in group["balances"]
            if (
                balance["user"]["id"] == user_id
                if view == "net"
                else user_id in (balance["from_user"]["id"], balance["to_user"]["id"])
            )
        ]
    return {"user_id": user_id, "groups": groups}


@router.get(
    "/groups/{group_id}/settlement-suggestions", response_model=PlanRead, tags=["Settlements"]
)
def settlement_suggestions(group_id: int, session: DB, request: Request, mode: Mode = "simplified"):
    return services.preview_settlements(
        session, group_id, mode, request.app.state.settings.exact_settlement_threshold
    )


@router.post(
    "/groups/{group_id}/settlements",
    response_model=SettlementRead,
    status_code=201,
    tags=["Settlements"],
)
def record_settlement(group_id: int, payload: SettlementCreate, session: DB):
    return services.record_settlement(session, group_id, payload)


@router.get(
    "/groups/{group_id}/settlements", response_model=Page[SettlementRead], tags=["Settlements"]
)
def list_settlements(
    group_id: int,
    session: DB,
    start: Start = None,
    end: End = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    group = services.require_group(session, group_id, read=True)
    statement = (
        select(Settlement)
        .where(Settlement.group_id == group_id)
        .order_by(Settlement.occurred_at.desc(), Settlement.id.desc())
    )
    low, high = services.date_bounds(start, end, group.timezone)
    labels = services.member_labels(session, group_id)
    return services.page(
        session,
        services.filter_dates(statement, Settlement.occurred_at, low, high),
        limit,
        offset,
        lambda payment: services.settlement_dict(session, payment, labels=labels),
    )


@router.get("/users/{user_id}/analytics", response_model=AnalyticsRead, tags=["Analytics"])
def user_analytics(
    user_id: int,
    session: DB,
    start: Start = None,
    end: End = None,
    group_id: int | None = None,
    timezone: str | None = None,
    bucket: Literal["month"] = "month",
):
    return reporting.summarize(
        session, user_id=user_id, group_id=group_id, start=start, end=end, timezone=timezone
    )


@router.get("/groups/{group_id}/analytics", response_model=AnalyticsRead, tags=["Analytics"])
def group_analytics(
    group_id: int,
    session: DB,
    start: Start = None,
    end: End = None,
    timezone: str | None = None,
    bucket: Literal["month"] = "month",
):
    return reporting.summarize(session, group_id=group_id, start=start, end=end, timezone=timezone)


@router.get("/search", response_model=Page[SearchHit], tags=["Search"])
def search(
    session: DB,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    types: str = "users,groups,expenses,features",
    group_id: int | None = None,
    user_id: int | None = None,
    limit: Limit = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
):
    return search_service.search(session, q, types, group_id, user_id, limit, offset)


@router.get("/categories", tags=["Categories"])
def categories():
    return {
        "categories": CATEGORIES,
        "rules_version": RULES_VERSION,
        "keywords": {key: sorted(values) for key, values in WORDS.items()},
        "phrase_overrides": PHRASES,
        "explanation": "Manual choice wins; phrase rules precede whole-word rules. Ambiguous or unmatched descriptions use other. Old expenses keep their saved classification.",
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine, sessions = session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        engine.dispose()

    application = FastAPI(
        title="Expense Sharing API",
        version="0.1.0",
        lifespan=lifespan,
        description="Assignment backend: exact INR splits, searchable history, consumption analytics and bounded optimal settlements. Demo has no authentication; use synthetic data. Monetary values are decimal strings; equal split is default.",
    )
    application.state.settings, application.state.engine, application.state.sessions = (
        settings,
        engine,
        sessions,
    )
    register_handlers(application)
    application.include_router(router)

    @application.get("/health/live", tags=["Health"])
    def live():
        return {"status": "ok"}

    @application.get("/health/ready", tags=["Health"], responses={503: {"model": ErrorRead}})
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise DomainError(503, "database_unavailable", "Database is not ready") from exc
        return {"status": "ready"}

    return application


app = create_app()
