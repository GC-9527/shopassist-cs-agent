from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import httpx

from customer_service_app.core.exceptions import ExternalServiceError
from customer_service_app.domain.schemas import KnowledgeChunk
from customer_service_app.infrastructure.lexical_search.opensearch_bm25 import (
    OpenSearchBM25Retriever,
)

BUSINESS_CODE_PATTERN = re.compile(r"[A-Z]{2,}-[A-Z0-9]+(?:-[A-Z0-9]+)*")
"""LOG-SLA-48、AFS-RET-007 这类业务编码。"""


class OpenSearchKeywordRetriever(OpenSearchBM25Retriever):
    """关键词覆盖通道。

    BM25 允许"命中任意一个词就参与排名"，召回高，但长文档里的弱相关词也会把
    正确文档挤下去。这一路要求查询词大部分出现在同一块里（minimum_should_match），
    是精确度导向的通道；查询里带业务编码时再额外加一条短语匹配。

    复用 BM25 的索引、连接和写入逻辑，只替换检索语句。
    """

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int,
        document_types: Sequence[str] | None = None,
    ) -> list[KnowledgeChunk]:
        text = query.strip()
        if len(text) < 2:
            return []

        await self.ensure_index()
        filters: list[dict[str, Any]] = [{"term": {"tenant_id": tenant_id}}]
        if document_types:
            filters.append({"terms": {"document_type": list(document_types)}})

        min_match = self._settings.keyword_min_match
        must: list[dict[str, Any]] = [
            {"match": {"content": {"query": text, "minimum_should_match": min_match}}}
        ]
        should: list[dict[str, Any]] = [
            {"match_phrase": {"title": {"query": text, "boost": 2.0}}},
            {
                "match": {
                    "title": {
                        "query": text,
                        "minimum_should_match": min_match,
                        "boost": 1.5,
                    }
                }
            },
        ]
        for code in BUSINESS_CODE_PATTERN.findall(text):
            should.append({"match_phrase": {"content": {"query": code, "boost": 3.0}}})

        try:
            response = await self._client.post(
                f"{self._base_url}/{self._index}/_search",
                json={
                    "size": top_k,
                    "track_total_hits": False,
                    "query": {"bool": {"filter": filters, "must": must, "should": should}},
                },
            )
            if response.status_code != 200:
                self._raise(response, "keyword search OpenSearch")
            hits = response.json().get("hits", {}).get("hits", [])
            return [self._to_chunk(hit) for hit in hits]
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError(f"OpenSearch keyword search failed: {exc}") from exc

    @staticmethod
    def _to_chunk(hit: dict[str, Any]) -> KnowledgeChunk:
        chunk = OpenSearchBM25Retriever._to_chunk(hit)
        chunk.metadata = {**chunk.metadata, "retriever": "keyword"}
        return chunk
