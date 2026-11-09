"""Enterprise customer service backend."""

from __future__ import annotations

import asyncio
import sys


if sys.platform == "win32":
    # psycopg 与 aiomysql 的异步连接都不支持 ProactorEventLoop，而 Python 3.8+
    # 在 Windows 上默认就是 Proactor。脚本用 asyncio.run() 时会继承该策略，
    # 因此在包导入时统一切到 Selector，避免每个入口脚本各写一遍。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
