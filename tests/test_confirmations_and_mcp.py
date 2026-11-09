from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from customer_service_app.core.config import Settings
from customer_service_app.infrastructure.mcp.client import _normalize_tool_result
from customer_service_app.infrastructure.db.repositories import PendingActionRepository
from customer_service_app.services.confirmation_service import ConfirmationService


def test_pending_action_expiration_uses_configured_ttl() -> None:
    service = ConfirmationService(
        session=object(),  # type: ignore[arg-type]
        settings=Settings(pending_action_ttl_seconds=10),
    )

    expired_action = SimpleNamespace(
        created_at=datetime.now(timezone.utc) - timedelta(seconds=11)
    )
    fresh_action = SimpleNamespace(
        created_at=datetime.now(timezone.utc) - timedelta(seconds=3)
    )

    assert service._is_expired(expired_action) is True  # type: ignore[arg-type]
    assert service._is_expired(fresh_action) is False  # type: ignore[arg-type]


def test_pending_action_expiration_accepts_naive_datetime_from_mysql() -> None:
    """MySQL 读回的 DATETIME 没有时区，不能因此抛 TypeError 让审批 500。"""

    service = ConfirmationService(
        session=object(),  # type: ignore[arg-type]
        settings=Settings(pending_action_ttl_seconds=10),
    )

    naive_expired = SimpleNamespace(
        expire_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=11)
    )
    naive_fresh = SimpleNamespace(
        expire_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=60)
    )

    assert service._is_expired(naive_expired) is True  # type: ignore[arg-type]
    assert service._is_expired(naive_fresh) is False  # type: ignore[arg-type]


def test_mcp_tool_result_prefers_structured_content() -> None:
    result = SimpleNamespace(structured_content={"ticket_id": "t001", "status": "open"})

    assert _normalize_tool_result(result) == {"ticket_id": "t001", "status": "open"}


def test_mcp_tool_result_parses_text_json() -> None:
    result = SimpleNamespace(
        structured_content=None,
        structuredContent=None,
        content=[SimpleNamespace(text='{"found": true, "order_id": "o001"}')],
    )

    assert _normalize_tool_result(result) == {"found": True, "order_id": "o001"}


@pytest.mark.asyncio
async def test_pending_action_claim_allows_only_one_request() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(rowcount=1)
    repo = PendingActionRepository(session)

    claimed = await repo.claim_for_approval(
        tenant_id="tenant-a",
        user_id="user-a",
        action_id="action-a",
        now=datetime.now(timezone.utc),
    )

    assert claimed is True
    session.execute.assert_awaited_once()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_pending_action_claim_rejects_losing_request() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(rowcount=0)
    repo = PendingActionRepository(session)

    claimed = await repo.claim_for_approval(
        tenant_id="tenant-a",
        user_id="user-a",
        action_id="action-a",
        now=datetime.now(timezone.utc),
    )

    assert claimed is False
    session.flush.assert_awaited_once()


def test_confirmation_prompt_follows_tenant_language() -> None:
    """中文租户不应看到英文确认提示，英文租户保持英文。"""

    tool = SimpleNamespace(action_type="refund")
    arguments = {"order_id": "202605150002", "reason": "不想要了"}

    zh = ConfirmationService._build_confirmation_prompt(
        tenant_id="zh", tool=tool, arguments=arguments  # type: ignore[arg-type]
    )
    en = ConfirmationService._build_confirmation_prompt(
        tenant_id="us", tool=tool, arguments=arguments  # type: ignore[arg-type]
    )

    assert "请确认是否提交退款申请" in zh
    assert "订单号：202605150002" in zh
    assert "Please confirm your refund request" in en
    assert "Order: 202605150002" in en
