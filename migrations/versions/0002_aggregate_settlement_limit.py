"""Allow aggregate settlements above the per-expense cap; keep BIGINT storage."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("settlement_amount", "settlements", type_="check")
    op.create_check_constraint("settlement_amount", "settlements", "amount_minor > 0")


def downgrade():
    # Refuse downgrade if larger payments exist rather than truncating accounting history.
    op.drop_constraint("settlement_amount", "settlements", type_="check")
    op.create_check_constraint(
        "settlement_amount", "settlements", "amount_minor > 0 AND amount_minor <= 1000000000"
    )
