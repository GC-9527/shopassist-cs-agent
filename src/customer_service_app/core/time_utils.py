from __future__ import annotations

from datetime import datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    """把数据库读出的 naive 时间标记为 UTC。

    MySQL 的 DATETIME 不存时区，应用写入的是 UTC，读出来却没有 tzinfo。
    直接序列化成 ISO 字符串，前端会当成本地时间解析，东八区就差 8 小时。
    """

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
