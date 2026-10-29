"""Depth searches for candidate modes and close negatives (Batch 3, Batch 5).

Each search is a deterministic filter over sessions not yet in any batch. A
filter finds traces where a mode's *trigger* is present; it does not know
whether the agent handled the trigger well. Every pick becomes a pending
`search_hit` suggestion that the reviewer accepts (failure present) or rejects
with the boundary that excludes it (often a close negative).

Usage: uv run python -m analysis.review_app.depth_search B3   (round 1)
       uv run python -m analysis.review_app.depth_search B5   (round 2)
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "review_app" / "cache" / "sessions.json"
MANIFEST = ROOT / "state" / "sample_manifest.json"
SUGGESTIONS = ROOT / "state" / "suggestions.json"
SEED = 7


def _msgs(s: dict[str, Any], role: str, name: str | None = None) -> list[dict[str, Any]]:
    return [m for t in s["turns"] for m in t["messages"] if m["role"] == role and (name is None or m.get("name") == name)]


def _results(s: dict[str, Any], name: str | None = None) -> list[dict[str, Any]]:
    return [m["content"] for m in _msgs(s, "tool_result", name) if isinstance(m.get("content"), dict)]


def _called(s: dict[str, Any], name: str) -> bool:
    return bool(_msgs(s, "tool_call", name))


def _repeated_call(s: dict[str, Any]) -> bool:
    """Same tool called twice in one turn with different arguments."""
    for t in s["turns"]:
        seen: dict[str, set[str]] = {}
        for m in t["messages"]:
            if m["role"] == "tool_call":
                seen.setdefault(m["name"], set()).add(json.dumps(m.get("arguments"), sort_keys=True))
        if any(len(v) > 1 for v in seen.values()):
            return True
    return False


# (mode, signal description, filter, how many). Escalation is split so both
# outcomes of the trigger are represented.
SEARCHES: list[tuple[str, str, Callable[[dict[str, Any]], bool], int]] = [
    ("access_overreach", "a tool returned permission_denied",
     lambda s: any(r.get("error") == "permission_denied" for r in _results(s)), 4),
    ("denial_not_explained", "check_return_eligibility returned eligible=false",
     lambda s: any(r.get("eligible") is False for r in _results(s, "check_return_eligibility")), 4),
    ("tone_mismatch", "user_style is frustrated_impatient or repetitive_pressuring",
     lambda s: s["tuple"].get("user_style") in ("frustrated_impatient", "repetitive_pressuring"), 4),
    ("fails_to_escalate", "intent is account_change or dispute and escalate_to_human was NOT called",
     lambda s: s["tuple"].get("intent") in ("account_change", "dispute") and not _called(s, "escalate_to_human"), 2),
    ("fails_to_escalate", "intent is account_change or dispute and escalate_to_human WAS called",
     lambda s: s["tuple"].get("intent") in ("account_change", "dispute") and _called(s, "escalate_to_human"), 2),
    ("unsupported_commitment", "issue_refund returned queued_for_approval",
     lambda s: any(r.get("status") == "queued_for_approval" for r in _results(s, "issue_refund")), 3),
    ("unsupported_commitment", "intent is refund and issue_refund was NOT called",
     lambda s: s["tuple"].get("intent") == "refund" and not _called(s, "issue_refund"), 1),
    ("malformed_tool_query", "same tool called more than once in a turn with different arguments",
     _repeated_call, 3),
    ("skips_available_tool", "intent is return_eligibility or refund and check_return_eligibility was NOT called",
     lambda s: s["tuple"].get("intent") in ("return_eligibility", "refund") and not _called(s, "check_return_eligibility"), 3),
]


def _longest_reply(s: dict[str, Any]) -> int:
    return max((len(m.get("text") or "") for m in _msgs(s, "assistant")), default=0)


# Round 2, after the round-3 definitions: positives for the three modes with
# only two, and close negatives where a mode has fewer than three.
SEARCHES_R2: list[tuple[str, str, Callable[[dict[str, Any]], bool], int]] = [
    ("denial_not_explained", "check_return_eligibility returned eligible=false",
     lambda s: any(r.get("eligible") is False for r in _results(s, "check_return_eligibility")), 3),
    ("access_overreach", "a tool returned permission_denied",
     lambda s: any(r.get("error") == "permission_denied" for r in _results(s)), 3),
    ("verbose_or_unrequested_detail", "an assistant reply is over 1200 characters",
     lambda s: _longest_reply(s) > 1200, 3),
    ("skips_available_tool", "intent is return_eligibility or refund and check_return_eligibility WAS called",
     lambda s: s["tuple"].get("intent") in ("return_eligibility", "refund") and _called(s, "check_return_eligibility"), 2),
    ("fails_to_escalate", "intent is account_change or dispute and escalate_to_human WAS called",
     lambda s: s["tuple"].get("intent") in ("account_change", "dispute") and _called(s, "escalate_to_human"), 1),
]

ROUNDS = {
    "B3": ("Batch 3: depth searches for candidate modes and close negatives", SEARCHES),
    "B5": ("Batch 5: depth search round 2 for thin modes and close negatives", SEARCHES_R2),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("batch_id")
    args = ap.parse_args()

    sessions = json.loads(CACHE.read_text(encoding="utf-8"))["sessions"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if any(b["id"] == args.batch_id for b in manifest["batches"]):
        raise SystemExit(f"batch {args.batch_id} already exists; pick a new id")
    if args.batch_id not in ROUNDS:
        raise SystemExit(f"no search round defined for {args.batch_id}; known: {', '.join(ROUNDS)}")
    batch_name, searches = ROUNDS[args.batch_id]
    used = {it["scenario_id"] for b in manifest["batches"] for it in b["items"]}
    pool = [s for s in sessions if s["scenario_id"] not in used]

    rng = random.Random(SEED)
    now = datetime.now(timezone.utc).isoformat()
    items, suggestions = [], json.loads(SUGGESTIONS.read_text(encoding="utf-8"))
    for mode, signal, keep, k in searches:
        hits = [s for s in pool if keep(s) and s["scenario_id"] not in {i["scenario_id"] for i in items}]
        picks = rng.sample(hits, min(k, len(hits)))
        print(f"{mode:30} {len(hits):3} hits, took {len(picks)}  ({signal})")
        for s in picks:
            items.append({"scenario_id": s["scenario_id"], "session_id": s["session_id"],
                          "trace_ids": [t["trace_id"] for t in s["turns"]],
                          "reason": f"depth search for {mode}: {signal}"})
            suggestions.append({
                "id": f"sugg-{args.batch_id}-{len(items):02d}", "kind": "search_hit", "author": "agent",
                "mode": mode, "signal": signal, "status": "pending", "created_at": now,
                "session_id": s["session_id"], "scenario_id": s["scenario_id"],
                "trace_id": s["turns"][-1]["trace_id"],
                "note": f"Search hit for {mode}: the trigger is present. Accept if the failure is present; "
                        "reject with the boundary that excludes it if the agent handled it (close negative).",
            })

    manifest["batches"].append({"id": args.batch_id, "name": batch_name,
                                "method": "deterministic trigger filters per candidate mode, random within hits",
                                "seed": SEED, "selected_at": now, "items": items})
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    SUGGESTIONS.write_text(json.dumps(suggestions, indent=2) + "\n", encoding="utf-8")
    print(f"{args.batch_id}: {len(items)} sessions, {sum(len(i['trace_ids']) for i in items)} traces")


if __name__ == "__main__":
    main()
