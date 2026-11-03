"""HW5: build and evaluate an LLM judge for one HW4 failure mode.

Each step is a function, run from the repo root:

    uv run --env-file .env python -m analysis.run_judges candidates

Steps: ``collect_candidates`` (Part A, one enrich batch for the review app).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from analysis.helpers import _state, next_to_label
from analysis.review_app.build_cache import CACHE

MODE = "unsupported_commitment"
TRACE_EXPORT = "traces/support_traces.json"


def collect_candidates(batch_id: str = "H1", k: int = 25) -> list[dict]:
    """Search unreviewed traces for likely failures and register their sessions
    as one review batch, so every turn of a candidate conversation is labeled.

    ``next_to_label`` already skips labeled traces; sessions from earlier batches
    are skipped too, so no conversation is reviewed twice.
    """
    path = _state.state_path("sample_manifest.json")
    manifest = _state.read_json(path)
    if any(b["id"] == batch_id for b in manifest["batches"]):
        raise SystemExit(f"batch {batch_id} already exists")
    taken = {it["session_id"] for b in manifest["batches"] for it in b["items"]}

    hits = next_to_label(mode=MODE, k=k, strategy="enrich", trace_source=TRACE_EXPORT)
    sessions = json.loads(CACHE.read_text(encoding="utf-8"))["sessions"]
    by_trace = {t["trace_id"]: s for s in sessions for t in s["turns"]}

    items, seen = [], set()
    for hit in hits:
        s = by_trace[hit["trace_id"]]
        if s["session_id"] in taken or s["session_id"] in seen:
            continue
        seen.add(s["session_id"])
        items.append({
            "scenario_id": s["scenario_id"],
            "session_id": s["session_id"],
            "trace_ids": [t["trace_id"] for t in s["turns"]],
            "reason": f"{hit['signal']} (hit {hit['trace_id'][:8]})",
        })

    manifest["batches"].append({
        "id": batch_id,
        "name": f"HW5 {MODE}: next_to_label enrich, k={k}",
        "method": f"next_to_label(mode={MODE}, k={k}, strategy=enrich) over {TRACE_EXPORT}",
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    })
    _state.write_json(path, manifest)
    return items


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "candidates":
        picked = collect_candidates()
        print(f"{len(picked)} sessions, {sum(len(i['trace_ids']) for i in picked)} traces")
        for item in picked:
            print(f"  {item['scenario_id']}  {len(item['trace_ids'])}t  {item['reason']}")
    else:
        raise SystemExit("usage: python -m analysis.run_judges candidates")
