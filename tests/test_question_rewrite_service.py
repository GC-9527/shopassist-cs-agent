from __future__ import annotations

import json

from customer_service_app.core.config import Settings
from customer_service_app.domain.memory import ShortTermContext
from customer_service_app.domain.schemas import ChatMessage
from customer_service_app.infrastructure.llm.base import LLMResponse, LLMToolCall
from customer_service_app.services.question_rewrite_service import QuestionRewriteService


class RewriteLLM:
    def __init__(self, *, standalone_question: str):
        self._standalone_question = standalone_question

    async def chat(self, messages, **kwargs):
        payload = {
            "standalone_question": self._standalone_question,
            "dense_query": self._standalone_question,
            "sparse_query": "202607180001 退货 签收 政策",
            "intent": "return_policy",
            "entities": {"order_id": "202607180001"},
            "missing_fields": [],
            "needs_rewrite": True,
            "needs_clarification": False,
            "clarification_question": None,
            "confidence": 0.92,
            "reason": "resolved_from_recent_message",
        }
        return LLMResponse(
            content="",
            tool_calls=[
                LLMToolCall(
                    id="rewrite-1",
                    name="submit_query_rewrite",
                    arguments=json.dumps(payload, ensure_ascii=False),
                )
            ],
            model="rewrite-model",
        )


async def test_vague_question_without_context_requests_clarification() -> None:
    service = QuestionRewriteService(
        settings=Settings(),
        llm_client=RewriteLLM(standalone_question="unused"),
    )

    result, response = await service.resolve(
        question="那个还能退吗？",
        context=ShortTermContext(),
        model="rewrite-model",
    )

    assert response is None
    assert result.missing_fields == ["business_reference"]
    assert result.needs_rewrite is True
    assert result.needs_clarification is True
    assert result.clarification_question


async def test_rewrite_uses_trusted_context_and_preserves_business_id() -> None:
    standalone = "订单 202607180001 已签收，是否符合退货政策？"
    service = QuestionRewriteService(
        settings=Settings(),
        llm_client=RewriteLLM(standalone_question=standalone),
    )
    context = ShortTermContext(
        recent_messages=[
            ChatMessage(role="user", content="我的订单是 202607180001"),
            ChatMessage(role="assistant", content="订单显示已签收"),
        ]
    )

    result, response = await service.resolve(
        question="那个还能退吗？",
        context=context,
        model="rewrite-model",
    )

    assert response is not None
    assert result.source == "llm"
    assert result.needs_rewrite is True
    assert result.standalone_question == standalone


async def test_rewrite_rejects_invented_business_id() -> None:
    service = QuestionRewriteService(
        settings=Settings(),
        llm_client=RewriteLLM(
            standalone_question="订单 999999999999 是否可以退货？"
        ),
    )
    context = ShortTermContext(
        recent_messages=[ChatMessage(role="user", content="订单 202607180001")]
    )

    result, _ = await service.resolve(
        question="那个还能退吗？",
        context=context,
        model="rewrite-model",
    )

    assert result.source == "fallback"
    assert "999999999999" not in result.standalone_question


class _CleanRewriteLLM:
    """返回不含虚构业务 ID 的改写结果，用于验证规则门禁不会误拦。"""

    async def chat(self, messages, **kwargs):
        payload = {
            "standalone_question": "耳机拆开卫生封签后还能直接退吗？",
            "dense_query": "耳机拆开卫生封签后还能直接退吗？",
            "sparse_query": "耳机 卫生封签 退货",
            "intent": "return_policy",
            "entities": {},
            "missing_fields": [],
            "needs_rewrite": True,
            "needs_clarification": False,
            "clarification_question": None,
            "confidence": 0.9,
            "reason": "standalone_question",
        }
        return LLMResponse(
            content="",
            tool_calls=[
                LLMToolCall(
                    id="rewrite-clean",
                    name="submit_query_rewrite",
                    arguments=json.dumps(payload, ensure_ascii=False),
                )
            ],
            model="rewrite-model",
        )


async def test_self_contained_question_skips_llm_rewrite() -> None:
    """完整问题不依赖上下文，不应为了一次改写多付一轮模型延迟。"""

    service = QuestionRewriteService(
        settings=Settings(),
        llm_client=_CleanRewriteLLM(),
    )

    result, response = await service.resolve(
        question="耳机拆开卫生封签后还能直接退吗？",
        context=ShortTermContext(),
        model="rewrite-model",
    )

    assert response is None
    assert result.needs_rewrite is False
    assert result.source == "original"


def _context_with_history() -> ShortTermContext:
    return ShortTermContext(
        recent_messages=[
            ChatMessage(role="user", content="我的订单是 202607180001"),
            ChatMessage(role="assistant", content="订单显示已签收"),
        ]
    )


def test_fixed_instructions_skip_rewrite_with_context() -> None:
    """固定指令和自足问题直接走规则/分类，不触发改写模型。"""

    service = QuestionRewriteService(settings=Settings(), llm_client=_CleanRewriteLLM())
    context = _context_with_history()

    assert service.should_rewrite("我要转人工客服", context) is False
    assert service.should_rewrite("退款多久到账", context) is False
    assert service.should_rewrite("帮我查一下订单 202607180001 的物流", context) is False
    assert service.should_rewrite("耳机还能退吗", context) is False


def test_follow_up_questions_use_llm_rewrite() -> None:
    """带指代或省略的追问才需要模型补全。"""

    service = QuestionRewriteService(settings=Settings(), llm_client=_CleanRewriteLLM())
    context = _context_with_history()

    assert service.should_rewrite("那退款呢", context) is True
    assert service.should_rewrite("那笔钱什么时候到", context) is True
    assert service.should_rewrite("这个怎么弄", context) is True


def test_short_vague_question_without_context_does_not_call_llm() -> None:
    """没有历史时连指代都无从消解，调用改写模型没有意义。"""

    service = QuestionRewriteService(settings=Settings(), llm_client=_CleanRewriteLLM())

    assert service.should_rewrite("那退款呢", ShortTermContext()) is False
