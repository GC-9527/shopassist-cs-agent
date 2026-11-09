"""Keyword-coverage retrieval channel."""

from customer_service_app.infrastructure.keyword_search.factory import build_keyword_retriever
from customer_service_app.infrastructure.keyword_search.opensearch_keyword import (
    OpenSearchKeywordRetriever,
)

__all__ = ["OpenSearchKeywordRetriever", "build_keyword_retriever"]
