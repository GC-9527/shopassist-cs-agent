from __future__ import annotations

import pytest

from customer_service_app.core.config import Settings
from customer_service_app.infrastructure.keyword_search.factory import build_keyword_retriever
from customer_service_app.infrastructure.keyword_search.opensearch_keyword import (
    OpenSearchKeywordRetriever,
)


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_body: dict | None = None

    async def post(self, url: str, json: dict | None = None, **_: object) -> _FakeResponse:
        self.last_body = json
        return _FakeResponse(self.payload)

    async def aclose(self) -> None:
        return None


def _settings(**overrides: object) -> Settings:
    base = {
        "opensearch_enabled": True,
        "opensearch_url": "http://opensearch.example.com",
        "keyword_search_enabled": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


async def _noop() -> None:
    return None


def _hit(source: str, title: str, content: str, score: float = 5.0) -> dict:
    return {
        "_id": f"{source}-0",
        "_score": score,
        "_source": {"source": source, "title": title, "content": content, "metadata": {}},
    }


@pytest.mark.asyncio
async def test_keyword_retriever_requires_query_coverage() -> None:
    """关键词通道和 BM25 的区别就在这：要求查询词覆盖率达到阈值。"""

    retriever = OpenSearchKeywordRetriever(_settings())
    fake = _FakeClient({"hits": {"hits": [_hit("policies/a.md", "A", "内容")]}})
    retriever._client = fake  # type: ignore[assignment]
    retriever.ensure_index = _noop  # type: ignore[method-assign]

    await retriever.search(tenant_id="default", query="七天无理由退货从哪天开始算？", top_k=5)

    must = fake.last_body["query"]["bool"]["must"][0]
    assert must["match"]["content"]["minimum_should_match"] == "50%"
    assert fake.last_body["query"]["bool"]["filter"][0] == {"term": {"tenant_id": "default"}}


@pytest.mark.asyncio
async def test_keyword_retriever_boosts_business_code_phrase() -> None:
    """查询里带业务编码时，额外加一条短语匹配，精确锁定规则文档。"""

    retriever = OpenSearchKeywordRetriever(_settings())
    fake = _FakeClient({"hits": {"hits": []}})
    retriever._client = fake  # type: ignore[assignment]
    retriever.ensure_index = _noop  # type: ignore[method-assign]

    await retriever.search(tenant_id="default", query="LOG-SLA-48 规定多少小时可以催查？", top_k=5)

    should = fake.last_body["query"]["bool"]["should"]
    code_clauses = [
        clause
        for clause in should
        if clause.get("match_phrase", {}).get("content", {}).get("query") == "LOG-SLA-48"
    ]
    assert code_clauses
    assert code_clauses[0]["match_phrase"]["content"]["boost"] == 3.0


@pytest.mark.asyncio
async def test_keyword_retriever_maps_hits_and_marks_retriever() -> None:
    retriever = OpenSearchKeywordRetriever(_settings())
    retriever._client = _FakeClient(
        {"hits": {"hits": [_hit("matrices/m.md", "类目矩阵", "食品不支持", 7.5)]}}
    )  # type: ignore[assignment]
    retriever.ensure_index = _noop  # type: ignore[method-assign]

    chunks = await retriever.search(tenant_id="default", query="食品没有质量问题可以退吗？", top_k=3)

    assert [chunk.source for chunk in chunks] == ["matrices/m.md"]
    assert chunks[0].score == 7.5
    assert chunks[0].metadata["retriever"] == "keyword"


@pytest.mark.asyncio
async def test_keyword_retriever_skips_too_short_query() -> None:
    retriever = OpenSearchKeywordRetriever(_settings())
    fake = _FakeClient({"hits": {"hits": []}})
    retriever._client = fake  # type: ignore[assignment]

    assert await retriever.search(tenant_id="default", query="退", top_k=3) == []
    assert fake.last_body is None


def test_factory_requires_both_switches() -> None:
    assert build_keyword_retriever(_settings()) is not None
    assert build_keyword_retriever(_settings(keyword_search_enabled=False)) is None
    assert build_keyword_retriever(_settings(opensearch_enabled=False)) is None
