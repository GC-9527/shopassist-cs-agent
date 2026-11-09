"""add attachments table

Revision ID: 0011_attachments
Revises: 0010_conversation_thread
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0011_attachments"
down_revision: str | None = "0010_conversation_thread"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_attachments_tenant_id", "attachments", ["tenant_id"])
    op.create_index("ix_attachments_user_id", "attachments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_user_id", table_name="attachments")
    op.drop_index("ix_attachments_tenant_id", table_name="attachments")
    op.drop_table("attachments")
