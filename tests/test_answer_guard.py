from __future__ import annotations

from customer_service_app.services.answer_guard import (
    SAFE_FALLBACK_ANSWER,
    corrective_instruction,
    guard_answer,
    has_successful_write,
    strip_decorations,
)


def _write_result(name: str = "create_refund_case", ok: bool = True) -> dict:
    return {"tool_call_id": "c1", "name": name, "ok": ok, "payload": {"ticket_id": "RS202611080001"}}


def test_claim_without_receipt_is_blocked() -> None:
    """没有写工具回执却宣称已创建工单，必须被拦截。"""

    result = guard_answer(
        answer="已成功创建退货退款工单，工单号：RS202611080001。",
        tool_results=[],
    )

    assert result.violated is True
    assert result.answer == SAFE_FALLBACK_ANSWER
    assert "completion_claim" in (result.reason or "")
    assert "RS202611080001" in result.business_ids


def test_claim_with_successful_receipt_passes() -> None:
    result = guard_answer(
        answer="已成功创建退货退款工单，工单号：RS202611080001。",
        tool_results=[_write_result()],
    )

    assert result.violated is False
    assert result.answer.startswith("已成功创建")


def test_failed_write_receipt_does_not_authorise_claim() -> None:
    result = guard_answer(
        answer="已为您提交退款申请。",
        tool_results=[_write_result(ok=False)],
    )

    assert result.violated is True


def test_read_only_receipt_does_not_authorise_claim() -> None:
    result = guard_answer(
        answer="已为您提交退款申请。",
        tool_results=[_write_result(name="query_order_status")],
    )

    assert result.violated is True


def test_plain_answer_without_claims_is_untouched() -> None:
    answer = "该订单当前为已发货状态，承运商为顺丰速运，运单号 SF1234567890。"
    receipts = [
        {
            "tool_call_id": "c2",
            "name": "query_logistics_status",
            "ok": True,
            "payload": {"tracking_number": "SF1234567890", "logistics_status": "shipped"},
        }
    ]

    result = guard_answer(answer=answer, tool_results=receipts)

    assert result.violated is False
    assert result.answer == answer


def test_business_id_alone_is_not_blocked() -> None:
    """只引用单号、没有"已完成"断言时不拦截，否则会误杀历史消息里的订单号。"""

    result = guard_answer(answer="您的工单号是 RS202611080009。", tool_results=[])

    assert result.violated is False
    assert result.answer == "您的工单号是 RS202611080009。"


def test_unsupported_ticket_id_with_claim_is_reported() -> None:
    result = guard_answer(answer="已为您生成工单 RS202611080009。", tool_results=[])

    assert result.violated is True
    assert "RS202611080009" in result.business_ids


def test_has_successful_write_requires_ok_and_write_tool() -> None:
    assert has_successful_write([_write_result()]) is True
    assert has_successful_write([_write_result(ok=False)]) is False
    assert has_successful_write([_write_result(name="query_order_status")]) is False
    assert has_successful_write(None) is False


def test_corrective_instruction_lists_real_receipts() -> None:
    text = corrective_instruction([_write_result(name="query_order_status")])
    assert "query_order_status" in text
    assert "不得声称" in text

    empty = corrective_instruction([])
    assert "没有任何工具成功回执" in empty


def test_strip_decorations_removes_emoji_and_collapses_blank_lines() -> None:
    text = "订单已发出。\n\n\n✅ 物流：顺丰\n🔹 运单号：SF123"

    cleaned = strip_decorations(text)

    assert "✅" not in cleaned
    assert "🔹" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "订单已发出。" in cleaned


def test_strip_decorations_keeps_plain_text_unchanged() -> None:
    text = "订单已发出，承运商顺丰，运单号 SF1234567890。"

    assert strip_decorations(text) == text


def test_strip_decorations_removes_retrieval_citation_markers() -> None:
    """检索片段编号只给调试看，C 端答复里要清掉。"""

    text = "外壳裂痕属于保修范围，可申请换货[4]。另见政策[1,2]和【3】。"

    cleaned = strip_decorations(text)

    assert cleaned == "外壳裂痕属于保修范围，可申请换货。另见政策和。"


def test_strip_decorations_keeps_bracketed_non_numeric_text() -> None:
    """只清纯数字角标，方括号里的正常内容不能误删。"""

    text = "请把[订单号]和[照片]发给我。"

    assert strip_decorations(text) == text


def test_strip_decorations_falls_back_when_nothing_left() -> None:
    """整段都是装饰符号时，宁可返回原文也不返回空串。"""

    assert strip_decorations("✅✅") == "✅✅"


def test_english_completion_claim_without_receipt_is_blocked() -> None:
    """英文场景同样会编造"已提交"，不能只拦中文。"""

    result = guard_answer(
        answer="I've submitted the refund case for order ORD-2026-100234.",
        tool_results=[],
    )

    assert result.violated is True
    assert result.answer == SAFE_FALLBACK_ANSWER


def test_english_claim_with_receipt_passes() -> None:
    result = guard_answer(
        answer="I've submitted the refund case.",
        tool_results=[_write_result()],
    )

    assert result.violated is False
