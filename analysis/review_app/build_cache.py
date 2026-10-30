"""Pull the HW3 traces from Langfuse once and group them into review sessions.

Langfuse stays the canonical trace store; this cache only saves the review
interface a minute-long fetch on every page load. Cartwheel writes one trace
per user turn, so the turns of a conversation are regrouped here by
``cartwheel.session_id`` and ordered by timestamp. Each session is joined to
its HW3 scenario (dimensions and expected outcome) by scenario id.

Run (from the repo root):

    uv run --env-file .env python -m analysis.review_app.build_cache
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from analysis.helpers.langfuse_io import fetch_traces

REPO = Path(__file__).resolve().parents[2]
SCENARIOS = REPO / "scenarios" / "support_scenarios.jsonl"
CACHE = Path(__file__).resolve().parent / "cache" / "sessions.json"

WRITE_TOOLS = {"issue_refund": "REFUND", "cancel_order": "CANCEL"}


def _load_scenarios() -> dict[str, dict[str, Any]]:
    with SCENARIOS.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {row["id"]: row for row in rows}


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def _turn(trace: dict[str, Any]) -> dict[str, Any]:
    """Keep only what a reviewer reads; drop OTel resource noise."""
    ends = [o["end_time"] for o in trace["observations"] if o.get("end_time")]
    return {
        "trace_id": trace["trace_id"],
        "start": trace["timestamp"],
        "end": max(ends) if ends else trace["timestamp"],
        "messages": trace["trace"],
        "features": trace["features"],
        "permalink": trace.get("permalink"),
    }


def _badges(turns: list[dict[str, Any]]) -> list[str]:
    """Structural outliers shown as header badges (not failure judgments)."""
    badges: set[str] = set()
    for turn in turns:
        for msg in turn["messages"]:
            if msg.get("role") == "tool_call":
                name = msg.get("name")
                if name == "escalate_to_human":
                    badges.add("ESCALATED")
                if name in WRITE_TOOLS:
                    badges.add(WRITE_TOOLS[name])
            if msg.get("role") == "tool_result":
                content = msg.get("content")
                if isinstance(content, dict):
                    if content.get("ok") is False:
                        badges.add("TOOL ERROR")
                    if any(v == [] for v in content.values()):
                        badges.add("EMPTY RESULT")
    if not any(t["features"].get("tool_call_count") for t in turns):
        badges.add("NO TOOLS")
    if len(turns) > 1:
        badges.add("MULTI-TURN")
    return sorted(badges)


def build() -> dict[str, Any]:
    scenarios = _load_scenarios()
    traces = fetch_traces()
    kept = [t for t in traces if t["meta"].get("scenario_id") in scenarios]

    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in kept:
        by_session[trace["meta"]["session_id"]].append(trace)

    sessions = []
    for session_id, group in by_session.items():
        group.sort(key=lambda t: t["timestamp"])
        turns = [_turn(t) for t in group]
        meta = group[0]["meta"]
        scenario = scenarios[meta["scenario_id"]]
        start, end = _parse(turns[0]["start"]), _parse(turns[-1]["end"])
        sessions.append(
            {
                "session_id": session_id,
                "scenario_id": meta["scenario_id"],
                "role": meta.get("role"),
                "prompt_version": meta.get("prompt_version"),
                "scenario_group": scenario.get("scenario_group"),
                "data_quality_case_id": scenario.get("data_quality_case_id"),
                "tuple": scenario.get("tuple", {}),
                "expected": scenario.get("expected"),
                "start": turns[0]["start"],
                "end": turns[-1]["end"],
                "duration_s": round((end - start).total_seconds(), 1),
                "n_turns": len(turns),
                "n_messages": sum(len(t["messages"]) for t in turns),
                "n_tool_calls": sum(t["features"].get("tool_call_count", 0) for t in turns),
                "badges": _badges(turns),
                "turns": turns,
            }
        )

    # A scenario run more than once has several sessions; flag every copy.
    per_scenario: dict[str, int] = defaultdict(int)
    for session in sessions:
        per_scenario[session["scenario_id"]] += 1
    for session in sessions:
        if per_scenario[session["scenario_id"]] > 1:
            session["badges"].append("RERUN")

    sessions.sort(key=lambda s: (s["scenario_id"], s["start"]))
    summary = {
        "fetched_traces": len(traces),
        "final_scenario_traces": len(kept),
        "dropped_non_final": len(traces) - len(kept),
        "sessions": len(sessions),
        "scenarios": len(per_scenario),
        "rerun_scenarios": sorted(s for s, n in per_scenario.items() if n > 1),
    }
    return {"built_at": datetime.now().astimezone().isoformat(), "summary": summary, "sessions": sessions}


def main() -> None:
    payload = build()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"wrote {CACHE.relative_to(REPO)}")


if __name__ == "__main__":
    main()
