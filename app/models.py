from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="user_name_nonblank"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="group_name_nonblank"),
        CheckConstraint("currency = 'INR'", name="group_inr_only"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Member(Base):
    __tablename__ = "group_members"
    __table_args__ = (Index("ix_member_user_group", "user_id", "group_id"),)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id", "paid_by"], ["group_members.group_id", "group_members.user_id"]
        ),
        UniqueConstraint("id", "group_id", name="uq_expense_id_group"),
        CheckConstraint("amount_minor > 0 AND amount_minor <= 1000000000", name="expense_amount"),
        CheckConstraint("split_type IN ('equal', 'custom')", name="expense_split_type"),
        CheckConstraint(
            "category IN ('travel','food','accommodation','activities','shopping','other')",
            name="expense_category",
        ),
        CheckConstraint(
            "category_source IN ('manual','rule','fallback')", name="expense_category_source"
        ),
        Index("ix_expense_group_date", "group_id", "occurred_at", "id"),
        Index("ix_expense_group_payer", "group_id", "paid_by"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    paid_by: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(String(500))
    split_type: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(20))
    category_source: Mapped[str] = mapped_column(String(10))
    category_rule: Mapped[str | None] = mapped_column(String(200))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Share(Base):
    __tablename__ = "expense_shares"
    __table_args__ = (
        ForeignKeyConstraint(["expense_id", "group_id"], ["expenses.id", "expenses.group_id"]),
        ForeignKeyConstraint(
            ["group_id", "user_id"], ["group_members.group_id", "group_members.user_id"]
        ),
        CheckConstraint("amount_minor >= 0", name="share_nonnegative"),
        Index("ix_share_user_expense", "user_id", "expense_id"),
    )
    expense_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["group_id", "from_user_id"], ["group_members.group_id", "group_members.user_id"]
        ),
        ForeignKeyConstraint(
            ["group_id", "to_user_id"], ["group_members.group_id", "group_members.user_id"]
        ),
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 1000000000", name="settlement_amount"
        ),
        CheckConstraint("from_user_id <> to_user_id", name="settlement_distinct_users"),
        CheckConstraint("mode IN ('direct','simplified')", name="settlement_mode"),
        Index("ix_settlement_group_date", "group_id", "occurred_at", "id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    from_user_id: Mapped[int] = mapped_column(Integer)
    to_user_id: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    mode: Mapped[str] = mapped_column(String(12))
    note: Mapped[str | None] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
