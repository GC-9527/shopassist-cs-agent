from __future__ import annotations

import argparse
import asyncio
import json


SCENARIOS: list[dict[str, object]] = [
    {
        "name": "Knowledge / hygiene seal return",
        "user_id": "u001",
        "turns": ["Can I return earbuds after the hygiene seal is broken?"],
        "expect_knowledge": True,
    },
    {
        "name": "Order lookup / own order",
        "user_id": "u001",
        "turns": ["Where is my order ORD-2026-100234?"],
        "expect_tool": True,
    },
    {
        "name": "Authorization / another customer's order",
        "user_id": "u002",
        "turns": ["Where is my order ORD-2026-100234?"],
        "expect_tool": True,
        "expect_order_not_found": True,
    },
    {
        "name": "Refund / multi-turn confirmation",
        "user_id": "u001",
        "turns": [
            "The earbuds from order ORD-2026-100234 have a quality issue, I want a refund.",
            "Yes, please submit the refund now.",
        ],
        "expect_confirmation": True,
    },
    {
        "name": "Out of scope",
        "user_id": "u001",
        "turns": ["Write me a poem about the ocean."],
        "expect_scope_decline": True,
    },
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run end-to-end customer service scenarios.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--json", action="store_true", help="Print raw JSON responses.")
    return parser.parse_args()


def _summarize(turn_label: str, payload: dict) -> list[str]:
    lines = [
        f"  [{turn_label}] status={payload.get('status')} mode={payload.get('service_mode')}",
    ]
    knowledge = payload.get("knowledge") or []
    if knowledge:
        sources = sorted({item.get("source") for item in knowledge if item.get("source")})
        lines.append(f"    knowledge={len(knowledge)} sources={sources}")
    tool_calls = payload.get("tool_calls") or []
    if tool_calls:
        lines.append(f"    tool_calls={[call.get('name') for call in tool_calls]}")
    for result in payload.get("tool_results") or []:
        payload_text = json.dumps(result.get("payload"), ensure_ascii=False)
        lines.append(f"    tool_result={payload_text[:200]}")
    pending = payload.get("pending_confirmation")
    if pending:
        lines.append(
            f"    pending_confirmation={pending.get('confirmation_id')} "
            f"tool={pending.get('tool_name') or pending.get('action_type')}"
        )
    if payload.get("human_handoff"):
        lines.append(f"    human_handoff={json.dumps(payload['human_handoff'], ensure_ascii=False)[:160]}")
    answer = (payload.get("answer") or "").strip().replace("\n", " ")
    lines.append(f"    answer={answer[:220]}")
    return lines


async def _login(client, base_url: str, tenant_id: str, user_id: str) -> str:
    response = await client.post(
        f"{base_url}/api/v1/auth/demo-token",
        json={"tenant_id": tenant_id, "user_id": user_id},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _run_scenario(client, base_url: str, tenant_id: str, scenario: dict) -> tuple[int, list[str]]:
    failures = 0
    lines = [f"\n=== {scenario['name']} ==="]
    token = await _login(client, base_url, tenant_id, str(scenario["user_id"]))
    headers = {"Authorization": f"Bearer {token}"}
    conversation_id: str | None = None
    thread_id: str | None = None
    last_payload: dict = {}

    for index, question in enumerate(scenario["turns"], start=1):
        body: dict[str, object] = {
            "tenant_id": tenant_id,
            "user_id": scenario["user_id"],
            "question": question,
        }
        if conversation_id:
            body["conversation_id"] = conversation_id
        if thread_id:
            body["thread_id"] = thread_id

        try:
            response = await client.post("/api/v1/chat", json=body, headers=headers)
        except Exception as exc:  # noqa: BLE001 - smoke script reports and continues
            lines.append(f"  [turn {index}] request failed: {exc}")
            return failures + 1, lines

        if response.status_code != 200:
            lines.append(f"  [turn {index}] http={response.status_code} body={response.text[:300]}")
            return failures + 1, lines

        payload = response.json()
        last_payload = payload
        conversation_id = payload.get("conversation_id") or conversation_id
        thread_id = payload.get("thread_id") or thread_id
        lines.extend(_summarize(f"turn {index}", payload))

    if scenario.get("expect_knowledge") and not last_payload.get("knowledge"):
        failures += 1
        lines.append("  !! expected knowledge chunks, got none")
    if scenario.get("expect_tool") and not last_payload.get("tool_calls"):
        failures += 1
        lines.append("  !! expected a tool call, got none")
    if scenario.get("expect_confirmation") and not last_payload.get("pending_confirmation"):
        failures += 1
        lines.append("  !! expected a pending confirmation, got none")
    if scenario.get("expect_scope_decline"):
        answer = str(last_payload.get("answer") or "").lower()
        if not any(word in answer for word in ("can't", "cannot", "not able", "help with")):
            failures += 1
            lines.append("  !! expected the assistant to decline the out-of-scope request")
    if scenario.get("expect_order_not_found"):
        results = json.dumps(last_payload.get("tool_results") or [], ensure_ascii=False)
        if '"found": false' not in results and "found': false" not in results:
            failures += 1
            lines.append("  !! expected the order lookup to return not found for another user")
    return failures, lines


async def main() -> int:
    args = _parse_args()
    try:
        import httpx
    except ImportError:
        print("httpx is required: pip install httpx")
        return 2

    total_failures = 0
    async with httpx.AsyncClient(base_url=args.base_url, timeout=180.0) as client:
        for scenario in SCENARIOS:
            failures, lines = await _run_scenario(client, args.base_url, args.tenant_id, scenario)
            total_failures += failures
            if not args.json:
                print("\n".join(lines))

    print(f"\nscenarios={len(SCENARIOS)} failures={total_failures}")
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
