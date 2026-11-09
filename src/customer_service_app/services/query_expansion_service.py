from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from customer_service_app.infrastructure.llm.base import LLMClient


@dataclass(frozen=True, slots=True)
class ExpandedQuery:
    """一次检索用的查询扩展结果。"""

    original: str
    expansions: tuple[str, ...]
    source: str

    @property
    def all_queries(self) -> tuple[str, ...]:
        return (self.original, *self.expansions)


class QueryExpansionService:
    """把口语化问题改写成知识库更可能使用的说法。

    失败样本的共同形态是：用户说"顾客/呈现/告知"，文档写"用户/展示/说明"。
    BM25 与关键词通道依赖词重叠，措辞一换就断锚；稠密向量也没能把这层桥起来。
    这里在检索前补一次同义改写，作为**额外的召回路**，而不是替换原查询——
    改写错了也不会把原来的正确结果挤掉。
    """

    _SYSTEM_PROMPT = (
        "你是电商客服知识库的检索助手。用户的问题偏口语，知识库文档用的是规范说法。\n"
        "请把问题改写成 {count} 条检索用查询，尽量换成文档里更可能出现的词，"
        "包括同义词、书面语和业务术语。\n"
        "硬性要求：\n"
        "- 不改变问题的含义，不新增原问题没有的要点；\n"
        "- 不得虚构订单号、金额、日期、规则编号；\n"
        "- 不要回答问题，不要解释；\n"
        "- 只输出一个 JSON 数组，正好 {count} 个字符串。\n"
        "示例：\n"
        "问题：售后的方案在正式执行之前要公示哪些内容？\n"
        "输出：[\"售后方案执行前需向用户展示哪些信息\", \"退款方案执行前 展示 订单号 退款原因 回寄责任\"]"
    )

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model: str,
        max_queries: int = 2,
        temperature: float = 0.2,
    ) -> None:
        self._llm_client = llm_client
        self._model = model
        self._max_queries = max(1, max_queries)
        self._temperature = temperature

    async def expand(self, question: str) -> ExpandedQuery:
        """生成扩展查询；任何失败都退回只用原查询，不影响检索主链路。"""

        original = question.strip()
        if not original:
            return ExpandedQuery(original=question, expansions=(), source="empty")

        messages = [
            {"role": "system", "content": self._SYSTEM_PROMPT.format(count=self._max_queries)},
            {"role": "user", "content": original},
        ]
        try:
            response = await self._llm_client.chat(
                messages,
                model=self._model,
                temperature=self._temperature,
            )
            expansions = self._parse(response.content or "", original)
        except Exception as exc:  # noqa: BLE001 - 扩展是增强项，失败只记录
            logging.warning("query expansion degraded: %s", exc)
            return ExpandedQuery(original=question, expansions=(), source="error")

        return ExpandedQuery(
            original=original,
            expansions=expansions,
            source="llm" if expansions else "empty",
        )

    def _parse(self, raw: str, original: str) -> tuple[str, ...]:
        text = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        parsed: object
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 模型偶尔会在数组前后带说明文字，只在这种情况下退一步截取数组。
            start, end = text.find("["), text.rfind("]")
            if start < 0 or end <= start:
                return ()
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return ()
        if not isinstance(parsed, list):
            return ()

        expansions: list[str] = []
        for item in parsed:
            if not isinstance(item, str):
                continue
            value = item.strip()
            # 丢掉空串、原句和重复项，避免把无效查询送进检索。
            if value and value != original and value not in expansions:
                expansions.append(value)
        return tuple(expansions[: self._max_queries])
