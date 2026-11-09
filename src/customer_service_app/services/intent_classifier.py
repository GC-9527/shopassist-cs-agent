from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentLabel = Literal["knowledge", "tool", "hybrid"]

BUSINESS_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])("
    # 跨境电商常见单号：ORD-2026-100234 / US-2026-100234
    r"[A-Z]{2,6}-\d{4}-\d{3,10}"
    # 规则编号或带前缀的单号：AFS-RET-007 / SF1234567890
    r"|[A-Z]{2,8}-[A-Z0-9-]{2,12}"
    # 纯数字单号
    r"|\d{8,24}"
    r")(?![A-Za-z0-9])"
)
"""订单号、工单号这类业务实体编号。"""


@dataclass(frozen=True, slots=True)
class IntentSignals:
    """从问题里抽出来的确定性特征，全部可解释。"""

    business_ids: tuple[str, ...] = ()
    self_reference: bool = False
    lookup_request: bool = False
    state_cue: bool = False
    policy_cue: bool = False
    action_verb: bool = False
    handoff_request: bool = False
    domains: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: IntentLabel
    confidence: float
    reason: str
    signals: IntentSignals


class IntentClassifier:
    """基于特征的意图分类器。

    早期版本用"命中业务域 + 命中动作词就算实时查询"的线性规则，问题在于：
    - 动作词（申请/创建/提交）出现在政策问题里也会触发，例如"创建退款前要做什么"；
    - 两个弱信号叠加会互相放大，例如"本人"+"换货"就把政策问句判成实时查询。

    这里改成特征加权打分：每个信号有独立权重，动作词只用于解释、不参与打分；
    只有当实时证据（单号、本人数据、明确查询请求）压过政策证据时才走工具。
    置信度取两类得分的相对差距，低置信度由调用方决定是否升级到模型分类。
    """

    # 实时证据权重
    W_BUSINESS_ID = 3.0
    W_SELF_REFERENCE = 1.2
    W_LOOKUP_REQUEST = 2.0
    W_STATE_CUE = 2.0
    W_HANDOFF_REQUEST = 3.0
    # 知识证据权重
    W_POLICY_CUE = 1.5
    W_DOMAIN = 1.0
    W_NO_ENTITY = 0.3

    _self_reference_words = (
        "我的",
        "本人",
        "我这单",
        "这个订单",
        "这笔订单",
        "这单",
        "我",
        "my ",
        "my order",
    )
    _lookup_words = (
        "帮我查", "帮我看看", "帮我查询", "查一下", "查询一下", "看一下", "看下", "查下", "查查", "查询",
        "track", "where is my", "order status", "check my order",
    )
    # 不用"到货"：它是"收到货"的子串，会把"没收到货怎么办"误判成状态查询。
    _state_words = (
        "状态", "进度", "到哪", "现在", "当前", "到账",
        "status", "tracking", "where is", "arrive", "delivered",
    )
    _policy_words = (
        "规则",
        "政策",
        "条件",
        "期限",
        "流程",
        "步骤",
        "什么情况",
        "哪些",
        "什么",
        "怎么做",
        "怎么办",
        "如何",
        "为什么",
        "规定",
        "标准",
        "要求",
        "能不能",
        "可不可以",
        "能否",
        "是否",
        "多久",
        "多长时间",
        "哪天",
        "吗",
        "policy",
        "how long",
        "warranty",
        "eligible",
        "allowed",
        "can i",
        "do you",
    )
    _action_words = ("申请", "创建", "提交", "取消", "修改", "转人工")
    # "转人工"可能是问规则（什么情况必须转人工），也可能是在下指令（我要转人工）。
    _handoff_words = (
        "转人工", "人工客服", "真人客服", "找人工", "接人工", "人工坐席",
        "talk to a human", "human agent", "real person", "speak to a person",
        "transfer me", "customer service agent", "live agent",
    )
    _handoff_request_markers = (
        "我要", "我想", "帮我", "麻烦", "直接", "请", "给我", "现在",
        "i want", "i need", "i'd like", "please", "can i", "let me",
    )
    _domain_words = (
        "订单",
        "物流",
        "快递",
        "运单",
        "退款",
        "退货",
        "换货",
        "工单",
        "投诉",
        "人工",
        "客服",
        "会员",
        "权益",
        "等级",
        # 英文表述：语料是中文，但用户会用英文问同一件事。
        "order",
        "refund",
        "return",
        "exchange",
        "logistics",
        "tracking",
        "status",
        "membership",
        "benefit",
        "delivery",
        "shipment",
    )

    def classify(self, question: str, *, rewrite_intent: str | None = None) -> IntentDecision:
        signals = self._extract(question, rewrite_intent=rewrite_intent)
        tool_score, knowledge_score = self._score(signals)
        asks_policy = signals.policy_cue or bool(
            rewrite_intent and ("policy" in rewrite_intent.lower() or "faq" in rewrite_intent.lower())
        )

        if signals.handoff_request:
            # 明确要求人工是用户主动发起的动作，必须真的去建工单，不能被政策问法带偏。
            intent: IntentLabel = "tool"
        elif tool_score <= knowledge_score:
            intent = "knowledge"
        elif asks_policy:
            intent = "hybrid"
        else:
            intent = "tool"

        return IntentDecision(
            intent=intent,
            confidence=self._confidence(tool_score=tool_score, knowledge_score=knowledge_score),
            reason=self._reason(intent, signals),
            signals=signals,
        )

    # ---------- 特征抽取 ----------

    def _extract(self, question: str, *, rewrite_intent: str | None) -> IntentSignals:
        text = question.strip().lower()
        raw = question.strip()
        rewrite_policy = bool(
            rewrite_intent and ("policy" in rewrite_intent.lower() or "faq" in rewrite_intent.lower())
        )
        return IntentSignals(
            business_ids=tuple(BUSINESS_ID_PATTERN.findall(raw)),
            self_reference=self._contains(text, self._self_reference_words),
            lookup_request=self._contains(text, self._lookup_words),
            state_cue=self._contains(text, self._state_words),
            policy_cue=rewrite_policy or self._contains(text, self._policy_words),
            action_verb=self._contains(text, self._action_words),
            handoff_request=self._is_handoff_request(raw),
            domains=frozenset(word for word in self._domain_words if word in text),
        )

    def _is_handoff_request(self, question: str) -> bool:
        """区分"我要转人工"和"什么情况必须转人工"。"""

        text = question.strip()
        lowered = text.lower()
        if not any(word in lowered for word in self._handoff_words):
            return False
        if any(marker in lowered for marker in self._handoff_request_markers):
            return True
        # 极短句"转人工"本身就是指令。
        return len(text) <= 6

    @staticmethod
    def _contains(text: str, words: tuple[str, ...]) -> bool:
        return any(word in text for word in words)

    # ---------- 打分 ----------

    def _score(self, signals: IntentSignals) -> tuple[float, float]:
        has_domain = bool(signals.domains)
        tool_score = 0.0
        if signals.business_ids:
            tool_score += self.W_BUSINESS_ID
        if signals.lookup_request and has_domain:
            tool_score += self.W_LOOKUP_REQUEST
        # 状态词只和本人指向配合才算证据："我的退款到账了吗"。
        # 否则"是否还可以查询退款进度"这种政策问句会被状态词带偏。
        if signals.state_cue and signals.self_reference and has_domain:
            tool_score += self.W_STATE_CUE

        knowledge_score = 0.0
        if signals.policy_cue:
            knowledge_score += self.W_POLICY_CUE
        # 已经指向本人数据时，业务域不再重复计入知识证据。
        if has_domain and not signals.self_reference:
            knowledge_score += self.W_DOMAIN
        if not signals.business_ids:
            knowledge_score += self.W_NO_ENTITY

        return round(tool_score, 3), round(knowledge_score, 3)

    @staticmethod
    def _confidence(*, tool_score: float, knowledge_score: float) -> float:
        """两类得分的相对差距。差距小说明规则无法判定，值得升级到模型。"""

        total = tool_score + knowledge_score
        if total <= 0:
            return 0.0
        return round(abs(tool_score - knowledge_score) / total, 3)

    @staticmethod
    def _reason(intent: IntentLabel, signals: IntentSignals) -> str:
        if signals.handoff_request:
            return "explicit_handoff_request"
        if intent == "hybrid":
            return "policy_evidence_and_realtime_fact_required"
        if intent == "tool":
            if signals.business_ids:
                return "business_entity_requires_tool"
            if signals.lookup_request:
                return "explicit_lookup_requires_tool"
            return "self_scoped_business_fact_requires_tool"
        return "stable_policy_can_use_rag" if signals.policy_cue else "stable_knowledge_can_use_rag"
