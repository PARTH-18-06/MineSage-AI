"""Add Q&A answers table.

Revision ID: 20260913_0003
Revises: 20260913_0002
Create Date: 2026-09-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260913_0003"
down_revision: Union[str, None] = "20260913_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_answers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_qa_answers_user_id"),
    )
    op.create_index("ix_qa_answers_user_id", "qa_answers", ["user_id"])
    op.create_index("ix_qa_answers_created_at", "qa_answers", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_qa_answers_created_at", table_name="qa_answers")
    op.drop_index("ix_qa_answers_user_id", table_name="qa_answers")
    op.drop_table("qa_answers")
