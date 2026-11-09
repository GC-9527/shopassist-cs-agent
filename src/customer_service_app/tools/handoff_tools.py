from __future__ import annotations

from typing import Any

from customer_service_app.services.tool_registry import ToolExecutionContext, ToolSpec


async def transfer_to_human_case(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    """Create a human handoff case after confirmation when needed."""

    return await context.business_gateway.transfer_to_human(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        reason=str(arguments["reason"]),
        priority=str(arguments.get("priority", "high")),
        approval_token=context.approval_token,
        origin_thread_id=context.langgraph_thread_id,
        idempotency_key=context.confirmation_id,
    )


HUMAN_HANDOFF_CASE_TOOL = ToolSpec(
    name="transfer_to_human",
    description="当用户明确要求人工客服、投诉升级、情绪强烈或自动处理风险过高时创建人工客服工单。",
    parameters={
        "type": "object",
        "properties": {
            "reason": {"type": "string", "minLength": 1, "description": "转人工原因"},
            "priority": {
                "type": "string",
                "enum": ["normal", "high", "urgent"],
                "description": "人工处理优先级",
            },
        },
        "required": ["reason"],
        "additionalProperties": False,
    },
    handler=transfer_to_human_case,
    read_only=False,
    # 用户主动要求转人工属于低风险、可逆动作，再弹一次确认只会增加摩擦。
    # 真正需要确认的是退款、补偿这类资金动作。
    requires_confirmation=False,
    risk_level="low",
    action_type="tool",
)
