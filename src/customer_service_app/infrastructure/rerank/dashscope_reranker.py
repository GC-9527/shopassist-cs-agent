from __future__ import annotations

import httpx

from customer_service_app.core.config import Settings
from customer_service_app.core.exceptions import ExternalServiceError
from customer_service_app.domain.schemas import KnowledgeChunk


DASHSCOPE_RERANK_PATH = "/api/v1/services/rerank/text-rerank/text-rerank"


class DashScopeKnowledgeReranker:
    """阿里云百炼 gte-rerank 适配器。

    百炼的 rerank 接口与其他厂商不同：body 不是平铺的 query/documents，
    结果也包在 output.results 里，因此不能复用 HttpKnowledgeReranker。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.require("RERANK_BASE_URL", settings.rerank_base_url).rstrip("/")
        self._api_key = settings.require("RERANK_API_KEY", settings.rerank_api_key)
        self._client = httpx.AsyncClient(
            timeout=settings.rerank_timeout_seconds,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    async def rerank(
        self,
        *,
        query: str,
        chunks: list[KnowledgeChunk],
        top_k: int,
    ) -> list[KnowledgeChunk]:
        if not chunks:
            return []
        payload = {
            "model": self._settings.rerank_model,
            "input": {
                "query": query,
                "documents": [item.content for item in chunks],
            },
            "parameters": {
                "top_n": min(top_k, len(chunks)),
                "return_documents": False,
            },
        }
        try:
            response = await self._client.post(
                f"{self._base_url}{DASHSCOPE_RERANK_PATH}",
                json=payload,
            )
            response.raise_for_status()
            results = response.json().get("output", {}).get("results", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise ExternalServiceError(f"DashScope rerank request failed: {exc}") from exc

        ranked: list[KnowledgeChunk] = []
        for item in results:
            index = int(item.get("index", -1))
            if index < 0 or index >= len(chunks):
                continue
            chunk = chunks[index].model_copy(deep=True)
            chunk.score = float(item.get("relevance_score") or 0.0)
            chunk.metadata = {**chunk.metadata, "reranked": True, "rerank_provider": "dashscope"}
            ranked.append(chunk)
        return ranked

    async def close(self) -> None:
        await self._client.aclose()
