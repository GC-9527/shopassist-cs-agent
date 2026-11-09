from __future__ import annotations

from types import SimpleNamespace

import pytest

from customer_service_app.core.exceptions import NotFoundError
from customer_service_app.services.conversation_service import ConversationService


class FakeConversationRepository:
    def __init__(self, conversation):
        self.conversation = conversation
        self.messages_requested = False

    async def get_owned(self, *, tenant_id: str, user_id: str, conversation_id: str):
        if self.conversation is None:
            return None
        if (
            self.conversation.tenant_id == tenant_id
            and self.conversation.user_id == user_id
            and self.conversation.id == conversation_id
        ):
            return self.conversation
        return None

    async def recent_messages(self, *, conversation_id: str, limit: int):
        self.messages_requested = True
        return [
            SimpleNamespace(
                id="m1",
                conversation_id=conversation_id,
                role="user",
                content="订单什么时候到？",
                metadata_json={},
            )
        ]


@pytest.mark.asyncio
async def test_get_conversation_detail_checks_owner_before_reading_messages() -> None:
    service = ConversationService(session=object())  # type: ignore[arg-type]
    fake_repo = FakeConversationRepository(
        SimpleNamespace(id="c1", tenant_id="tenant-a", user_id="u1")
    )
    service._repo = fake_repo  # type: ignore[assignment]

    conversation, messages = await service.get_conversation_detail(
        tenant_id="tenant-a",
        user_id="u1",
        conversation_id="c1",
        message_limit=20,
    )

    assert conversation.id == "c1"
    assert messages[0].content == "订单什么时候到？"
    assert fake_repo.messages_requested is True


@pytest.mark.asyncio
async def test_get_conversation_detail_rejects_unowned_conversation() -> None:
    service = ConversationService(session=object())  # type: ignore[arg-type]
    fake_repo = FakeConversationRepository(
        SimpleNamespace(id="c1", tenant_id="tenant-a", user_id="u1")
    )
    service._repo = fake_repo  # type: ignore[assignment]

    with pytest.raises(NotFoundError):
        await service.get_conversation_detail(
            tenant_id="tenant-a",
            user_id="other-user",
            conversation_id="c1",
        )

    assert fake_repo.messages_requested is False



@pytest.mark.asyncio
async def test_close_conversation_cancels_active_handoff(monkeypatch) -> None:
    """客户结束会话时，排队中/已接管的人工任务要一起取消。"""

    import customer_service_app.services.conversation_service as conversation_module

    conversation = SimpleNamespace(
        id="c1",
        tenant_id="tenant-a",
        user_id="u1",
        status="active",
        service_mode="waiting_human",
        updated_at=None,
    )
    handoff = SimpleNamespace(status="waiting_assignment", resolved_at=None)

    class FakeHandoffRepo:
        def __init__(self, _session):
            self._session = _session

        async def get_active_for_conversation(self, **_kwargs):
            return handoff

    class FakeSession:
        async def flush(self):
            return None

        async def refresh(self, _obj, _attrs=None):
            return None

    monkeypatch.setattr(conversation_module, "HumanHandoffRepository", FakeHandoffRepo)
    service = ConversationService(session=FakeSession())  # type: ignore[arg-type]
    service._repo = FakeConversationRepository(conversation)  # type: ignore[assignment]

    result = await service.close_conversation(
        tenant_id="tenant-a",
        user_id="u1",
        conversation_id="c1",
    )

    assert result.status == "closed"
    assert result.service_mode == "bot"
    assert handoff.status == "cancelled"
    assert handoff.resolved_at is not None
