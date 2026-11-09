from __future__ import annotations

import json
import re
from dataclasses import dataclass


WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "create_refund_case",
        "create_refund_ticket",
        "create_compensation_case",
        "create_exchange_case",
        "transfer_to_human",
    }
)
"""会产生业务副作用或改变会话归属的工具。"""


_COMPLETION_CLAIMS: tuple[str, ...] = (
    "已成功创建",
    "已为您创建",
    "已为您成功创建",
    "已成功提交",
    "已为您提交",
    "已提交成功",
    "已成功发起",
    "已为您发起",
    "已为您生成",
    "已成功生成",
    "已成功办理",
    "已为您办理",
    "已为您转接",
    "已转接人工",
    "退款已原路",
    "已退款",
    # 英文场景：模型同样会声称已经提交/创建，词表必须跟着覆盖。
    "i've submitted",
    "i have submitted",
    "i've created",
    "i have created",
    "i've opened",
    "i have opened",
    "i've processed",
    "i have processed",
    "i've issued",
    "i have issued",
    "has been submitted",
    "has been created",
    "has been issued",
    "successfully submitted",
    "refund has been",
    "case has been",
)
"""断言"动作已经完成"的表达；没有工具回执时不能出现。"""


_BUSINESS_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,6}\d{8,}(?![A-Za-z0-9])")
"""形如 RS202611080001 的业务单号；没有回执却出现即为编造。"""


SAFE_FALLBACK_ANSWER = (
    "抱歉，这一步我没有真正执行成功，也没有产生任何工单或退款记录。\n\n"
    "可以再说一次你的需求，我会重新确认后再执行；也可以直接联系人工客服。"
)
"""兜底答复：宁可少说，也不能声称一个没有发生的业务结果。"""


@dataclass(frozen=True, slots=True)
class AnswerGuardResult:
    """输出校验结果。"""

    answer: str
    violated: bool
    reason: str | None = None
    claims: tuple[str, ...] = ()
    business_ids: tuple[str, ...] = ()


def has_successful_write(tool_results: list[dict] | None) -> bool:
    """判断本次运行是否真的拿到过写工具的成功回执。"""

    for item in tool_results or []:
        if item.get("ok") and item.get("name") in WRITE_TOOL_NAMES:
            return True
    return False


def guard_answer(*, answer: str, tool_results: list[dict] | None) -> AnswerGuardResult:
    """拦截"没有回执却宣称已完成"的答复。

    Prompt 里写明"不得虚构业务结果"只能降低概率，不能保证；
    这里用确定性规则兜底，避免模型凭一句话就生成退款成功、工单号等承诺。
    """

    if not answer or has_successful_write(tool_results):
        return AnswerGuardResult(answer=answer, violated=False)

    # 英文断言大小写不定，而且模型常用弯引号（I’ve）；统一归一化后再匹配。
    haystack = answer.lower().replace("’", "'").replace("‘", "'")
    claims = tuple(claim for claim in _COMPLETION_CLAIMS if claim in haystack)
    if not claims:
        # 只出现单号、没有"已完成"类断言时不算违规：订单号可能来自历史消息，
        # 单纯引用不等于宣称业务结果。
        return AnswerGuardResult(answer=answer, violated=False)

    # 工具回执里出现过的单号（运单号、工单号）是真实业务事实，不能当成编造。
    known_receipts = json.dumps(tool_results or [], ensure_ascii=False)
    business_ids = tuple(
        item for item in _BUSINESS_ID_PATTERN.findall(answer) if item not in known_receipts
    )

    reason_parts = [f"completion_claim={list(claims)}"]
    if business_ids:
        reason_parts.append(f"unsupported_business_id={list(business_ids)}")

    return AnswerGuardResult(
        answer=SAFE_FALLBACK_ANSWER,
        violated=True,
        reason="; ".join(reason_parts),
        claims=claims,
        business_ids=business_ids,
    )


def corrective_instruction(tool_results: list[dict] | None) -> str:
    """给模型的纠正指令：明确列出真实回执，禁止声称未发生的动作。"""

    names = sorted(
        {item.get("name", "") for item in (tool_results or []) if item.get("ok")}
    )
    executed = f"本次可用的工具成功回执只有：{names}。" if names else "本次没有任何工具成功回执。"
    return (
        f"{executed}你不得声称任何售后申请、退款、工单或转人工操作已经完成，"
        "也不得编造工单号。请改用：说明当前已核实的事实，并请用户确认后再提交。"
    )


_DECORATION_PATTERN = re.compile(
    "[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]"
)
"""emoji 与装饰符号。提示词已经禁止，但模型不稳定，输出前再确定性地清一遍。"""

_CITATION_PATTERN = re.compile(r"(?:\[\d{1,2}(?:\s*[,，]\s*\d{1,2})*\]|【\d{1,2}】)")
"""模型引用检索片段时留下的角标，如 `[4]`、`[1,2]`、`【3】`。

片段编号只对调试有用，C 端答复里不应该出现。
"""


def strip_decorations(text: str) -> str:
    """去掉 emoji、检索角标，收敛多余空行和连续空格。

    只做确定性的排版清理，不改写内容；清完是空的就退回原文。
    """

    if not text:
        return text
    cleaned = _DECORATION_PATTERN.sub("", text)
    cleaned = _CITATION_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip() or text
