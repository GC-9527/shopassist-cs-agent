from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
DATASETS = [
    ("eval_set_v1.json", "seeds.json"),
    ("eval_set_blind_v1.json", "seeds_blind.json"),
    ("eval_set_blind_v2.json", "seeds_blind_v2.json"),
    ("eval_set_blind_v3.json", "seeds_blind_v3.json"),
]
ENTITY_PATTERN = re.compile(r"[A-Z]{2,}-\w+|\d{10,}")


@pytest.fixture(scope="module", params=DATASETS, ids=[name for name, _ in DATASETS])
def dataset(request) -> dict:
    dataset_name, _ = request.param
    path = EVAL_DIR / dataset_name
    if not path.exists():
        pytest.skip(f"{dataset_name} not built yet")
    return json.loads(path.read_text(encoding="utf-8"))


def test_split_never_splits_a_seed_across_sides(dataset: dict) -> None:
    """同一 seed 的变体必须落在同一侧，否则改写会泄漏到封闭测试里。"""

    sides: dict[str, set[str]] = defaultdict(set)
    for item in dataset["items"]:
        sides[item["seed_id"]].add(item["split"])

    leaking = {seed: value for seed, value in sides.items() if len(value) > 1}
    assert leaking == {}


def test_every_item_has_required_fields(dataset: dict) -> None:
    required = {
        "id",
        "seed_id",
        "group_id",
        "variant",
        "category",
        "question",
        "expected_action",
        "risk_tier",
        "split",
    }
    for item in dataset["items"]:
        assert required.issubset(item), f"missing fields in {item.get('id')}"
        assert item["question"].strip()
        assert item["split"] in {"dev", "test"}
        if item["expected_action"] == "answer":
            assert item["expected_source"], f"{item['id']} 是知识类问题却没有期望来源"


def test_split_sizes_are_not_grossly_unbalanced(dataset: dict) -> None:
    dev = sum(1 for item in dataset["items"] if item["split"] == "dev")
    test = len(dataset["items"]) - dev

    assert dev + test == dataset["item_count"]
    # 硬约束是"同一 seed 不跨侧"；两侧比例只是防止切分一边倒，
    # 种子数少时按类别交替会有漂移，这里要求每侧至少占 35%。
    assert min(dev, test) >= int(dataset["item_count"] * 0.35)


def test_variants_preserve_business_entities(dataset: dict) -> None:
    """改写不能丢掉订单号、规则编号这类实体，否则测的就不是同一个问题。"""

    broken: list[str] = []
    for item in dataset["items"]:
        if item["variant"] == "original":
            continue
        seed = next(
            other for other in dataset["items"]
            if other["seed_id"] == item["seed_id"] and other["variant"] == "original"
        )
        for entity in ENTITY_PATTERN.findall(seed["question"]):
            if entity not in item["question"]:
                broken.append(f"{item['id']} 丢失实体 {entity}")

    assert broken == []


def test_questions_are_unique(dataset: dict) -> None:
    questions = [item["question"] for item in dataset["items"]]

    assert len(questions) == len(set(questions))


@pytest.mark.parametrize(
    ("dataset_name", "seeds_name"),
    DATASETS,
    ids=[name for name, _ in DATASETS],
)
def test_every_seed_source_exists_in_corpus(dataset_name: str, seeds_name: str) -> None:
    """种子指向的文档必须真的在语料里，否则评测指标没有意义。"""

    seeds_path = EVAL_DIR / seeds_name
    if not seeds_path.exists():
        pytest.skip(f"{seeds_name} not found")
    seeds = json.loads(seeds_path.read_text(encoding="utf-8"))
    root = EVAL_DIR.parent / "knowledge_base"

    missing = [
        seed["seed_id"]
        for seed in seeds
        if seed.get("expected_source") and not (root / seed["expected_source"]).exists()
    ]
    assert missing == []


def test_blind_set_does_not_reuse_tuning_questions() -> None:
    """盲测集不能和调参集用同一批问题，否则"盲测"没有意义。"""

    tuning_path = EVAL_DIR / "seeds.json"
    blind_path = EVAL_DIR / "seeds_blind.json"
    if not (tuning_path.exists() and blind_path.exists()):
        pytest.skip("seed files not found")

    tuning = {seed["question"] for seed in json.loads(tuning_path.read_text(encoding="utf-8"))}
    blind = {seed["question"] for seed in json.loads(blind_path.read_text(encoding="utf-8"))}

    assert tuning & blind == set()
