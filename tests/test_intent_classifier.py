from __future__ import annotations

import pytest

from customer_service_app.services.intent_classifier import IntentClassifier


@pytest.fixture(scope="module")
def classifier() -> IntentClassifier:
    return IntentClassifier()


@pytest.mark.parametrize(
    "question",
    [
        "我的订单 202606040001 现在到哪了？",
        "帮我查一下订单 202606040001 的状态",
        "我的order 202606040001 now 到哪里了？",
        "麻烦check一下order 202606040001的status～",
    ],
)
def test_business_entity_forces_tool(classifier: IntentClassifier, question: str) -> None:
    """带具体单号就是实时业务查询，与提问语言无关。"""

    decision = classifier.classify(question)

    assert decision.intent in {"tool", "hybrid"}
    assert decision.signals.business_ids


def test_action_verb_alone_does_not_imply_tool(classifier: IntentClassifier) -> None:
    """提到"创建/申请"是在描述流程，不是要求执行。"""

    decision = classifier.classify("创建退款前要做什么？")

    assert decision.intent == "knowledge"
    assert decision.signals.action_verb is True


def test_self_reference_plus_policy_cue_stays_knowledge(classifier: IntentClassifier) -> None:
    """"本人 + 换货"这类弱信号叠加不应压过政策证据。"""

    decision = classifier.classify(
        "办理退换货服务是否必须由用户提交本人身份证件及银行卡取款密码？"
    )

    assert decision.intent == "knowledge"


def test_self_reference_with_state_cue_uses_tool(classifier: IntentClassifier) -> None:
    """指向本人且带当前状态，才说明要查实时数据。"""

    decision = classifier.classify("我现在的会员权益都有啥呀？")

    assert decision.intent == "tool"


def test_lookup_request_without_entity_uses_tool(classifier: IntentClassifier) -> None:
    decision = classifier.classify("帮我查一下物流")

    assert decision.intent == "tool"


def test_english_domain_terms_are_recognised(classifier: IntentClassifier) -> None:
    """语料是中文，但用户会用英文问同一件事。"""

    decision = classifier.classify("check my order 202606040001 status please")

    assert decision.intent in {"tool", "hybrid"}


def test_policy_cue_with_live_evidence_becomes_hybrid(classifier: IntentClassifier) -> None:
    decision = classifier.classify("订单 202607180001 是否可以退货？")

    assert decision.intent == "hybrid"


def test_plain_policy_question_is_knowledge(classifier: IntentClassifier) -> None:
    decision = classifier.classify("七天无理由退货从哪天开始算？")

    assert decision.intent == "knowledge"
    assert decision.confidence > 0.5


def test_borderline_question_has_low_confidence(classifier: IntentClassifier) -> None:
    """规则判定不出结果时，置信度必须低，方便上层升级到模型分类。"""

    strong = classifier.classify("我的订单 202606040001 现在到哪了？")
    borderline = classifier.classify("我刚续费了年卡，想确认下现在能享受哪些会员权益？")

    assert strong.confidence > borderline.confidence


def test_signals_are_exposed_for_observability(classifier: IntentClassifier) -> None:
    decision = classifier.classify("帮我查一下订单 202606040001 的状态")

    assert decision.signals.lookup_request is True
    assert "订单" in decision.signals.domains
    assert decision.reason == "business_entity_requires_tool"
