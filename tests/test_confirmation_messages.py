from __future__ import annotations

from customer_service_app.workflows.nodes import CustomerServiceGraphNodes


def test_confirmation_completion_is_customer_facing() -> None:
    answer = CustomerServiceGraphNodes._confirmation_completion(
        tenant_id="zh",
        action_type="refund",
        result={"ticket_id": "T-123"},
    )

    assert "退款申请已提交" in answer
    assert "T-123" in answer
    assert "工具" not in answer
    assert "LangGraph" not in answer


def test_confirmation_completion_uses_english_for_us_tenant() -> None:
    answer = CustomerServiceGraphNodes._confirmation_completion(
        tenant_id="us",
        action_type="exchange",
        result={"ticket_id": "T-456"},
    )

    assert "exchange request has been submitted" in answer
    assert "T-456" in answer


def test_handoff_completion_does_not_mention_internal_state() -> None:
    answer = CustomerServiceGraphNodes._confirmation_completion(
        tenant_id="zh",
        action_type="handoff",
        result={"handoff_id": "H-1"},
    )

    assert "转接人工客服" in answer
    assert "handoff" not in answer.lower()
