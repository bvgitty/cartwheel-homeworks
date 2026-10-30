"""Select a review batch of sessions and record it in sample_manifest.json.

Sampling is per scenario (one session each), and every turn-trace of a picked
session joins the batch, so a reviewer always sees the whole conversation.
Sessions already in an earlier batch are excluded, so no trace counts toward
two batches. Selection uses only structure and scenario dimensions, never
outcomes or failure predictions.

    # Batch 1: 15 uniform + 15 cluster representatives
    uv run python -m analysis.review_app.select_batch B1 --uniform 15 --cluster 15
    # Batch 2: 10 sessions per value of one product dimension
    uv run python -m analysis.review_app.select_batch B2 --stratify role --per-value 10
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sklearn.cluster import KMeans

from analysis.helpers import _state
from analysis.review_app.build_cache import CACHE

SEED = 4  # HW4; fixed so every batch is reproducible


def _load_sessions() -> list[dict[str, Any]]:
    return json.loads(CACHE.read_text(encoding="utf-8"))["sessions"]


def _features(sessions: list[dict[str, Any]]) -> np.ndarray:
    """Structural features: one-hot dimensions, multi-hot tools and badges,
    and scaled turn and tool-call counts."""
    def tools(s: dict[str, Any]) -> set[str]:
        return {m["name"] for t in s["turns"] for m in t["messages"] if m.get("role") == "tool_call"}

    cats = {
        "role": lambda s: [s["role"]],
        "intent": lambda s: [s["tuple"].get("intent")],
        "group": lambda s: [s["scenario_group"]],
        "tool": lambda s: sorted(tools(s)),
        "badge": lambda s: s["badges"],
    }
    vocab = sorted({f"{k}={v}" for s in sessions for k, fn in cats.items() for v in fn(s)})
    index = {name: i for i, name in enumerate(vocab)}
    X = np.zeros((len(sessions), len(vocab) + 2))
    for row, s in enumerate(sessions):
        for k, fn in cats.items():
            for v in fn(s):
                X[row, index[f"{k}={v}"]] = 1.0
        X[row, -2] = s["n_turns"]
        X[row, -1] = s["n_tool_calls"]
    X[:, -2:] = (X[:, -2:] - X[:, -2:].mean(0)) / (X[:, -2:].std(0) + 1e-9)
    return X


def _describe(s: dict[str, Any]) -> str:
    return f"{s['role']}/{s['tuple'].get('intent')}/{s['scenario_group']}, {s['n_turns']} turn(s), {s['n_tool_calls']} tool call(s)"


def uniform(pool: list[dict[str, Any]], k: int, rng: random.Random) -> list[tuple[dict, str]]:
    return [(s, f"uniform random (seed {SEED})") for s in rng.sample(pool, k)]


def cluster(all_sessions: list[dict[str, Any]], pool_ids: set[str], k: int) -> list[tuple[dict, str]]:
    """Cluster the whole population, then take the eligible session nearest
    each centroid, so representatives reflect the population's structure."""
    X = _features(all_sessions)
    km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)
    sizes = Counter(km.labels_)
    picks = []
    for c in range(k):
        members = [i for i in np.where(km.labels_ == c)[0] if all_sessions[i]["session_id"] in pool_ids]
        if not members:
            continue
        dist = np.linalg.norm(X[members] - km.cluster_centers_[c], axis=1)
        s = all_sessions[members[int(np.argmin(dist))]]
        picks.append((s, f"cluster {c + 1}/{k} representative (cluster size {sizes[c]}): {_describe(s)}"))
    return picks


def stratify(pool: list[dict[str, Any]], dimension: str, per_value: int, rng: random.Random) -> list[tuple[dict, str]]:
    def value(s: dict[str, Any]) -> Any:
        return s.get(dimension, s["tuple"].get(dimension))

    picks = []
    for v in sorted({value(s) for s in pool}, key=str):
        members = [s for s in pool if value(s) == v]
        for s in rng.sample(members, min(per_value, len(members))):
            picks.append((s, f"stratified on {dimension}={v} ({per_value} per value, random within value)"))
    return picks


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a review batch.")
    parser.add_argument("batch_id")
    parser.add_argument("--name", default="")
    parser.add_argument("--uniform", type=int, default=0)
    parser.add_argument("--cluster", type=int, default=0)
    parser.add_argument("--stratify")
    parser.add_argument("--per-value", type=int, default=10)
    args = parser.parse_args()

    path = _state.state_path("sample_manifest.json")
    manifest = _state.read_json(path, default={}) or {}
    manifest.setdefault("source", "langfuse")
    manifest.setdefault("unit", "Sampling per scenario (one session each); every turn-trace of a picked session is reviewed and labeled.")
    batches = manifest.setdefault("batches", [])
    if any(b["id"] == args.batch_id for b in batches):
        raise SystemExit(f"batch {args.batch_id} already exists; pick a new id")

    sessions = _load_sessions()
    taken = {it["session_id"] for b in batches for it in b["items"]}
    pool = [s for s in sessions if s["session_id"] not in taken]
    rng = random.Random(f"{SEED}-{args.batch_id}")

    picks: list[tuple[dict, str]] = []
    methods = []
    if args.uniform:
        picks += uniform(pool, args.uniform, rng)
        methods.append(f"{args.uniform} uniform")
    if args.cluster:
        chosen = {s["session_id"] for s, _ in picks}
        picks += cluster(sessions, {s["session_id"] for s in pool} - chosen, args.cluster)
        methods.append(f"{args.cluster} k-means cluster representatives")
    if args.stratify:
        picks += stratify(pool, args.stratify, args.per_value, rng)
        methods.append(f"stratified on {args.stratify}, {args.per_value} per value")
    if not picks:
        raise SystemExit("nothing selected; pass --uniform, --cluster, or --stratify")

    items = [
        {"scenario_id": s["scenario_id"], "session_id": s["session_id"],
         "trace_ids": [t["trace_id"] for t in s["turns"]], "reason": reason}
        for s, reason in picks
    ]
    batches.append({
        "id": args.batch_id,
        "name": args.name or " + ".join(methods),
        "method": "; ".join(methods),
        "seed": SEED,
        "selected_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    })
    _state.write_json(path, manifest)

    n_traces = sum(len(it["trace_ids"]) for it in items)
    print(f"{args.batch_id}: {len(items)} sessions, {n_traces} traces")
    print("roles:", dict(Counter(s["role"] for s, _ in picks)))
    print("groups:", dict(Counter(s["scenario_group"] for s, _ in picks)))
    for it in items:
        print(f"  {it['scenario_id']}  {len(it['trace_ids'])}t  {it['reason']}")


if __name__ == "__main__":
    main()
