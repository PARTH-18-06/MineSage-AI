"""Add report governance fields.

Revision ID: 20260914_0004
Revises: 20260913_0003
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260914_0004"
down_revision: Union[str, None] = "20260913_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


report_status = sa.Enum("draft", "in_review", "approved", "superseded", name="report_status")


def upgrade() -> None:
    report_status.create(op.get_bind(), checkfirst=True)

    op.add_column("reports", sa.Column("parent_report_id", sa.BigInteger(), nullable=True))
    op.add_column("reports", sa.Column("status", report_status, nullable=False, server_default="draft"))
    op.add_column("reports", sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("reports", sa.Column("submitted_for_review_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("submitted_for_review_by_user_id", sa.BigInteger(), nullable=True))
    op.add_column("reports", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reports", sa.Column("approved_by_user_id", sa.BigInteger(), nullable=True))
    op.add_column("reports", sa.Column("approval_note", sa.Text(), nullable=True))

    op.create_foreign_key("fk_reports_parent_report_id", "reports", "reports", ["parent_report_id"], ["id"])
    op.create_foreign_key("fk_reports_submitted_by_user_id", "reports", "users", ["submitted_for_review_by_user_id"], ["id"])
    op.create_foreign_key("fk_reports_approved_by_user_id", "reports", "users", ["approved_by_user_id"], ["id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_parent_report_id", "reports", ["parent_report_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_parent_report_id", table_name="reports")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_constraint("fk_reports_approved_by_user_id", "reports", type_="foreignkey")
    op.drop_constraint("fk_reports_submitted_by_user_id", "reports", type_="foreignkey")
    op.drop_constraint("fk_reports_parent_report_id", "reports", type_="foreignkey")

    op.drop_column("reports", "approval_note")
    op.drop_column("reports", "approved_by_user_id")
    op.drop_column("reports", "approved_at")
    op.drop_column("reports", "submitted_for_review_by_user_id")
    op.drop_column("reports", "submitted_for_review_at")
    op.drop_column("reports", "version_number")
    op.drop_column("reports", "status")
    op.drop_column("reports", "parent_report_id")

    report_status.drop(op.get_bind(), checkfirst=True)
