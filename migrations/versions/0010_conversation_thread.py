"""add conversation thread id for resume

Revision ID: 0010_conversation_thread
Revises: 0009_approval_jti
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0010_conversation_thread"
down_revision: str | None = "0009_approval_jti"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("thread_id", sa.String(length=128), nullable=True))
    op.create_index("ix_conversations_thread_id", "conversations", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_thread_id", table_name="conversations")
    op.drop_column("conversations", "thread_id")
