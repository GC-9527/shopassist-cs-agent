from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import customer_service_app.services.csat_service as csat_module
from customer_service_app.core.exceptions import AppError
from customer_service_app.domain.csat import CsatRequest
from customer_service_app.infrastructure.db.models import CsatRating
from customer_service_app.services.csat_service import CsatService, summarize_ratings


def _rating(score: int, *, tags: list[str] | None = None, comment: str | None = None) -> CsatRating:
    row = CsatRating(
        tenant_id="zh",
        user_id="u001",
        conversation_id=f"c-{score}-{len(tags or [])}",
        score=score,
        comment=comment,
        tags_json=tags or [],
    )
    row.created_at = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
    row.id = f"csat-{score}-{id(row)}"
    return row


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def one_or_none(self):
        return self._value

    def all(self):
        return self._value


class FakeSession:
    def __init__(self, *, existing=None, ratings=None):
        self.existing = existing
        self.ratings = ratings or []
        self.added: list[CsatRating] = []
        self.flushed = False
        self.committed = False

    async def execute(self, _statement):
        if self.ratings:
            return FakeResult(self.ratings)
        return FakeResult(self.existing)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        self.flushed = True
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = "csat-test-id"
            if row.created_at is None:
                row.created_at = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
            if row.updated_at is None:
                row.updated_at = row.created_at

    async def refresh(self, row, _attrs=None):
        if getattr(row, "created_at", None) is None:
            row.created_at = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)


def _fake_conversation_service(status: str):
    class FakeConversationService:
        def __init__(self, _session):
            self._session = _session

        async def ensure_conversation(self, **_kwargs):
            return SimpleNamespace(status=status, id="c-1")

    return FakeConversationService


def test_summarize_ratings_handles_empty_window() -> None:
    view = summarize_ratings(tenant_id="zh", days=30, ratings=[])

    assert view.total == 0
    assert view.average is None
    assert view.positive_rate is None
    assert view.distribution == {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    assert view.recent == []


def test_summarize_ratings_computes_average_rate_and_tags() -> None:
    ratings = [
        _rating(5, tags=["fast", "resolved"], comment="很快"),
        _rating(4, tags=["friendly"]),
        _rating(2, tags=["needs_work"]),
    ]

    view = summarize_ratings(tenant_id="zh", days=30, ratings=ratings, recent_limit=2)

    assert view.total == 3
    assert view.average == 3.67
    assert view.positive_rate == 0.667
    assert view.distribution[5] == 1
    assert view.distribution[2] == 1
    assert view.tag_counts == {"fast": 1, "resolved": 1, "friendly": 1, "needs_work": 1}
    assert len(view.recent) == 2


def test_summarize_ratings_ignores_unknown_tags() -> None:
    view = summarize_ratings(
        tenant_id="zh",
        days=30,
        ratings=[_rating(5, tags=["fast", "not-a-tag"])],
    )

    assert view.tag_counts == {"fast": 1}


@pytest.mark.asyncio
async def test_submit_rejects_open_conversation(monkeypatch) -> None:
    monkeypatch.setattr(
        csat_module, "ConversationService", _fake_conversation_service("active")
    )
    service = CsatService(FakeSession())

    with pytest.raises(AppError) as exc:
        await service.submit(
            tenant_id="zh",
            user_id="u001",
            conversation_id="c-1",
            request=CsatRequest(score=5),
        )

    assert exc.value.code == "conversation_not_closed"


@pytest.mark.asyncio
async def test_submit_normalizes_tags_and_trims_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        csat_module, "ConversationService", _fake_conversation_service("closed")
    )
    session = FakeSession()
    service = CsatService(session)

    view = await service.submit(
        tenant_id="zh",
        user_id="u001",
        conversation_id="c-1",
        request=CsatRequest(
            score=5,
            comment="  包装很好  ",
            tags=["fast", "bogus", "fast", "resolved"],
        ),
    )

    assert len(session.added) == 1
    row = session.added[0]
    assert row.tags_json == ["fast", "resolved"]
    assert row.comment == "包装很好"
    assert view.score == 5
    assert view.tags == ["fast", "resolved"]


@pytest.mark.asyncio
async def test_submit_overwrites_existing_rating(monkeypatch) -> None:
    """重复提交覆盖旧值，后台统计不会把同一会话算两次。"""

    monkeypatch.setattr(
        csat_module, "ConversationService", _fake_conversation_service("closed")
    )
    existing = _rating(2, tags=["needs_work"], comment="之前不满意")
    session = FakeSession(existing=existing)
    service = CsatService(session)

    view = await service.submit(
        tenant_id="zh",
        user_id="u001",
        conversation_id=existing.conversation_id,
        request=CsatRequest(score=5, comment="后来解决了", tags=["resolved"]),
    )

    assert session.added == []
    assert existing.score == 5
    assert existing.comment == "后来解决了"
    assert existing.tags_json == ["resolved"]
    assert view.score == 5


@pytest.mark.asyncio
async def test_summary_uses_window_query(monkeypatch) -> None:
    ratings = [_rating(5), _rating(4)]
    service = CsatService(FakeSession(ratings=ratings))

    view = await service.summary(tenant_id="zh", days=7)

    assert view.days == 7
    assert view.total == 2
    assert view.average == 4.5
