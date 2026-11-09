from __future__ import annotations

from customer_service_app.core.config import Settings
from customer_service_app.infrastructure.keyword_search.opensearch_keyword import (
    OpenSearchKeywordRetriever,
)


def build_keyword_retriever(settings: Settings) -> OpenSearchKeywordRetriever | None:
    """关键词通道依赖 OpenSearch 索引，未开启时返回 None，检索自动退化为两路融合。"""

    if not settings.keyword_search_enabled or not settings.opensearch_enabled:
        return None
    return OpenSearchKeywordRetriever(settings)
