from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.core.exceptions import AppError
from customer_service_app.core.time_utils import as_utc
from customer_service_app.domain.csat import (
    CSAT_TAGS,
    CsatCommentView,
    CsatRequest,
    CsatSummaryView,
    CsatView,
)
from customer_service_app.infrastructure.db.models import CsatRating
from customer_service_app.services.conversation_service import ConversationService


class CsatService:
    """会话满意度：提交评价与后台汇总。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def submit(
        self,
        *,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        request: CsatRequest,
    ) -> CsatView:
        """提交评价。

        只有会话本人、且会话已结束后才接受评价；一条会话只保留一条，
        重复提交覆盖旧值，避免同一会话在后台统计里被重复计数。
        """

        conversation = await ConversationService(self._session).ensure_conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            first_question="",
            allow_closed=True,
        )
        if conversation.status != "closed":
            raise AppError(
                "请先结束会话再评价",
                code="conversation_not_closed",
                status_code=409,
            )

        tags = self._normalize_tags(request.tags)
        result = await self._session.execute(
            select(CsatRating).where(
                CsatRating.tenant_id == tenant_id,
                CsatRating.conversation_id == conversation_id,
            )
        )
        rating = result.scalars().one_or_none()
        if rating is None:
            rating = CsatRating(
                tenant_id=tenant_id,
                user_id=user_id,
                conversation_id=conversation_id,
                score=request.score,
                comment=(request.comment or "").strip() or None,
                tags_json=tags,
            )
            self._session.add(rating)
        else:
            rating.score = request.score
            rating.comment = (request.comment or "").strip() or None
            rating.tags_json = tags

        await self._session.flush()
        await self._session.refresh(rating, ["created_at", "updated_at"])
        return self._to_view(rating)

    async def get(
        self, *, tenant_id: str, user_id: str, conversation_id: str
    ) -> CsatView | None:
        """读取某条会话的评价；会话归属仍走统一校验。"""

        await ConversationService(self._session).ensure_conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            first_question="",
            allow_closed=True,
        )
        result = await self._session.execute(
            select(CsatRating).where(
                CsatRating.tenant_id == tenant_id,
                CsatRating.conversation_id == conversation_id,
            )
        )
        rating = result.scalars().one_or_none()
        return self._to_view(rating) if rating is not None else None

    async def summary(
        self,
        *,
        tenant_id: str,
        days: int = 30,
        recent_limit: int = 10,
    ) -> CsatSummaryView:
        """按时间窗口汇总满意度，并附最近带文字的评价。"""

        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(CsatRating)
            .where(CsatRating.tenant_id == tenant_id, CsatRating.created_at >= since)
            .order_by(CsatRating.created_at.desc())
        )
        ratings = list(result.scalars().all())
        return summarize_ratings(
            tenant_id=tenant_id,
            days=days,
            ratings=ratings,
            recent_limit=recent_limit,
        )

    @staticmethod
    def _normalize_tags(tags: list[str]) -> list[str]:
        """只保留预置标签并去重，未知值直接丢弃。"""

        seen: list[str] = []
        for item in tags:
            value = item.strip()
            if value in CSAT_TAGS and value not in seen:
                seen.append(value)
        return seen

    @staticmethod
    def _to_view(rating: CsatRating) -> CsatView:
        return CsatView(
            id=rating.id,
            conversation_id=rating.conversation_id,
            score=rating.score,
            comment=rating.comment,
            tags=list(rating.tags_json or []),
            created_at=as_utc(rating.created_at),
        )


def summarize_ratings(
    *,
    tenant_id: str,
    days: int,
    ratings: list[CsatRating],
    recent_limit: int = 10,
) -> CsatSummaryView:
    """把评价列表聚合成后台看板需要的形状。

    独立成纯函数，方便不连数据库直接测边界情况（空样本、全一星等）。
    """

    total = len(ratings)
    distribution = {score: 0 for score in range(5, 0, -1)}
    tag_counts: dict[str, int] = {}
    for rating in ratings:
        if rating.score in distribution:
            distribution[rating.score] += 1
        for tag in rating.tags_json or []:
            if tag in CSAT_TAGS:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    average = round(sum(item.score for item in ratings) / total, 2) if total else None
    positive = sum(1 for item in ratings if item.score >= 4)
    positive_rate = round(positive / total, 3) if total else None

    recent = [
        CsatCommentView(
            conversation_id=item.conversation_id,
            user_id=item.user_id,
            score=item.score,
            comment=item.comment,
            tags=list(item.tags_json or []),
            created_at=as_utc(item.created_at),
        )
        for item in ratings[:recent_limit]
    ]

    return CsatSummaryView(
        tenant_id=tenant_id,
        days=days,
        total=total,
        average=average,
        positive_rate=positive_rate,
        distribution=distribution,
        tag_counts=tag_counts,
        recent=recent,
    )
