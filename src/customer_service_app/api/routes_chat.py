from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.api.dependencies import get_customer_service_agent, require_roles
from customer_service_app.core.config import Settings, get_settings
from customer_service_app.core.exceptions import PermissionDeniedError
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.domain.schemas import ChatRequest, ChatResponse, MessageAttachment
from customer_service_app.infrastructure.db.models import Attachment
from customer_service_app.infrastructure.db.session import get_db_session
from customer_service_app.services.customer_service_agent import CustomerServiceAgent


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=128,
    ),
    agent: CustomerServiceAgent = Depends(get_customer_service_agent),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> ChatResponse:
    """返回完整回答和执行轨迹。"""
    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
    )
    attachments = await _verify_attachments(
        session,
        request.attachments,
        tenant_id=tenant_id,
        user_id=user_id,
        api_prefix=settings.api_prefix,
    )
    secured_request = _secure_request(
        request,
        tenant_id=tenant_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        attachments=attachments,
    )
    return await agent.answer(secured_request)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=128,
    ),
    agent: CustomerServiceAgent = Depends(get_customer_service_agent),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> StreamingResponse:
    """流式聊天接口，返回 text/event-stream。"""
    tenant_id, user_id = authorize_identity(
        principal,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
    )
    attachments = await _verify_attachments(
        session,
        request.attachments,
        tenant_id=tenant_id,
        user_id=user_id,
        api_prefix=settings.api_prefix,
    )
    secured_request = _secure_request(
        request,
        tenant_id=tenant_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        attachments=attachments,
    )
    return StreamingResponse(
        agent.stream_answer(secured_request),
        media_type="text/event-stream",
    )


def _secure_request(
    request: ChatRequest,
    *,
    tenant_id: str,
    user_id: str,
    idempotency_key: str | None,
    attachments: list[MessageAttachment],
) -> ChatRequest:
    """统一写入可信身份和客户端幂等键，避免两个入口处理不一致。"""
    metadata = dict(request.metadata)
    if idempotency_key:
        metadata["idempotency_key"] = idempotency_key.strip()
    return request.model_copy(
        update={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "metadata": metadata,
            "attachments": attachments,
        }
    )


async def _verify_attachments(
    session: AsyncSession,
    attachments: list[MessageAttachment],
    *,
    tenant_id: str,
    user_id: str,
    api_prefix: str,
) -> list[MessageAttachment]:
    """确认附件属于当前用户，并把地址改写成服务端路径。

    附件 ID 由客户端提交，不校验就可以把别人的凭证图挂到自己的消息上；
    地址也不信任客户端，统一由服务端生成。
    """

    if not attachments:
        return []

    ids = {item.id for item in attachments}
    result = await session.execute(
        select(Attachment.id).where(
            Attachment.id.in_(ids),
            Attachment.tenant_id == tenant_id,
            Attachment.user_id == user_id,
        )
    )
    owned = set(result.scalars().all())
    if owned != ids:
        raise PermissionDeniedError("附件不存在或无权使用")

    return [
        item.model_copy(update={"url": f"{api_prefix}/uploads/{item.id}"})
        for item in attachments
    ]
