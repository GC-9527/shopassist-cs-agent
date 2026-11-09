from __future__ import annotations

from collections.abc import Iterable

from customer_service_app.domain.query_rewrite import QueryRewriteResult
from customer_service_app.domain.routing import ExecutionMode, RouteDecision, RouteSource
from customer_service_app.domain.schemas import ChatRequest
from customer_service_app.services.intent_classifier import BUSINESS_ID_PATTERN, IntentClassifier

_SOURCE_BY_INTENT: dict[str, RouteSource] = {
    "knowledge": "knowledge",
    "tool": "realtime_tool",
    "hybrid": "hybrid",
}


class QuestionRouter:
    """把意图分类结果翻译成可执行的路由决策。

    路由本身不再做关键词判断，全部交给 `IntentClassifier`：
    这里只负责把意图映射成数据来源、执行模式和复杂度门禁。
    """

    _condition_words = ("如果", "然后", "同时", "再", "并且", "否则")

    def __init__(self, classifier: IntentClassifier | None = None) -> None:
        self._classifier = classifier or IntentClassifier()

    def route(
        self,
        question: str,
        *,
        resolved_question: str | None = None,
        rewrite: QueryRewriteResult | None = None,
        planner_enabled: bool = False,
    ) -> RouteDecision:
        """为当前问题生成一个可观测、可传递的路由决策。"""

        value = (resolved_question or question).strip()
        if not value:
            return RouteDecision(reason="empty_question")

        decision = self._classifier.classify(
            value,
            rewrite_intent=rewrite.intent if rewrite is not None else None,
        )
        source = _SOURCE_BY_INTENT[decision.intent]

        needs_plan = planner_enabled and self._should_plan_question(value)
        execution_mode: ExecutionMode
        if needs_plan:
            execution_mode = "planner"
        elif source == "realtime_tool":
            execution_mode = "direct_tool"
        elif source == "hybrid":
            execution_mode = "rag_then_tool"
        else:
            execution_mode = "direct_answer"

        return RouteDecision(
            source=source,
            execution_mode=execution_mode,
            # 召回阶段只带可信范围（租户/权限/生效时间），不做关键词推断的文档类型过滤。
            document_types=[],
            confidence=decision.confidence,
            reason=("complex_dependency_requires_planner" if needs_plan else decision.reason),
        )

    def should_plan(self, request: ChatRequest, *, resolved_question: str | None = None) -> bool:
        """零 Token 复杂度门禁，供 Planner 和主路由共同使用。"""

        question = (resolved_question or request.question).strip()
        return self._should_plan_question(question)

    def _should_plan_question(self, question: str) -> bool:
        """按纯文本判断复杂度，避免把改写后的长上下文重新校验成请求 DTO。"""

        if not question:
            return False
        if any(word in question for word in self._condition_words):
            return True

        intents = 0
        if self._contains_any(question, ("订单", "物流", "快递", "运单", "单号", "发货", "签收")):
            intents += 1
        if self._contains_any(question, ("退款", "退货", "退掉", "换货", "补发", "重新发")):
            intents += 1
        if self._contains_any(question, ("补偿", "赔偿", "价保", "保价", "差价", "优惠券")):
            intents += 1
        if self._contains_any(question, ("人工", "客服", "投诉", "举报", "升级处理", "12315")):
            intents += 1

        action_count = sum(
            question.count(word)
            for word in ("查询", "查看", "申请", "创建", "取消", "修改", "转", "处理")
        )
        order_ids = set(BUSINESS_ID_PATTERN.findall(question))
        # 两个业务名词并不等于两个执行步骤，例如"订单是否可以退货"
        # 仍是一次规则判断；只有出现动作、条件依赖或多实体时才启动 Planner。
        return (
            (intents >= 3 and action_count >= 1)
            or action_count >= 2
            or len(order_ids) >= 2
        )

    @staticmethod
    def _contains_any(value: str, words: Iterable[str]) -> bool:
        return any(word in value for word in words)
