from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from customer_service_app.core.exceptions import AppError
from customer_service_app.services.human_support_service import HumanSupportService


def _handoff(**updates):
    values = {
        "id": "handoff-1",
        "tenant_id": "tenant-a",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "support_ticket_id": "ticket-1",
        "origin_thread_id": None,
        "status": "waiting_assignment",
        "queue_name": "general",
        "priority": "normal",
        "reason": "需要人工处理",
        "assigned_agent_id": None,
        "resolution_code": None,
        "resolution_summary": None,
        "resolution_metadata_json": {},
        "next_mode": None,
        "version": 1,
        "requested_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_assign_changes_conversation_ownership_to_human() -> None:
    service = HumanSupportService(object())  # type: ignore[arg-type]
    handoff = _handoff()
    conversation = SimpleNamespace(service_mode="waiting_human")
    service._handoffs = SimpleNamespace(  # type: ignore[assignment]
        get_owned=AsyncMock(return_value=handoff),
        flush=AsyncMock(),
    )
    service._conversations = SimpleNamespace(  # type: ignore[assignment]
        get_owned=AsyncMock(return_value=conversation),
    )

    result = await service.assign(
        tenant_id="tenant-a",
        handoff_id="handoff-1",
        agent_id="agent-1",
        expected_version=1,
    )

    assert result.status == "assigned"
    assert result.assigned_agent_id == "agent-1"
    assert conversation.service_mode == "human"
    service._handoffs.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_other_agent_cannot_reply_to_assigned_handoff() -> None:
    service = HumanSupportService(object())  # type: ignore[arg-type]
    handoff = _handoff(status="assigned", assigned_agent_id="agent-1")
    service._handoffs = SimpleNamespace(  # type: ignore[assignment]
        get_owned=AsyncMock(return_value=handoff),
    )

    with pytest.raises(AppError) as exc_info:
        await service.send_agent_message(
            tenant_id="tenant-a",
            handoff_id="handoff-1",
            agent_id="agent-2",
            content="您好",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "handoff_agent_mismatch"


@pytest.mark.asyncio
async def test_customer_session_state_reports_queue_position() -> None:
    service = HumanSupportService(object())  # type: ignore[arg-type]
    conversation = SimpleNamespace(id="conversation-1", status="active", service_mode="waiting_human")
    first = _handoff(id="handoff-0", requested_at=datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc))
    mine = _handoff(requested_at=datetime(2026, 11, 8, 10, 5, tzinfo=timezone.utc))
    service._conversations = SimpleNamespace(  # type: ignore[assignment]
        get_owned=AsyncMock(return_value=conversation),
    )
    service._handoffs = SimpleNamespace(  # type: ignore[assignment]
        get_active_for_conversation=AsyncMock(return_value=mine),
        list_queue=AsyncMock(return_value=[first, mine]),
    )

    view = await service.customer_session_state(
        tenant_id="tenant-a",
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert view.service_mode == "waiting_human"
    assert view.handoff is not None
    assert view.handoff.queue_position == 2
    assert view.handoff.status == "waiting_assignment"


@pytest.mark.asyncio
async def test_customer_session_state_has_no_position_once_assigned() -> None:
    service = HumanSupportService(object())  # type: ignore[arg-type]
    conversation = SimpleNamespace(id="conversation-1", status="active", service_mode="human")
    assigned = _handoff(status="assigned", assigned_agent_id="agent-1")
    service._conversations = SimpleNamespace(  # type: ignore[assignment]
        get_owned=AsyncMock(return_value=conversation),
    )
    service._handoffs = SimpleNamespace(  # type: ignore[assignment]
        get_active_for_conversation=AsyncMock(return_value=assigned),
        list_queue=AsyncMock(),
    )

    view = await service.customer_session_state(
        tenant_id="tenant-a",
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert view.service_mode == "human"
    assert view.handoff is not None
    assert view.handoff.assigned_agent_id == "agent-1"
    assert view.handoff.queue_position is None
