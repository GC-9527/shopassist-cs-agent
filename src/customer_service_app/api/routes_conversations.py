from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.api.dependencies import require_roles
from customer_service_app.core.config import Settings, get_settings
from customer_service_app.core.exceptions import NotFoundError
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.core.time_utils import as_utc
from customer_service_app.domain.csat import CsatRequest, CsatView
from customer_service_app.domain.human_support import ConversationSessionView
from customer_service_app.domain.schemas import (
    ConversationCreateRequest,
    ConversationMessageView,
    ConversationView,
)
from customer_service_app.infrastructure.db.session import get_db_session
from customer_service_app.services.conversation_service import ConversationService
from customer_service_app.services.csat_service import CsatService
from customer_service_app.services.human_support_service import HumanSupportService


router = APIRouter(prefix="/conversations", tags=["conversations"])
"""会话管理路由组，最终路径是 `/api/v1/conversations`。"""


@router.post("", response_model=ConversationView)
async def create_conversation(
    request: ConversationCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> ConversationView:
    """创建新会话。

    这里没有直接操作数据库，而是交给 `ConversationService`，
    保持 API 层薄、业务层清晰。
    """
    service = ConversationService(session)
    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
    )

    conversation = await service.ensure_conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=None,
        first_question=request.title,
    )

    await session.commit()

    return ConversationView(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        service_mode=conversation.service_mode,
    )


@router.get("", response_model=list[ConversationView])
async def list_conversations(
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> list[ConversationView]:
    """查询某个用户的会话列表。"""
    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    conversations = await ConversationService(session).list_conversations(
        tenant_id=tenant_id,
        user_id=user_id,
    )

    return [
        ConversationView(
            id=item.id,
            tenant_id=item.tenant_id,
            user_id=item.user_id,
            title=item.title,
            status=item.status,
            service_mode=item.service_mode,
        )
        for item in conversations
    ]


@router.get("/latest", response_model=ConversationView | None)
async def latest_conversation(
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> ConversationView | None:
    """返回可恢复的最近一条会话；超出恢复窗口或已结束时返回 null。"""

    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    since = datetime.now(timezone.utc) - timedelta(hours=settings.chat_resume_window_hours)
    conversation = await ConversationService(session).latest_resumable(
        tenant_id=tenant_id,
        user_id=user_id,
        since=since,
    )
    if conversation is None:
        return None
    return ConversationView(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        service_mode=conversation.service_mode,
        thread_id=conversation.thread_id,
        updated_at=as_utc(conversation.updated_at),
    )


@router.post("/{conversation_id}/close", response_model=ConversationView)
async def close_conversation(
    conversation_id: str,
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> ConversationView:
    """结束会话：标记 closed，之后不再自动恢复。"""

    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    service = ConversationService(session)
    conversation = await service.close_conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    await session.commit()
    return ConversationView(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        service_mode=conversation.service_mode,
        thread_id=conversation.thread_id,
        updated_at=as_utc(conversation.updated_at),
    )


@router.post("/{conversation_id}/csat", response_model=CsatView)
async def submit_csat(
    conversation_id: str,
    request: CsatRequest,
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> CsatView:
    """结束会话后提交满意度评价。"""

    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    view = await CsatService(session).submit(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        request=request,
    )
    await session.commit()
    return view


@router.get("/{conversation_id}/session", response_model=ConversationSessionView)
async def conversation_session_state(
    conversation_id: str,
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> ConversationSessionView:
    """C 端轮询用：当前会话归谁处理、排队到第几位、是否已结束。"""

    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    return await HumanSupportService(session).customer_session_state(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )


@router.get("/{conversation_id}/csat", response_model=CsatView | None)
async def get_csat(
    conversation_id: str,
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> CsatView | None:
    """读取已提交的评价，没有则返回 null。"""

    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    return await CsatService(session).get(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageView])
async def list_conversation_messages(
    conversation_id: str,
    tenant_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> list[ConversationMessageView]:
    """Restore one owned conversation in the customer-service workspace."""

    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    service = ConversationService(session)
    conversation = await service.ensure_conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        first_question="",
        allow_closed=True,
    )

    if conversation is None:
        raise NotFoundError("Conversation not found")

    messages = await service.list_message_records(conversation_id=conversation_id)

    return [
        ConversationMessageView(
            id=item.id,
            role=item.role,
            content=item.content,
            metadata=item.metadata_json,
            created_at=as_utc(item.created_at).isoformat() if item.created_at else None,
        )
        for item in messages
        if item.role in {"system", "user", "assistant", "tool"}
    ]
