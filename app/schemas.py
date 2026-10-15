from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Category = Literal["travel", "food", "accommodation", "activities", "shopping", "other"]
Mode = Literal["direct", "simplified"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Money = Annotated[
    Decimal, Field(ge=0, le=10_000_000, max_digits=10, decimal_places=2, allow_inf_nan=False)
]
PositiveMoney = Annotated[
    Decimal, Field(gt=0, le=10_000_000, max_digits=10, decimal_places=2, allow_inf_nan=False)
]
PositiveId = Annotated[int, Field(gt=0, strict=True)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorContent(BaseModel):
    code: str
    message: str
    details: list[dict] = Field(default_factory=list)


class ErrorRead(BaseModel):
    error: ErrorContent


class UserCreate(Input):
    name: Name


class GroupCreate(Input):
    name: Name
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class Split(Input):
    user_id: PositiveId
    amount: Money


class ExpenseBase(Input):
    paid_by: PositiveId
    amount: PositiveMoney
    description: Description
    category: Category | None = None
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def aware_timestamp(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timestamp must include a timezone offset")
        return value


class EqualExpense(ExpenseBase):
    split_type: Literal["equal"] = "equal"


class CustomExpense(ExpenseBase):
    split_type: Literal["custom"]
    splits: list[Split] = Field(min_length=1)


def default_equal(value):
    return {"split_type": "equal", **value} if isinstance(value, dict) else value


ExpenseCreate = Annotated[
    EqualExpense | CustomExpense, Field(discriminator="split_type"), BeforeValidator(default_equal)
]


class SettlementCreate(Input):
    from_user_id: PositiveId
    to_user_id: PositiveId
    amount: PositiveMoney
    mode: Mode
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    occurred_at: datetime | None = None
    _aware_timestamp = field_validator("occurred_at")(ExpenseBase.aware_timestamp.__func__)


class CategoryUpdate(Input):
    category: Category


class UserLabel(BaseModel):
    id: int
    name: str


class UserRead(UserLabel):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime


class GroupRead(BaseModel):
    id: int
    name: str
    currency: str
    timezone: str
    created_at: datetime
    member_count: int


class MemberRead(UserLabel):
    group_id: int
    joined_at: datetime


class Page[T](BaseModel):
    items: list[T]
    limit: int
    offset: int
    total: int


class ShareRead(BaseModel):
    user: UserLabel
    amount: str


class ExpenseRead(BaseModel):
    id: int
    group_id: int
    paid_by: UserLabel
    amount: str
    currency: str = "INR"
    description: str
    split_type: str
    category: str
    category_source: str
    category_rule: str | None
    occurred_at: datetime
    created_at: datetime
    shares: list[ShareRead]


class SettlementRead(BaseModel):
    id: int
    group_id: int
    from_user: UserLabel
    to_user: UserLabel
    amount: str
    currency: str = "INR"
    mode: str
    note: str | None
    occurred_at: datetime
    created_at: datetime


class TransferRead(BaseModel):
    from_user: UserLabel
    to_user: UserLabel
    amount: str


class PositionRead(BaseModel):
    user: UserLabel
    amount: str


class BalanceRead(BaseModel):
    group_id: int
    currency: str = "INR"
    view: Literal["direct", "net"]
    is_settled: bool
    balances: list[TransferRead] | list[PositionRead]
    explanation: str | None = None


class PlanRead(BaseModel):
    group_id: int
    currency: str = "INR"
    mode: Mode
    strategy: Literal["exact", "greedy", "direct"]
    objective: Literal["minimum_transactions", "preserve_original_debts"]
    optimality_guaranteed: bool
    transaction_count: int
    transfers: list[TransferRead]
    explanation: str


class UserBalancesRead(BaseModel):
    user_id: int
    groups: list[BalanceRead]


class SearchHit(BaseModel):
    type: Literal["users", "groups", "expenses", "features"]
    id: int | str
    label: str
    match_field: str
    api_path: str


class Breakdown(BaseModel):
    key: str
    amount: str
    percentage: str


class Totals(BaseModel):
    spending: str
    paid: str
    settlements_sent: str
    settlements_received: str
    net_cash_outflow: str


class AnalyticsRead(BaseModel):
    scope: Literal["user", "group"]
    id: int
    currency: str = "INR"
    timezone: str
    from_date: str | None
    to_date: str | None
    totals: Totals
    categories: list[Breakdown]
    months: list[Breakdown]
    groups: list[Breakdown]
    members: list[Breakdown]
    largest_expenses: list[dict]
    metric_definitions: dict[str, str]
