from __future__ import annotations

import json

import pytest

from customer_service_app.domain.schemas import KnowledgeChunk
from customer_service_app.infrastructure.llm.base import LLMResponse
from customer_service_app.services.query_expansion_service import QueryExpansionService


class _FakeLLM:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content or ""
        self.error = error
        self.calls: list[list[dict]] = []

    async def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return LLMResponse(content=self.content, tool_calls=[], model="fake")


def _service(llm: _FakeLLM, *, max_queries: int = 2) -> QueryExpansionService:
    return QueryExpansionService(llm_client=llm, model="fake", max_queries=max_queries)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_expansion_parses_json_array() -> None:
    llm = _FakeLLM(json.dumps(["售后方案执行前要展示哪些信息", "退款方案确认 展示 内容"], ensure_ascii=False))

    result = await _service(llm).expand("售后的方案在正式执行之前要公示哪些内容？")

    assert result.source == "llm"
    assert len(result.expansions) == 2
    assert result.all_queries[0] == "售后的方案在正式执行之前要公示哪些内容？"


@pytest.mark.asyncio
async def test_expansion_tolerates_code_fence() -> None:
    llm = _FakeLLM('```json\n["改写一", "改写二"]\n```')

    result = await _service(llm).expand("原问题")

    assert result.expansions == ("改写一", "改写二")


@pytest.mark.asyncio
async def test_expansion_drops_original_and_duplicates() -> None:
    llm = _FakeLLM(json.dumps(["原问题", "改写一", "改写一"], ensure_ascii=False))

    result = await _service(llm).expand("原问题")

    assert result.expansions == ("改写一",)


@pytest.mark.asyncio
async def test_expansion_respects_max_queries() -> None:
    llm = _FakeLLM(json.dumps(["a", "b", "c"], ensure_ascii=False))

    result = await _service(llm, max_queries=2).expand("原问题")

    assert result.expansions == ("a", "b")


@pytest.mark.asyncio
async def test_expansion_degrades_when_model_fails() -> None:
    llm = _FakeLLM(error=RuntimeError("llm down"))

    result = await _service(llm).expand("原问题")

    assert result.expansions == ()
    assert result.source == "error"


@pytest.mark.asyncio
async def test_expansion_ignores_non_list_payload() -> None:
    llm = _FakeLLM('{"queries": ["a"]}')

    result = await _service(llm).expand("原问题")

    assert result.expansions == ()


@pytest.mark.asyncio
async def test_expansion_is_not_added_to_fusion_when_empty() -> None:
    """扩展为空时不应产生额外的检索通道。"""

    from customer_service_app.core.config import Settings
    from customer_service_app.services.rag_service import RagService

    class _Embedding:
        async def embed_query(self, _: str) -> list[float]:
            return [1.0]

    class _Vector:
        def __init__(self) -> None:
            self.calls = 0

        async def search(self, **_: object) -> list[KnowledgeChunk]:
            self.calls += 1
            return [
                KnowledgeChunk(id="a", source="a.md", title="A", content="A", score=0.9)
            ]

    class _Lexical:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def search(self, **kwargs: object) -> list[KnowledgeChunk]:
            self.queries.append(str(kwargs.get("query")))
            return []

    lexical = _Lexical()
    service = RagService(
        settings=Settings(retrieval_mode="hybrid"),
        embedding_client=_Embedding(),  # type: ignore[arg-type]
        vector_store=_Vector(),  # type: ignore[arg-type]
        lexical_retriever=lexical,  # type: ignore[arg-type]
        query_expander=_service(_FakeLLM("[]")),  # type: ignore[arg-type]
    )

    await service.retrieve(tenant_id="t", question="退货政策是什么")

    assert lexical.queries == ["退货政策是什么"]


@pytest.mark.asyncio
async def test_expansion_adds_extra_lexical_pass() -> None:
    from customer_service_app.core.config import Settings
    from customer_service_app.services.rag_service import RagService

    class _Embedding:
        async def embed_query(self, _: str) -> list[float]:
            return [1.0]

    class _Vector:
        async def search(self, **_: object) -> list[KnowledgeChunk]:
            return []

    class _Lexical:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def search(self, **kwargs: object) -> list[KnowledgeChunk]:
            self.queries.append(str(kwargs.get("query")))
            return []

    lexical = _Lexical()
    service = RagService(
        settings=Settings(retrieval_mode="hybrid", query_expansion_weight=0.7),
        embedding_client=_Embedding(),  # type: ignore[arg-type]
        vector_store=_Vector(),  # type: ignore[arg-type]
        lexical_retriever=lexical,  # type: ignore[arg-type]
        query_expander=_service(_FakeLLM('["改写一"]')),  # type: ignore[arg-type]
    )

    await service.retrieve(tenant_id="t", question="退货政策是什么")

    assert lexical.queries == ["退货政策是什么", "改写一"]
