"""HW5: build and evaluate an LLM judge for one HW4 failure mode.

Each step is a function, run from the repo root:

    uv run --env-file .env python -m analysis.run_judges candidates

Steps:

- ``candidates``: Part A, one enrich batch for the review app.
- ``labels``: export HW5 labels (1 = Pass, 0 = Fail) from the review app's label log.
- ``inputs``: Part B, one judge input record per labeled conversation.
- ``split``: Part B, 20/40/40 train/dev/test split (run once).
- ``dev <prompt_path>``: Part C, register a prompt version and score it on dev (paid).
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analysis.helpers import _state, judge_alignment, next_to_label, register_judge, run_judge, split_labels
from analysis.helpers.normalization import normalize_trace
from analysis.review_app.build_cache import CACHE

MODE = "unsupported_commitment"
TRACE_EXPORT = "traces/support_traces.json"
INPUTS = Path("analysis/state/hw5_trace_inputs.json")
REPORT = Path("analysis/report")
JUDGE_MODEL = "gpt-4o-mini"

# Judge runs read the saved inputs, never a fresh Langfuse fetch.
os.environ.setdefault("CARTWHEEL_JUDGE_TRACE_SOURCE", str(INPUTS.resolve()))


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


def _hw4_labels(mode: str = MODE) -> dict[str, dict]:
    """Live label per trace from the review app's append-only log (1 = Fail)."""
    live = {}
    for row in _state.read_jsonl(_state.state_path("labels", f"{mode}.jsonl")):
        if not row.get("superseded_by"):
            live[row["trace_id"]] = row
    return live


def export_labels(mode: str = MODE) -> Path:
    """Write the HW5 label file with Pass = 1, Fail = 0.

    The review app keeps writing HW4-convention labels (1 = failure present) to
    ``labels/<mode>.jsonl``; that log stays the source of truth, so rerun this
    after any label flip. The helpers read the HW5 file once it exists.
    """
    rows = [
        {
            "trace_id": r["trace_id"],
            "label": 1 - int(r["label"]),
            "evidence": r.get("evidence", ""),
            "session_id": r.get("session_id"),
            "scenario_id": r.get("scenario_id"),
            "source": r.get("source", "human"),
            "ts": r["ts"],
            "hw4_label_id": r["label_id"],
        }
        for r in _hw4_labels(mode).values()
    ]
    path = _state.state_path("hw5_labels", f"{mode}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def _sessions() -> dict[str, list[dict]]:
    """Normalized HW3 turn-traces grouped by session, in turn order."""
    raw = json.loads(Path(TRACE_EXPORT).read_text(encoding="utf-8"))["traces"]
    by_session = defaultdict(list)
    for record in sorted(raw, key=lambda r: r["timestamp"]):
        trace = normalize_trace(record)
        by_session[trace["meta"]["session_id"]].append(trace)
    return by_session


def _judge_message(message: dict) -> dict:
    """Keep role and text or tool data. ``_flatten`` renders a tool call by its
    arguments only, so the tool name goes in front of them for the judge."""
    message = dict(message)
    if message.get("role") == "tool_call":
        args = message.get("arguments")
        args = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
        message["arguments"] = f"{message['name']} {args}"
    return message


def prepare_inputs(mode: str = MODE) -> list[dict]:
    """One judge input per labeled conversation, saved to ``hw5_trace_inputs.json``.

    The evaluated turn is the session's first Fail turn, else its last turn.
    Cartwheel writes one trace per turn, so the earlier turns are stitched in
    front as context; the reply to judge is the final assistant message. Only
    ``trace_id`` and the messages are written: no labels, notes or scenario data.
    """
    labels = _hw4_labels(mode)
    records = []
    for traces in _sessions().values():
        labeled = [t for t in traces if t["trace_id"] in labels]
        if not labeled:
            continue
        if len(labeled) != len(traces):
            raise ValueError(f"session {traces[0]['meta']['session_id']} is partly labeled")
        fails = [t for t in traces if labels[t["trace_id"]]["label"] == 1]
        target = fails[0] if fails else traces[-1]
        upto = traces[: traces.index(target) + 1]
        messages = [_judge_message(m) for t in upto for m in t["trace"]]
        if messages[-1]["role"] != "assistant":
            raise ValueError(f"trace {target['trace_id']} does not end with a reply")
        records.append({"trace_id": target["trace_id"], "trace": messages})
    INPUTS.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return records


def split_data(mode: str = MODE) -> dict[str, list[str]]:
    """Stratified 20/40/40 split over the input records (run once)."""
    records = json.loads(INPUTS.read_text(encoding="utf-8"))
    return split_labels(
        mode,
        fractions=(0.20, 0.40, 0.40),
        seed=7,
        min_per_class=10,
        eligible_trace_ids=[record["trace_id"] for record in records],
    )


def run_development(mode: str, prompt_path: str) -> dict:
    """Register a prompt version, judge the dev split, and save its metrics.

    Each call registers a new version. To resume an interrupted run, call
    ``run_judge`` and ``judge_alignment`` on the same judge id instead.
    """
    record = register_judge(
        mode=mode,
        prompt_text=Path(prompt_path).read_text(encoding="utf-8"),
        judge_model=JUDGE_MODEL,
    )
    return score_dev(record["judge_id"], prompt_path)


def score_dev(judge_id: str, prompt_path: str = "") -> dict:
    """Run (or resume) a judge on dev and write ``report/dev-<judge_id>.json``."""
    run_judge(judge_id, split="dev", batch_size=10)
    development = judge_alignment(judge_id, split="dev")
    development.update(model=JUDGE_MODEL, prompt_path=prompt_path)
    (REPORT / f"dev-{judge_id}.json").write_text(json.dumps(development, indent=2) + "\n", encoding="utf-8")
    return development


def _class_counts(trace_ids: list[str], mode: str = MODE) -> Counter:
    labels = _hw4_labels(mode)
    return Counter("Fail" if labels[t]["label"] == 1 else "Pass" for t in trace_ids)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "candidates":
        picked = collect_candidates()
        print(f"{len(picked)} sessions, {sum(len(i['trace_ids']) for i in picked)} traces")
        for item in picked:
            print(f"  {item['scenario_id']}  {len(item['trace_ids'])}t  {item['reason']}")
    elif step == "labels":
        print(export_labels())
    elif step == "inputs":
        records = prepare_inputs()
        print(f"{len(records)} records: {dict(_class_counts([r['trace_id'] for r in records]))}")
    elif step == "split":
        for name, ids in split_data().items():
            print(f"{name}: {len(ids)} {dict(_class_counts(ids))}")
    elif step == "dev":
        dev = run_development(MODE, sys.argv[2])
        print(f"{dev['judge_id']}: TPR {dev['tpr']} {dev['tpr_interval']}  TNR {dev['tnr']} {dev['tnr_interval']}")
        print(f"TP {dev['tp']} FN {dev['fn']} TN {dev['tn']} FP {dev['fp']}  disagreements {len(dev['disagreements'])}")
    else:
        raise SystemExit("usage: python -m analysis.run_judges candidates|labels|inputs|split|dev <prompt>")
