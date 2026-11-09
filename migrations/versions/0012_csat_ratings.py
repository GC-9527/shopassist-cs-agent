"""add csat ratings table

Revision ID: 0012_csat_ratings
Revises: 0011_attachments
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0012_csat_ratings"
down_revision: str | None = "0011_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "csat_ratings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id", "conversation_id", name="uq_csat_conversation"
        ),
    )
    op.create_index("ix_csat_ratings_tenant_id", "csat_ratings", ["tenant_id"])
    op.create_index("ix_csat_ratings_user_id", "csat_ratings", ["user_id"])
    op.create_index("ix_csat_ratings_conversation_id", "csat_ratings", ["conversation_id"])
    op.create_index("idx_csat_tenant_created", "csat_ratings", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_csat_tenant_created", table_name="csat_ratings")
    op.drop_index("ix_csat_ratings_conversation_id", table_name="csat_ratings")
    op.drop_index("ix_csat_ratings_user_id", table_name="csat_ratings")
    op.drop_index("ix_csat_ratings_tenant_id", table_name="csat_ratings")
    op.drop_table("csat_ratings")
