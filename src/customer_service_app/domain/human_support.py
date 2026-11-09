from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


HumanHandoffStatus = Literal[
    "waiting_assignment",
    "assigned",
    "in_service",
    "resolution_submitted",
    "resolved",
    "cancelled",
]


class HumanHandoffView(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    conversation_id: str
    support_ticket_id: str | None = None
    origin_thread_id: str | None = None
    status: HumanHandoffStatus
    queue_name: str
    priority: str
    reason: str
    assigned_agent_id: str | None = None
    resolution_code: str | None = None
    resolution_summary: str | None = None
    next_mode: str | None = None
    version: int
    requested_at: str
    updated_at: str


class ConversationSessionView(BaseModel):
    """C 端看到的会话状态。

    前端按 `service_mode` 显示不同的状态条：Bot 正常应答、排队等待人工、
    人工接管中、坐席已提交结果待确认，以及会话已结束。
    """

    conversation_id: str
    status: str
    service_mode: str
    handoff: "HandoffStateView | None" = None


class HandoffStateView(BaseModel):
    """转人工任务的对外可见状态，不含内部处理细节。"""

    id: str
    status: HumanHandoffStatus
    queue_name: str
    priority: str
    reason: str
    assigned_agent_id: str | None = None
    queue_position: int | None = None
    resolution_summary: str | None = None
    updated_at: str | None = None


class HumanAssignmentRequest(BaseModel):
    tenant_id: str
    agent_id: str = Field(min_length=1, max_length=64)
    expected_version: int | None = None


class HumanMessageRequest(BaseModel):
    tenant_id: str
    agent_id: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=8000)


class HumanResolutionRequest(BaseModel):
    tenant_id: str
    agent_id: str = Field(min_length=1, max_length=64)
    resolution_code: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=8000)
    next_mode: Literal["resume_bot", "close_conversation"] = "resume_bot"
    metadata: dict[str, Any] = Field(default_factory=dict)


class HumanResolutionConfirmationRequest(BaseModel):
    tenant_id: str
    operator_id: str = Field(min_length=1, max_length=64)
    expected_version: int | None = None


ConversationSessionView.model_rebuild()
