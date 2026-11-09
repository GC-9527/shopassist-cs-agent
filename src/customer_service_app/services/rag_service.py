from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from time import perf_counter
from typing import Any

from customer_service_app.core.config import Settings
from customer_service_app.domain.query_rewrite import RetrievalQuality
from customer_service_app.domain.routing import RouteDecision
from customer_service_app.domain.schemas import KnowledgeChunk
from customer_service_app.infrastructure.embeddings.base import EmbeddingClient
from customer_service_app.infrastructure.lexical_search.base import LexicalKnowledgeRetriever
from customer_service_app.infrastructure.rerank.base import KnowledgeReranker
from customer_service_app.infrastructure.vector_store.base import KnowledgeVectorStore
from customer_service_app.observability.metrics import (
    RETRIEVAL_CALLS,
    RETRIEVAL_LATENCY,
    RETRIEVAL_RESULTS,
)
from customer_service_app.services.query_expansion_service import QueryExpansionService
from customer_service_app.services.question_router import QuestionRouter


class RagService:
    """租户隔离的向量/BM25 混合检索，支持 RRF 融合和可选 Reranker。"""

    def __init__(
        self,
        *,
        settings: Settings,
        embedding_client: EmbeddingClient,
        vector_store: KnowledgeVectorStore,
        lexical_retriever: LexicalKnowledgeRetriever | None = None,
        keyword_retriever: LexicalKnowledgeRetriever | None = None,
        query_expander: QueryExpansionService | None = None,
        reranker: KnowledgeReranker | None = None,
        question_router: QuestionRouter | None = None,
    ) -> None:
        self._settings = settings
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._lexical_retriever = lexical_retriever
        self._keyword_retriever = keyword_retriever
        self._query_expander = query_expander
        self._reranker = reranker
        self._question_router = question_router or QuestionRouter()

    async def retrieve(
        self,
        *,
        tenant_id: str,
        question: str,
        dense_query: str | None = None,
        sparse_query: str | None = None,
        top_k: int | None = None,
        use_rerank: bool = False,
        route_decision: RouteDecision | None = None,
        document_types: Sequence[str] | None = None,
    ) -> list[KnowledgeChunk]:
        """并发召回两路候选，融合后只把最终 top_k 交给大模型。"""

        if not self._settings.rag_enabled:
            RETRIEVAL_CALLS.labels(mode="disabled", status="skipped").inc()
            return []
        resolved_top_k = top_k or self._settings.rag_top_k
        decision = route_decision or self._question_router.route(question)
        mode = self._retrieval_mode()
        if decision.source == "realtime_tool":
            RETRIEVAL_CALLS.labels(mode="tool", status="skipped").inc()
            return []
        allowed_document_types = tuple(
            document_types if document_types is not None else decision.document_types
        )
        started = perf_counter()

        candidate_k = max(
            resolved_top_k,
            resolved_top_k * max(self._settings.hybrid_candidate_multiplier, 1),
        )
        channels = []
        if mode in {"dense", "hybrid"}:
            channels.append(
                (
                    "dense",
                    self._dense_search(
                        tenant_id=tenant_id,
                        question=dense_query or question,
                        top_k=candidate_k,
                        document_types=allowed_document_types,
                    ),
                    self._settings.hybrid_dense_weight,
                )
            )
        if mode in {"lexical", "hybrid"} and self._lexical_retriever is not None:
            channels.append(
                (
                    "bm25",
                    self._lexical_retriever.search(
                        tenant_id=tenant_id,
                        query=sparse_query or question,
                        top_k=candidate_k,
                        document_types=allowed_document_types,
                    ),
                    self._settings.hybrid_lexical_weight,
                )
            )
        if mode in {"keyword", "hybrid"} and self._keyword_retriever is not None:
            channels.append(
                (
                    "keyword",
                    self._keyword_retriever.search(
                        tenant_id=tenant_id,
                        query=sparse_query or question,
                        top_k=candidate_k,
                        document_types=allowed_document_types,
                    ),
                    self._settings.hybrid_keyword_weight,
                )
            )

        # 查询扩展作为额外召回路：改写结果只增加候选，不替换原查询，
        # 改写错了也不会把原本正确的召回挤掉。
        expansions: tuple[str, ...] = ()
        if self._query_expander is not None and mode in {"lexical", "keyword", "hybrid"}:
            expanded = await self._query_expander.expand(question)
            expansions = expanded.expansions

        for index, alternative in enumerate(expansions, start=1):
            if self._lexical_retriever is not None and mode in {"lexical", "hybrid"}:
                channels.append(
                    (
                        f"bm25+{index}",
                        self._lexical_retriever.search(
                            tenant_id=tenant_id,
                            query=alternative,
                            top_k=candidate_k,
                            document_types=allowed_document_types,
                        ),
                        self._settings.hybrid_lexical_weight
                        * self._settings.query_expansion_weight,
                    )
                )
            if self._keyword_retriever is not None and mode in {"keyword", "hybrid"}:
                channels.append(
                    (
                        f"keyword+{index}",
                        self._keyword_retriever.search(
                            tenant_id=tenant_id,
                            query=alternative,
                            top_k=candidate_k,
                            document_types=allowed_document_types,
                        ),
                        self._settings.hybrid_keyword_weight
                        * self._settings.query_expansion_weight,
                    )
                )

        tasks = {name: asyncio.create_task(coro) for name, coro, _ in channels}
        weights = {name: weight for name, _, weight in channels}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        results: dict[str, Any] = dict(zip(tasks, gathered, strict=True))

        failures: list[Exception] = []
        for name, value in results.items():
            if isinstance(value, Exception):
                failures.append(value)
                logging.warning("%s retrieval degraded: %s", name, value)

        # 所有通道都失败才显式报错；只要有一路成功就用它降级返回。
        if failures and not any(isinstance(value, list) and value for value in results.values()):
            self._record_retrieval(
                mode=mode,
                status="error",
                result_count=0,
                started=started,
            )
            raise failures[0]

        rankings = [
            (name, value, weights[name])
            for name, value in results.items()
            if not isinstance(value, Exception)
        ]
        candidates = self._rrf(rankings)
        if use_rerank and self._reranker is not None and candidates:
            try:
                reranked = await self._reranker.rerank(
                    query=question,
                    chunks=candidates,
                    top_k=resolved_top_k,
                )
                self._record_retrieval(
                    mode=mode,
                    status="success",
                    result_count=len(reranked),
                    started=started,
                )
                return reranked
            except Exception as exc:
                # Reranker 是质量增强，不应成为客服链路单点。
                logging.warning("rerank degraded to RRF order: %s", exc)
        result = candidates[:resolved_top_k]
        self._record_retrieval(
            mode=mode,
            status="degraded" if any(isinstance(item, Exception) for item in results) else "success",
            result_count=len(result),
            started=started,
        )
        return result

    @staticmethod
    def _record_retrieval(
        *,
        mode: str,
        status: str,
        result_count: int,
        started: float,
    ) -> None:
        """记录有限标签的检索指标，禁止把问题文本或租户 ID 放进标签。"""

        RETRIEVAL_CALLS.labels(mode=mode, status=status).inc()
        RETRIEVAL_LATENCY.labels(mode=mode).observe(perf_counter() - started)
        RETRIEVAL_RESULTS.labels(mode=mode).observe(result_count)

    def evaluate_quality(
        self,
        *,
        question: str,
        chunks: list[KnowledgeChunk],
        route_decision: RouteDecision | None = None,
    ) -> RetrievalQuality:
        """对检索结果做确定性质量门禁，避免低质量上下文直接进入 LLM。"""
        # 实时订单/物流查询本来就应走工具，RAG 为空不代表检索失败。
        decision = route_decision or self._question_router.route(question)
        if decision.source == "realtime_tool":
            return RetrievalQuality(
                sufficient=True,
                chunk_count=0,
                reason="business_query_routed_to_tools",
            )

        max_score = max((float(item.score or 0.0) for item in chunks), default=0.0)
        enough_chunks = len(chunks) >= max(self._settings.retrieval_quality_min_chunks, 1)

        # RRF 分数与余弦分数不同尺度，混合检索主要依据非空候选判定。
        score_required = self._settings.retrieval_mode.lower() == "dense"
        score_ok = (
            max_score >= self._settings.retrieval_quality_min_score
            if score_required
            else bool(chunks)
        )
        sufficient = enough_chunks and score_ok
        return RetrievalQuality(
            sufficient=sufficient,
            chunk_count=len(chunks),
            max_score=max_score,
            retry_recommended=not sufficient,
            reason="retrieval_sufficient" if sufficient else "insufficient_retrieval_evidence",
        )

    async def _dense_search(
        self,
        *,
        tenant_id: str,
        question: str,
        top_k: int,
        document_types: Sequence[str] | None = None,
    ) -> list[KnowledgeChunk]:
        query_vector = await self._embedding_client.embed_query(question)
        chunks = await self._vector_store.search(
            tenant_id=tenant_id,
            query_vector=query_vector,
            top_k=top_k,
            score_threshold=self._settings.rag_score_threshold,
            document_types=document_types,
        )
        for item in chunks:
            item.metadata = {**item.metadata, "retriever": "dense"}
        return chunks

    def _route(self, question: str) -> str:
        """Compatibility helper for callers that still expect a retrieval mode."""

        decision = self._question_router.route(question)
        return "none" if decision.source == "realtime_tool" else self._retrieval_mode()

    def _retrieval_mode(self) -> str:
        configured = self._settings.retrieval_mode.lower()
        if configured in {"lexical", "hybrid"} and self._lexical_retriever is None:
            return "dense"
        if configured not in {"dense", "lexical", "hybrid"}:
            return "dense"
        return configured

    def _rrf(
        self,
        rankings: list[tuple[str, list[KnowledgeChunk], float]],
    ) -> list[KnowledgeChunk]:
        """用排名融合而非原始分数融合，避免 BM25、关键词与余弦分数尺度不一致。"""

        rrf_k = max(self._settings.hybrid_rrf_k, 1)
        scores: dict[str, float] = {}
        chunks: dict[str, KnowledgeChunk] = {}
        sources: dict[str, set[str]] = {}
        for source, ranking, weight in rankings:
            for rank, chunk in enumerate(ranking, start=1):
                key = chunk.id or f"{chunk.source}:{chunk.title}:{hash(chunk.content)}"
                scores[key] = scores.get(key, 0.0) + weight / (rrf_k + rank)
                chunks.setdefault(key, chunk.model_copy(deep=True))
                sources.setdefault(key, set()).add(source)

        ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
        result: list[KnowledgeChunk] = []
        for key in ordered:
            chunk = chunks[key]
            chunk.score = scores[key]
            chunk.metadata = {
                **chunk.metadata,
                "retrievers": sorted(sources[key]),
                "fusion": "rrf",
            }
            result.append(chunk)
        return result
