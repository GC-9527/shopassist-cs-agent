from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """解析服务启动参数。"""
    parser = argparse.ArgumentParser(description="Start the FastAPI application server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def main() -> None:
    """使用当前 Python 解释器启动开发服务器。

    为什么不用 `uvicorn` 命令行：Windows 下 uvicorn 0.36+ 的 asyncio loop factory
    会强制返回 ProactorEventLoop，而 psycopg 的异步连接只支持 SelectorEventLoop，
    LangGraph 的 PostgreSQL checkpointer 会在启动时直接失败。这里显式指定
    loop_factory 来绕开该分支。
    """

    args = parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))

    import uvicorn

    reload_enabled = args.reload
    if reload_enabled and sys.platform == "win32":
        # reload 会另起子进程，loop_factory 无法继承。
        print("[run_dev] Windows 不支持 reload + psycopg 异步，已关闭 reload。")
        reload_enabled = False

    config = uvicorn.Config(
        "customer_service_app.main:app",
        host=args.host,
        port=args.port,
        reload=reload_enabled,
        reload_dirs=[str(ROOT / "src")] if reload_enabled else None,
    )
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        server.run()


if __name__ == "__main__":
    main()
