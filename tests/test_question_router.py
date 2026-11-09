from __future__ import annotations

from customer_service_app.domain.schemas import ChatRequest
from customer_service_app.services.question_router import QuestionRouter


def test_policy_question_stays_on_knowledge_without_type_filtering() -> None:
    """召回阶段不再按关键词推断文档类型，只保留租户、权限这类可信范围。"""

    decision = QuestionRouter().route("七天无理由退货的条件和处理流程是什么？")

    assert decision.source == "knowledge"
    assert decision.execution_mode == "direct_answer"
    assert decision.document_types == []


def test_realtime_lookup_skips_rag_and_uses_tool() -> None:
    decision = QuestionRouter().route("帮我查询订单 202607180001 现在的物流状态")

    assert decision.source == "realtime_tool"
    assert decision.execution_mode == "direct_tool"
    assert decision.document_types == []


def test_order_policy_question_uses_hybrid_route() -> None:
    decision = QuestionRouter().route(
        "订单 202607180001 是否可以退货？",
        planner_enabled=True,
    )

    assert decision.source == "hybrid"
    assert decision.execution_mode == "rag_then_tool"


def test_policy_word_does_not_turn_stable_question_into_realtime_tool() -> None:
    decision = QuestionRouter().route("退款怎么处理？")

    assert decision.source == "knowledge"
    assert decision.execution_mode == "direct_answer"


def test_complex_request_enters_planner_when_enabled() -> None:
    request = ChatRequest(
        user_id="u1",
        question="先查询订单 202607180001，如果符合条件就申请退款，否则转人工",
    )

    decision = QuestionRouter().route(request.question, planner_enabled=True)

    assert decision.execution_mode == "planner"
    assert decision.reason == "complex_dependency_requires_planner"


def test_process_question_with_action_verb_stays_on_knowledge() -> None:
    """"创建退款前要做哪些步骤"是问流程，不是查我这一单，不能跳过检索。"""

    decision = QuestionRouter().route("真正帮用户创建退款前要做哪些步骤？")

    assert decision.source == "knowledge"
    assert decision.document_types == []


def test_handoff_condition_question_stays_on_knowledge() -> None:
    """"什么情况必须转人工"是政策问题，不是要求立刻转接。"""

    decision = QuestionRouter().route("机器客服什么情况必须转人工？")

    assert decision.source == "knowledge"
    assert decision.document_types == []


def test_personal_order_marker_forces_realtime_even_with_policy_words() -> None:
    """一旦指向"我的订单"，即便带流程类词也必须有实时工具路径。"""

    decision = QuestionRouter().route("我的订单退款流程到哪一步了？")

    assert decision.source == "hybrid"
    assert decision.execution_mode == "rag_then_tool"


def test_yes_no_eligibility_question_is_policy() -> None:
    """"可以申请…吗"是资格问题，不是要立刻查实时数据。"""

    decision = QuestionRouter().route("定制商品可以申请无理由退货吗？")

    assert decision.source == "knowledge"
    assert decision.document_types == []


def test_single_char_query_word_does_not_hijack_policy_question() -> None:
    """"催查"里的"查"不能让整句被判定成实时查询。"""

    decision = QuestionRouter().route("发货后多久没有物流轨迹可以催查？")

    assert decision.source == "knowledge"


def test_profile_lookup_routes_to_realtime_tool() -> None:
    """会员等级来自用户画像工具，不能靠知识库回答。"""

    decision = QuestionRouter().route("帮我看下我的会员等级和可用权益")

    assert decision.source == "realtime_tool"


def test_policy_question_containing_progress_words_stays_on_knowledge() -> None:
    """问"能不能查退款进度"是政策问题，不能因为字面含"退款进度"就判成实时查询。"""

    decision = QuestionRouter().route("风险复核期间，是否还可以帮忙查询用户的退款进度呢？")

    assert decision.source == "knowledge"


def test_explicit_lookup_without_order_id_still_uses_tool() -> None:
    """没有单号但明确说"帮我查一下物流"，仍应交给工具去补问。"""

    decision = QuestionRouter().route("帮我查一下物流")

    assert decision.source == "realtime_tool"
