"""Part E: save all-Pass rows for traces the reviewer marked "no failure observed".

The reviewer authorized this on 2026-10-29: traces with a no-failure
annotation have no other failures. A trace qualifies only if it has a
no_failure annotation, no first-failure note, and no Fail draft; anything else
is skipped and listed for manual labeling. Labels go through the running
review server (/api/label), so each one is appended to labels/<mode>.jsonl and
written to Langfuse exactly as Save row does.

Usage: uv run python -m analysis.review_app.bulk_pass [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from analysis.helpers import _state

CACHE = Path(__file__).resolve().parent / "cache" / "sessions.json"
API = "http://localhost:8020/api"
NOTE = "no failure observed (bulk-saved from the reviewer's no-failure annotation)"


def _call(path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(API + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sessions = {s["scenario_id"]: s for s in json.loads(CACHE.read_text(encoding="utf-8"))["sessions"]}
    state = _call("/state")
    drafts, labels = state["drafts"]["drafts"], state["labels"]
    modes = state["drafts"]["modes"]
    anns = [a for a in state["annotations"]["annotations"] if a.get("status") != "retracted"]
    review = [it["scenario_id"] for b in state["manifest"]["batches"] for it in b["items"]]

    no_fail = set()
    for a in anns:
        if a.get("kind") == "no_failure":
            no_fail.update(a.get("trace_ids") or [a["trace_id"]])
    first_fail = {a["trace_id"] for a in anns if a.get("first_failure")}

    todo, skipped = [], []
    for sid in review:
        for t in sessions[sid]["turns"]:
            tid = t["trace_id"]
            if tid not in no_fail:
                continue
            fails = [m for m in modes if drafts[m][tid]["label"] == 1]
            if tid in first_fail or fails:
                skipped.append((sid, tid, "first-failure note" if tid in first_fail else "Fail draft: " + ", ".join(fails)))
            elif all(tid in labels.get(m, {}) for m in modes):
                continue  # already saved
            else:
                todo.append((sid, tid))

    print(f"{len(todo)} traces to save as all-Pass ({len(todo) * len(modes)} labels); {len(skipped)} skipped")
    for sid, tid, why in skipped:
        print(f"  skipped {sid} {tid[:8]}: {why}")
    if args.dry_run:
        return

    not_synced = 0
    for sid, tid in todo:
        for m in modes:
            if tid in labels.get(m, {}):
                continue
            d = drafts[m][tid]
            evidence = d["evidence"] if d["basis"] == "close_neg" and d["evidence"] else NOTE
            rec = _call("/label", {"mode": m, "trace_id": tid, "label": 0, "evidence": evidence,
                                   "session_id": sessions[sid]["session_id"], "scenario_id": sid})
            not_synced += rec.get("langfuse") != "ok"
    print(f"saved; labels not synced to Langfuse: {not_synced}")


if __name__ == "__main__":
    main()
