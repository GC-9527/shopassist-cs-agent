from __future__ import annotations

import json
import re
from typing import Any

from customer_service_app.core.config import Settings
from customer_service_app.domain.memory import ShortTermContext
from customer_service_app.domain.query_rewrite import QueryRewriteResult
from customer_service_app.infrastructure.llm.base import LLMClient, LLMResponse


class QuestionRewriteService:
    """将依赖上下文的用户追问改写为可独立检索的问题。"""

    # 只收录真正的指代词/回指词。"还能""可以"这类是普通副词，
    # 出现在"耳机还能退吗"里并不表示上下文缺失，收进来会造成大面积误澄清。
    _vague_words = ("这个", "那个", "它", "刚才", "上面", "怎么弄", "那笔")
    _business_id_pattern = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]{2,8}-?)?\d{8,24}(?![A-Za-z0-9])")
    # 带这些词的问题通常是自足的：有明确业务对象，改写不会带来新信息。
    _domain_terms = (
        "订单", "物流", "快递", "包裹", "发货", "收货", "签收",
        "退货", "退款", "换货", "保修", "售后", "发票", "价保", "差价",
        "优惠", "运费", "地址", "耳机", "充电", "音箱", "数据线", "充电宝",
        "投影", "配件", "人工", "客服", "政策", "规则", "流程",
    )
    _follow_up_prefixes = ("那", "还有", "再", "然后", "另外", "顺便")
    _elliptical_suffixes = ("呢", "怎么办", "可以吗", "行吗", "怎么弄")

    def __init__(self, *, settings: Settings, llm_client: LLMClient):
        self._settings = settings
        self._llm_client = llm_client

    def should_rewrite(
        self, question: str, context: ShortTermContext | None = None
    ) -> bool:
        """零 token 门禁：只把真正依赖上下文的问题交给改写模型。

        渐进式策略：
        1. 自带业务单号 → 信息已足够，直接检索；
        2. 出现明确指代词 → 值得改写（没有上下文时 resolve 会直接澄清）；
        3. 没有历史上下文 → 没有可消解的指代，调用模型也改写不出东西；
        4. 以"那/还有/再/然后"开头，或极短且没有业务词 → 典型追问，改写；
        5. 带业务词或表达完整 → 自足，不改写。

        复杂问题不会因此被牺牲：检索质量不足时，
        `evaluate_retrieval` 会带着 retrieval_feedback 触发一次受控改写。
        """
        compact = question.strip()
        if not compact:
            return False
        if self._business_id_pattern.search(compact):
            return False
        if self._contains_vague_reference(compact):
            return True
        if context is None or not self._has_trusted_context(context):
            return False
        if compact.startswith(self._follow_up_prefixes):
            return True
        if any(term in compact for term in self._domain_terms):
            return False
        return len(compact) <= 6 or (
            len(compact) <= 12 and compact.endswith(self._elliptical_suffixes)
        )

    async def resolve(
        self,
        *,
        question: str,
        context: ShortTermContext,
        model: str,
        retrieval_feedback: dict[str, Any] | None = None,
    ) -> tuple[QueryRewriteResult, LLMResponse | None]:
        """生成结构化改写；模型失败时使用确定性规则降级。"""
        original = question.strip()
        needs_rewrite = (
            self.should_rewrite(original, context) or retrieval_feedback is not None
        )
        if not self._settings.semantic_rewrite_enabled or not needs_rewrite:
            return self._original_result(original), None

        context_payload = self._context_payload(context)
        if not self._has_trusted_context(context) and self._contains_vague_reference(original):
            return (
                QueryRewriteResult(
                    original_question=original,
                    standalone_question=original,
                    dense_query=original,
                    sparse_query=original,
                    missing_fields=["business_reference"],
                    needs_rewrite=True,
                    needs_clarification=True,
                    clarification_question="请说明您指的订单、商品或刚才的哪个处理步骤。",
                    confidence=0.0,
                    source="rule",
                    reason="vague_reference_without_context",
                ),
                None,
            )

        tool = self._rewrite_tool_schema()
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是客服检索问题改写器，只调用 submit_query_rewrite。"
                    "不得创造上下文中没有的订单号、日期、金额和业务事实。"
                    "standalone_question 用于规划和回答，dense_query 面向向量语义检索，"
                    "sparse_query 保留产品名、规则词和业务 ID 供 BM25 检索。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": original,
                        "trusted_context": context_payload,
                        "retrieval_feedback": retrieval_feedback or {},
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            response = await self._llm_client.chat(
                messages,
                model=model,
                temperature=0,
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": "submit_query_rewrite"}},
            )
            result = self._parse_response(response=response, original=original)
            self._validate_no_invented_business_ids(
                result=result,
                original=original,
                context_payload=context_payload,
            )
            if result.confidence < self._settings.semantic_rewrite_min_confidence:
                return self._rule_fallback(original, context), response
            return result, response
        except Exception:
            return self._rule_fallback(original, context), None

    def _rule_fallback(
        self, question: str, context: ShortTermContext
    ) -> QueryRewriteResult:
        hints: list[str] = []
        if context.summary and context.summary.strip():
            hints.append(context.summary.strip())
        for message in context.recent_messages[-2:]:
            if message.content.strip():
                hints.append(message.content.strip())
        if not hints:
            return self._original_result(question, source="fallback")
        standalone = f"上下文：{' 。'.join(hints[-2:])}。当前问题：{question}"
        return QueryRewriteResult(
            original_question=question,
            standalone_question=standalone,
            dense_query=standalone,
            sparse_query=question,
            needs_rewrite=True,
            confidence=0.55,
            source="fallback",
            reason="llm_rewrite_unavailable",
        )

    def _parse_response(self, *, response: LLMResponse, original: str) -> QueryRewriteResult:
        payload: dict[str, Any] | None = None
        for call in response.tool_calls:
            if call.name == "submit_query_rewrite":
                value = json.loads(call.arguments or "{}")
                if isinstance(value, dict):
                    payload = value
                    break
        if payload is None:
            value = json.loads(response.content or "{}")
            if not isinstance(value, dict):
                raise ValueError("query rewrite response must be an object")
            payload = value
        return QueryRewriteResult(original_question=original, source="llm", **payload)

    def _validate_no_invented_business_ids(
        self,
        *,
        result: QueryRewriteResult,
        original: str,
        context_payload: dict[str, Any],
    ) -> None:
        trusted_text = original + json.dumps(context_payload, ensure_ascii=False)
        trusted_ids = set(self._business_id_pattern.findall(trusted_text))
        generated_text = " ".join(
            (result.standalone_question, result.dense_query, result.sparse_query)
        )
        generated_ids = set(self._business_id_pattern.findall(generated_text))
        if not generated_ids.issubset(trusted_ids):
            raise ValueError("query rewrite invented an untrusted business id")

    @staticmethod
    def _context_payload(context: ShortTermContext) -> dict[str, Any]:
        return {
            "summary": context.summary,
            "recent_messages": [
                {"role": item.role, "content": item.content}
                for item in context.recent_messages[-4:]
            ],
            "verified_memories": [item.model_dump(mode="json") for item in context.memories[:5]],
            "pending_actions": context.pending_actions[:3],
        }

    def _contains_vague_reference(self, question: str) -> bool:
        return any(word in question for word in self._vague_words)

    @staticmethod
    def _has_trusted_context(context: ShortTermContext) -> bool:
        return bool(
            (context.summary and context.summary.strip())
            or context.recent_messages
            or context.memories
            or context.pending_actions
        )

    @staticmethod
    def _original_result(
        question: str, *, source: str = "original"
    ) -> QueryRewriteResult:
        return QueryRewriteResult(
            original_question=question,
            standalone_question=question,
            dense_query=question,
            sparse_query=question,
            needs_rewrite=False,
            source=source,  # type: ignore[arg-type]
            reason="rewrite_not_required",
        )

    @staticmethod
    def _rewrite_tool_schema() -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_query_rewrite",
                "description": "提交受控的检索问题改写结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "standalone_question": {"type": "string"},
                        "dense_query": {"type": "string"},
                        "sparse_query": {"type": "string"},
                        "intent": {"type": "string"},
                        "entities": {"type": "object"},
                        "missing_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "needs_rewrite": {"type": "boolean"},
                        "needs_clarification": {"type": "boolean"},
                        "clarification_question": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "standalone_question",
                        "dense_query",
                        "sparse_query",
                        "intent",
                        "entities",
                        "missing_fields",
                        "needs_rewrite",
                        "needs_clarification",
                        "confidence",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            },
        }
