from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_service_app.core.config import get_settings
from customer_service_app.infrastructure.embeddings.factory import (
    build_embedding_client,
)
from customer_service_app.infrastructure.llm.openai_compatible import (
    OpenAICompatibleLLMClient,
)
from customer_service_app.infrastructure.keyword_search import (
    build_keyword_retriever,
)
from customer_service_app.infrastructure.lexical_search import (
    build_lexical_retriever,
)
from customer_service_app.infrastructure.rerank import build_reranker
from customer_service_app.infrastructure.vector_store.factory import (
    build_vector_store,
)
from customer_service_app.services.query_expansion_service import QueryExpansionService
from customer_service_app.services.question_router import QuestionRouter
from customer_service_app.services.rag_service import RagService

KNOWLEDGE_SOURCES = {"knowledge", "hybrid"}
TOOL_SOURCES = {"realtime_tool", "hybrid"}


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


async def _close_resource(resource: Any) -> None:
    if resource is None:
        return
    close = getattr(resource, "close", None) or getattr(resource, "aclose", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """把逐条结果压成 hit@k / mrr。"""

    hits = [1.0 if row["hit"] else 0.0 for row in rows]
    reciprocal = [1.0 / row["rank"] if row["rank"] else 0.0 for row in rows]
    return {"n": len(rows), "hit": _mean(hits), "mrr": _mean(reciprocal)}


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key))].append(row)
    return {name: _summarize(bucket) for name, bucket in sorted(buckets.items())}


def _table(title: str, data: dict[str, dict[str, Any]]) -> list[str]:
    lines = [f"### {title}", "", "| 分组 | 样本 | Hit@5 | MRR |", "| --- | ---: | ---: | ---: |"]
    for name, stats in data.items():
        lines.append(f"| {name} | {stats['n']} | {stats['hit']:.3f} | {stats['mrr']:.3f} |")
    lines.append("")
    return lines


async def run(args: argparse.Namespace) -> int:
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = dataset["items"]
    settings = get_settings()

    embedding_client = build_embedding_client(settings)
    vector_store = build_vector_store(settings)
    lexical_retriever = build_lexical_retriever(settings)
    keyword_retriever = build_keyword_retriever(settings)
    llm_client = OpenAICompatibleLLMClient(settings)
    query_expander = (
        QueryExpansionService(
            llm_client=llm_client,
            model=settings.llm_model,
            max_queries=settings.query_expansion_max_queries,
        )
        if settings.query_expansion_enabled
        else None
    )
    reranker = build_reranker(settings)
    service = RagService(
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        lexical_retriever=lexical_retriever,
        keyword_retriever=keyword_retriever,
        query_expander=query_expander,
        reranker=reranker,
    )
    router = QuestionRouter()

    retrieval_rows: list[dict[str, Any]] = []
    routing_rows: list[dict[str, Any]] = []

    try:
        for item in items:
            decision = router.route(item["question"])
            expected_action = item["expected_action"]
            if expected_action == "answer":
                route_ok = decision.source in KNOWLEDGE_SOURCES
            elif expected_action == "tool":
                route_ok = decision.source in TOOL_SOURCES
            else:
                route_ok = None
            if route_ok is not None:
                routing_rows.append({**item, "route_ok": route_ok, "route_source": decision.source})

            expected_source = item.get("expected_source")
            if not expected_source:
                continue
            chunks = await service.retrieve(
                tenant_id=args.tenant_id,
                question=item["question"],
                top_k=args.top_k,
                use_rerank=args.rerank,
            )
            sources = [chunk.source for chunk in chunks]
            rank = sources.index(expected_source) + 1 if expected_source in sources else None
            retrieval_rows.append({**item, "hit": rank is not None, "rank": rank, "sources": sources})
    finally:
        await _close_resource(llm_client)
        for resource in (reranker, keyword_retriever, lexical_retriever, vector_store, embedding_client):
            await _close_resource(resource)

    overall = _summarize(retrieval_rows)
    by_category = _group(retrieval_rows, "category")
    by_variant = _group(retrieval_rows, "variant")
    by_split = _group(retrieval_rows, "split")
    by_risk = _group(retrieval_rows, "risk_tier")
    originals = _summarize([row for row in retrieval_rows if row["variant"] == "original"])

    routing_overall = _mean([1.0 if row["route_ok"] else 0.0 for row in routing_rows])
    routing_by_category: dict[str, dict[str, Any]] = {}
    for name in sorted({row["category"] for row in routing_rows}):
        bucket = [row for row in routing_rows if row["category"] == name]
        ok = sum(1 for row in bucket if row["route_ok"])
        routing_by_category[name] = {"n": len(bucket), "accuracy": round(ok / len(bucket), 4)}

    failures = [row for row in retrieval_rows if not row["hit"]]

    lines: list[str] = []
    lines.append("# 分层评测报告")
    lines.append("")
    lines.append(f"生成时间：{datetime.now(UTC).isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## 数据集")
    lines.append("")
    lines.append(
        f"- 评测集版本：`{dataset['version']}`，语料版本：`{dataset['corpus_version']}`\n"
        f"- 独立语义种子：{dataset['seed_count']} 条；表达变体：每条 {dataset['variants_per_seed']} 种；"
        f"合计 {dataset['item_count']} 条\n"
        f"- 切分：开发 {dataset['split']['dev']} 条 / 封闭测试 {dataset['split']['test']} 条，"
        "按种子分组切分，同一 seed 的变体不会跨侧\n"
        f"- 其中模型改写失败的种子走了确定性模板兜底：{dataset['fallback_seeds']} 条"
    )
    lines.append("")
    lines.append(
        f"> 说明：{dataset['item_count']} 条由 {dataset['seed_count']} 条独立语义扩展而来，"
        f"**真正独立的语义只有 {dataset['seed_count']} 条**。"
        "变体衡量的是表达鲁棒性，不是知识覆盖度。"
    )
    lines.append("")
    lines.append("## 检索")
    lines.append("")
    lines.append(
        f"- 参与检索评测的样本：{overall['n']} 条（另有 {dataset['item_count'] - overall['n']} 条为工具/超纲/越权项，"
        "无知识来源期望）\n"
        f"- 总体 Hit@5：**{overall['hit']:.3f}**，MRR：**{overall['mrr']:.3f}**\n"
        f"- 只看原句（{originals['n']} 条）：Hit@5 {originals['hit']:.3f}，MRR {originals['mrr']:.3f}"
    )
    lines.append("")
    lines.extend(_table("按类别", by_category))
    lines.extend(_table("按表达变体", by_variant))
    lines.extend(_table("按切分", by_split))
    lines.extend(_table("按风险等级", by_risk))

    lines.append("## 路由判定")
    lines.append("")
    lines.append(
        f"- 可判定的样本：{len(routing_rows)} 条\n"
        f"- 路由准确率：**{routing_overall:.3f}**"
    )
    lines.append("")
    lines.append("| 类别 | 样本 | 路由准确率 |")
    lines.append("| --- | ---: | ---: |")
    for name, stats in routing_by_category.items():
        lines.append(f"| {name} | {stats['n']} | {stats['accuracy']:.3f} |")
    lines.append("")

    lines.append("## 失败样本")
    lines.append("")
    if not failures:
        lines.append("本轮没有检索失败样本。")
    else:
        lines.append("| seed | 变体 | 问题 | 期望 | 实际命中 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in failures[: args.max_failures]:
            got = ", ".join(row["sources"][:2]) or "（空）"
            lines.append(
                f"| {row['seed_id']} | {row['variant']} | {row['question']} | "
                f"{row['expected_source']} | {got} |"
            )
        if len(failures) > args.max_failures:
            lines.append(f"\n（仅展示前 {args.max_failures} 条，共 {len(failures)} 条）")
    lines.append("")

    report = "\n".join(lines)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the agent against the layered eval set.")
    parser.add_argument("--dataset", default=str(ROOT / "eval" / "eval_set_v1.json"))
    parser.add_argument("--output", default=str(ROOT / "evidence" / "eval_report.md"))
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--max-failures", type=int, default=15)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
