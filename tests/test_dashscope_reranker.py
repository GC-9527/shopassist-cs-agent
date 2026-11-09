from __future__ import annotations

import pytest

from customer_service_app.core.config import Settings
from customer_service_app.domain.schemas import KnowledgeChunk
from customer_service_app.infrastructure.rerank.dashscope_reranker import (
    DashScopeKnowledgeReranker,
)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """记录请求体并返回百炼结构的假客户端。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_request: dict | None = None

    async def post(self, url: str, json: dict) -> _FakeResponse:
        self.last_request = {"url": url, "json": json}
        return _FakeResponse(self.payload)

    async def aclose(self) -> None:
        return None


def _settings() -> Settings:
    return Settings(
        rerank_enabled=True,
        rerank_provider="dashscope",
        rerank_base_url="https://dashscope.example.com",
        rerank_api_key="test-key",
        rerank_model="gte-rerank-v2",
    )


def _chunks() -> list[KnowledgeChunk]:
    return [
        KnowledgeChunk(id="a", source="refund.md", title="退货政策", content="退货政策", score=0.2),
        KnowledgeChunk(id="b", source="logistics.md", title="物流时效", content="物流时效", score=0.3),
    ]


@pytest.mark.asyncio
async def test_dashscope_reranker_uses_nested_payload_and_maps_scores() -> None:
    reranker = DashScopeKnowledgeReranker(_settings())
    fake_client = _FakeClient(
        {"output": {"results": [{"index": 1, "relevance_score": 0.91}, {"index": 0, "relevance_score": 0.12}]}}
    )
    reranker._client = fake_client  # type: ignore[assignment]

    ranked = await reranker.rerank(query="物流多久到", chunks=_chunks(), top_k=2)

    assert [item.id for item in ranked] == ["b", "a"]
    assert ranked[0].score == pytest.approx(0.91)
    assert ranked[0].metadata["reranked"] is True
    body = fake_client.last_request["json"]
    assert body["input"]["query"] == "物流多久到"
    assert body["input"]["documents"] == ["退货政策", "物流时效"]
    assert body["parameters"]["top_n"] == 2
    assert fake_client.last_request["url"].endswith("/text-rerank/text-rerank")


@pytest.mark.asyncio
async def test_dashscope_reranker_returns_empty_for_no_chunks() -> None:
    reranker = DashScopeKnowledgeReranker(_settings())
    reranker._client = _FakeClient({"output": {"results": []}})  # type: ignore[assignment]

    assert await reranker.rerank(query="任意问题", chunks=[], top_k=3) == []


@pytest.mark.asyncio
async def test_dashscope_reranker_skips_out_of_range_index() -> None:
    reranker = DashScopeKnowledgeReranker(_settings())
    reranker._client = _FakeClient(
        {"output": {"results": [{"index": 9, "relevance_score": 0.8}]}}
    )  # type: ignore[assignment]

    assert await reranker.rerank(query="任意问题", chunks=_chunks(), top_k=2) == []
