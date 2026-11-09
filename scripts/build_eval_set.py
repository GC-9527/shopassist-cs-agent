from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_service_app.core.config import get_settings
from customer_service_app.infrastructure.llm.openai_compatible import (
    OpenAICompatibleLLMClient,
)

VARIANT_STYLES: list[tuple[str, str]] = [
    ("colloquial", "改写成更口语化的日常说法"),
    ("terse", "用更短更直接的说法"),
    ("polite", "加上礼貌客气的措辞"),
    ("background", "先补一句无关紧要的个人背景再提问"),
    ("synonym", "换一组同义词表达同样的问题"),
    ("bilingual", "中英文混用"),
    ("emotional", "用有点着急的语气"),
    ("formal", "改成正式的书面表达"),
    ("filler", "加上口语赘词，比如“就是”“那个”"),
]
"""每条种子扩展 9 个表达变体，加上原句共 10 条。

变体只改表达，不改语义和实体：订单号、规则编号、产品名必须原样保留。
"""


def _fallback_variant(question: str, style: str) -> str:
    """模型不可用时用确定性模板兜底，保证脚本可离线产出。"""

    core = question.rstrip("。？?！!")
    if not _has_cjk(question):
        # 英文问题不能套中文模板，否则回落的变体会变成中英混杂。
        english = {
            "colloquial": f"Hey, quick question — {core}?",
            "terse": f"{core}?",
            "polite": f"Sorry to bother you, {core}? Thanks.",
            "background": f"I've ordered from you before, {core}?",
            "synonym": f"What's the rule on this: {core}?",
            "bilingual": f"{core}? (Chinese answer is fine too.)",
            "emotional": f"I'm a bit frustrated — {core}?",
            "formal": f"I would like to ask: {core}.",
            "filler": f"So, um, {core}?",
        }
        return english.get(style, f"{core}?")

    templates = {
        "colloquial": f"想问一下，{core}？",
        "terse": f"{core}？",
        "polite": f"麻烦问一下，{core}？谢谢。",
        "background": f"我是老客户了，之前也下过几单，{core}？",
        "synonym": f"{core}，这种情况一般怎么算？",
        "bilingual": f"{core}？用英文回答也可以。",
        "emotional": f"有点着急，{core}？",
        "formal": f"咨询一下：{core}。",
        "filler": f"就是那个，{core}？",
    }
    return templates.get(style, f"{core}？")


def _has_cjk(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)


def _parse_variants(raw: str, question: str, count: int) -> list[str]:
    """从模型输出里取出变体数组，容忍代码块围栏和多余说明。"""

    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    variants: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if value and value != question and value not in variants:
            variants.append(value)
    return variants[:count]


def _split_for_category(seed_ids: list[str]) -> dict[str, str]:
    """按类别交替切分，保证同一 seed 的所有变体落在同一侧。"""

    ordered = sorted(seed_ids)
    assignment: dict[str, str] = {}
    for index, seed_id in enumerate(ordered):
        digest = hashlib.sha256(seed_id.encode()).hexdigest()
        # 用哈希做稳定的整体偏移，再按序号交替，避免人为挑选导致两侧难度失衡。
        offset = int(digest[:2], 16) % 2
        assignment[seed_id] = "test" if (index + offset) % 2 == 0 else "dev"
    return assignment


async def _expand(
    client: OpenAICompatibleLLMClient,
    seed: dict[str, Any],
    *,
    model: str,
    semaphore: asyncio.Semaphore,
) -> tuple[list[str], bool]:
    """为一条种子生成变体，返回 (变体列表, 是否走了兜底)。"""

    question = seed["question"]
    style_lines = "\n".join(
        f"{index + 1}. {name}：{desc}" for index, (name, desc) in enumerate(VARIANT_STYLES)
    )
    prompt = (
        "你是客服质检标注员。下面有一条客服问题，请按给定的 9 种风格各改写一次。\n"
        "硬性要求：\n"
        "- 只改表达方式，问题和实体（订单号、规则编号、产品名、金额、时长）必须保持不变；\n"
        "- 保持原问题的语言：英文问题就用英文改写，不要翻译；\n"
        "- 每条都是能独立成立的问句，不依赖上下文；\n"
        "- 不要回答问题，不要解释，不要编号。\n"
        f"只输出一个 JSON 数组，正好 9 个字符串，顺序与风格列表一致。\n\n"
        f"风格列表：\n{style_lines}\n\n"
        f"原问题：{question}"
    )
    async with semaphore:
        try:
            response = await client.chat(
                [{"role": "user", "content": prompt}],
                model=model,
                temperature=0.7,
            )
            variants = _parse_variants(response.content or "", question, len(VARIANT_STYLES))
        except Exception as exc:  # noqa: BLE001 - 单条失败不应中断整体构造
            print(f"[warn] {seed['seed_id']} 改写失败：{exc}")
            variants = []

    if len(variants) < len(VARIANT_STYLES):
        used = set(variants)
        for name, _ in VARIANT_STYLES:
            if len(variants) >= len(VARIANT_STYLES):
                break
            candidate = _fallback_variant(question, name)
            if candidate not in used:
                variants.append(candidate)
                used.add(candidate)
        return variants, True
    return variants, False


async def build(
    *,
    seeds_path: Path,
    output_path: Path,
    model: str,
    offline: bool,
    concurrency: int,
) -> None:
    seeds = json.loads(seeds_path.read_text(encoding="utf-8"))
    settings = get_settings()
    client = None if offline else OpenAICompatibleLLMClient(settings)
    semaphore = asyncio.Semaphore(concurrency)

    async def expand_one(seed: dict[str, Any]) -> tuple[list[str], bool]:
        if client is None:
            return (
                [_fallback_variant(seed["question"], name) for name, _ in VARIANT_STYLES],
                True,
            )
        return await _expand(client, seed, model=model, semaphore=semaphore)

    try:
        expanded = await asyncio.gather(*(expand_one(seed) for seed in seeds))
    finally:
        if client is not None:
            await client.close()

    by_category: dict[str, list[str]] = {}
    for seed in seeds:
        by_category.setdefault(seed["category"], []).append(seed["seed_id"])
    split_by_seed = {
        seed_id: split
        for ids in by_category.values()
        for seed_id, split in _split_for_category(ids).items()
    }

    items: list[dict[str, Any]] = []
    fallback_count = 0
    for seed, (variants, used_fallback) in zip(seeds, expanded, strict=True):
        fallback_count += int(used_fallback)
        split = split_by_seed[seed["seed_id"]]
        rows = [("original", seed["question"]), *zip(
            [name for name, _ in VARIANT_STYLES], variants, strict=False
        )]
        for variant, question in rows:
            items.append(
                {
                    "id": f"{seed['seed_id']}-{variant}",
                    "seed_id": seed["seed_id"],
                    "group_id": seed["seed_id"],
                    "variant": variant,
                    "category": seed["category"],
                    "question": question,
                    "expected_source": seed.get("expected_source"),
                    "expected_action": seed["expected_action"],
                    "expected_tool": seed.get("expected_tool"),
                    "risk_tier": seed.get("risk_tier", "normal"),
                    "split": split,
                }
            )

    dev = sum(1 for item in items if item["split"] == "dev")
    payload = {
        "version": output_path.stem,
        "corpus_version": settings.knowledge_corpus_version,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed_count": len(seeds),
        "item_count": len(items),
        "variants_per_seed": 1 + len(VARIANT_STYLES),
        "fallback_seeds": fallback_count,
        "split": {"dev": dev, "test": len(items) - dev},
        "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"built {len(items)} items from {len(seeds)} seeds -> {output_path}\n"
        f"dev={dev} test={len(items) - dev} fallback_seeds={fallback_count}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the layered evaluation set.")
    parser.add_argument("--seeds", default=str(ROOT / "eval" / "seeds.json"))
    parser.add_argument("--output", default=str(ROOT / "eval" / "eval_set_v1.json"))
    parser.add_argument("--model", default="")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--offline", action="store_true", help="不调用模型，使用确定性模板")
    args = parser.parse_args()

    settings = get_settings()
    asyncio.run(
        build(
            seeds_path=Path(args.seeds),
            output_path=Path(args.output),
            model=args.model or settings.llm_model,
            offline=args.offline,
            concurrency=args.concurrency,
        )
    )


if __name__ == "__main__":
    main()
