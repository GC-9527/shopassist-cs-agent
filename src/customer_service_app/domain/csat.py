from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


CSAT_TAGS = ("fast", "clear", "friendly", "resolved", "needs_work")
"""预置评价标签，前端展示成可多选按钮。

用固定枚举而不是自由文本，后台才能按标签聚合；
自由文本只放在 `comment` 里，不做结构化统计。
"""


class CsatRequest(BaseModel):
    """客户对一次会话的满意度评价。"""

    score: int = Field(ge=1, le=5, description="1-5 星")
    comment: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=5)


class CsatView(BaseModel):
    """单条评价。"""

    id: str
    conversation_id: str
    score: int
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class CsatCommentView(BaseModel):
    """后台列表里展示的一条评价。"""

    conversation_id: str
    user_id: str
    score: int
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class CsatSummaryView(BaseModel):
    """满意度汇总。

    `distribution` 固定返回 5 到 1 星的计数，前端可直接画长度条；
    样本为 0 时 average 返回 None，避免显示成 0 分。
    """

    tenant_id: str
    days: int
    total: int = 0
    average: float | None = None
    positive_rate: float | None = None
    distribution: dict[int, int] = Field(default_factory=dict)
    tag_counts: dict[str, int] = Field(default_factory=dict)
    recent: list[CsatCommentView] = Field(default_factory=list)
