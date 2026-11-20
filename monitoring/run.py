"""Run the monitor for one period: fetch, validate, sample, judge, correct, score.

Usage:
    uv run python -m monitoring.run --period before --dry-run   # counts only, no judge calls
    uv run python -m monitoring.run --period before --yes       # judge, correct, write scores
    uv run python -m monitoring.run --last-hours 24 --yes       # the scheduled form

Two ways to define a period:

* ``--period LABEL`` reads a fixed UTC window from ``monitoring/config.json``.
  The window must contain all 50 monitoring scenario ids (Homework 3), and
  the turns are grouped into conversations by scenario id.
* ``--last-hours N`` reads the previous N hours. The turns are grouped by
  ``meta.session_id``. An empty window records a zero count and exits 0
  without calling the judge.

In both modes every eligible trace must come from the configured Cartwheel
model, otherwise the period is rejected.

Only the random sample feeds the prevalence estimate. Risk-group verdicts are
saved and scored separately because the groups are not a random sample.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from analysis.helpers.normalization import _text, normalize_trace
from monitoring.sample import DEFAULT_RISK_GROUPS, select_traces

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "monitoring" / "config.json"
SCENARIOS_PATH = ROOT / "scenarios" / "monitoring_scenarios.jsonl"
HISTORY_PATH = ROOT / "monitoring" / "history.jsonl"
CHART_PATH = ROOT / "monitoring" / "prevalence.svg"
OUTPUT_DIR = ROOT / "monitoring" / "output"


# ---------------------------------------------------------------------------
# config and time windows
# ---------------------------------------------------------------------------


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    unknown = set(config["risk_groups"]) - set(DEFAULT_RISK_GROUPS)
    if unknown:
        raise ValueError(f"unknown risk groups in config: {sorted(unknown)}")
    return config


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def monitoring_scenario_ids(path: Path = SCENARIOS_PATH) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {json.loads(line)["id"] for line in lines if line.strip()}


def _bare_model(model: str) -> str:
    """'anthropic/claude-haiku-4-5' -> 'claude-haiku-4-5' (Langfuse keeps the LiteLLM prefix)."""
    return model.split("/", 1)[-1]


# ---------------------------------------------------------------------------
# Langfuse -> normalized traces
# ---------------------------------------------------------------------------


def fetch_window(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Every trace whose timestamp falls in [start, end), normalized."""
    from analysis.helpers.langfuse_io import _client

    lf = _client()
    summaries: list[Any] = []
    page = 1
    while True:
        resp = lf.api.trace.list(
            from_timestamp=start, to_timestamp=end, page=page, limit=100
        )
        batch = list(resp.data or [])
        summaries.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    traces = []
    for summary in summaries:
        try:
            traces.append(normalize_trace(lf.api.trace.get(summary.id)))
        except ValueError as exc:  # a trace with no messages has nothing to judge
            print(f"  skipping {summary.id}: {exc}")
    return traces


def check_models(traces: list[dict[str, Any]], model: str) -> None:
    """Reject the period if any eligible trace used a different (or unknown) model."""
    bad = {
        trace["id"]: trace["models"]
        for trace in traces
        if {_bare_model(m) for m in trace["models"]} != {model}
    }
    if bad:
        sample = dict(list(bad.items())[:3])
        raise SystemExit(
            f"rejected: {len(bad)} eligible trace(s) not on {model}, e.g. {sample}"
        )


# ---------------------------------------------------------------------------
# traces -> one conversation record per scenario / session
# ---------------------------------------------------------------------------


def _render(messages: list[dict[str, Any]]) -> str:
    """The Homework 5 normalized text, with the tool name kept on tool lines.

    ``analysis.helpers.normalization._flatten`` writes ``tool_call: {args}``
    and drops the tool name. In Homework 5 we prefixed it back, so the judge
    can tell a policy lookup from an order lookup. Same here.
    """
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "step")
        if role == "tool_call":
            content = _text(message.get("arguments"))
        else:
            content = _text(message.get("text", message.get("content")))
        if not content:
            continue
        name = message.get("name")
        label = f"{role} {name}" if role in {"tool_call", "tool_result"} and name else role
        parts.append(f"{label}: {content}")
    return "\n".join(parts)


def build_conversations(
    traces: list[dict[str, Any]], key: str
) -> list[dict[str, Any]]:
    """Group turn-traces into conversation records.

    The record id is the FINAL trace id, so the verdict score lands on the
    last turn in Langfuse. ``tools`` and ``turn_count`` come from the trace
    evidence (tool-call observations and user messages), never from the
    agent's reply text, and feed the risk-group predicates.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        groups[trace["meta"][key]].append(trace)

    records = []
    for group_key in sorted(groups):  # stable order -> reproducible sample
        turns = sorted(groups[group_key], key=lambda t: (t["timestamp"] or "", t["id"]))
        messages = [m for turn in turns for m in turn["trace"]]
        tools = sorted(
            {str(m["name"]) for m in messages if m.get("role") == "tool_call" and m.get("name")}
        )
        records.append(
            {
                "id": turns[-1]["id"],
                key: group_key,
                "trace_ids": [t["id"] for t in turns],
                "tools": tools,
                "turn_count": sum(m.get("role") == "user" for m in messages),
                "text": _render(messages),
            }
        )
    return records


# ---------------------------------------------------------------------------
# sampling seed, history, chart
# ---------------------------------------------------------------------------


def label_seed(label: str) -> int:
    """A per-period seed: reruns of one period reproduce its sample (stable
    score ids), while different periods/days draw independent samples."""
    return int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)


def upsert_history(record: dict[str, Any], path: Path = HISTORY_PATH) -> None:
    """One line per period label, in time order; a rerun replaces its line instead of adding one."""
    lines = []
    if path.exists():
        lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines = [l for l in lines if l["label"] != record["label"]] + [record]
    lines.sort(key=lambda l: l["from"])  # ISO-8601 UTC strings sort chronologically
    path.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")


def write_chart(config: dict[str, Any]) -> None:
    from monitoring.chart import prevalence_chart

    lines = [json.loads(l) for l in HISTORY_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    points = [
        {k: l[k] for k in ("label", "corrected", "ci_low", "ci_high")}
        for l in lines
        if l.get("corrected") is not None
    ]
    if points:
        CHART_PATH.write_text(
            prevalence_chart(points, threshold=config["threshold"], mode=config["judge_mode"]),
            encoding="utf-8",
        )


def attach_to_monitor_trace(
    scores: list[dict[str, Any]], label: str, mode: str, record: dict[str, Any]
) -> str:
    """Give the period-level prevalence score a trace to live on.

    Langfuse v3 rejects a score with no trace, observation, session, or
    dataset run ("Bad request"), and the score contract leaves the period
    score's trace_id as None. So each period gets one small monitor trace
    whose id is seeded by (mode, label): a rerun reuses the same trace, and
    the score id stays stable. The trace has no session or scenario id, so
    the monitor itself never picks it up as traffic.
    """
    from langfuse import get_client

    client = get_client()
    trace_id = client.create_trace_id(seed=f"hw7-monitor|{mode}|{label}")
    with client.start_as_current_span(
        name="hw7-monitor", trace_context={"trace_id": trace_id}
    ) as span:
        span.update_trace(
            name=f"hw7-monitor {label}",
            tags=["hw7-monitor"],
            input={"period": label, "from": record["from"], "to": record["to"]},
            output={k: record.get(k) for k in ("raw", "corrected", "ci_low", "ci_high")},
            metadata={"judge_id": record["judge_id"], "model": record["model"]},
        )
    for score in scores:
        if score["trace_id"] is None:
            score["trace_id"] = trace_id
    return trace_id


def save_output(label: str, payload: dict[str, Any]) -> Path:
    """Local run output (ids, memberships, verdicts; no trace text). Uploaded as a CI artifact."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{label}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _confirm(yes: bool, n_calls: int, judge_model: str) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print("not confirmed: pass --yes to run the judge non-interactively")
        return False
    answer = input(f"Run {n_calls} judge calls on {judge_model}? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--period", help="a period label from monitoring/config.json")
    which.add_argument("--last-hours", type=float, help="monitor the previous N hours")
    parser.add_argument("--dry-run", action="store_true", help="stop before the judge")
    parser.add_argument("--yes", action="store_true", help="run the judge without asking")
    args = parser.parse_args(argv)

    from observability.instrument import load_env

    load_env()  # .env locally; in CI the secrets are already in the environment
    config = load_config()
    model = config["model"]

    # 1. The window.
    if args.period:
        matches = [p for p in config["periods"] if p["label"] == args.period]
        if not matches:
            raise SystemExit(f"no period {args.period!r} in {CONFIG_PATH.name}")
        period = matches[0]
        label, start, end = period["label"], _parse_utc(period["from"]), _parse_utc(period["to"])
        key = "scenario_id"
    else:
        end = datetime.now(timezone.utc).replace(microsecond=0)
        start = end - timedelta(hours=args.last_hours)
        label = f"daily-{end:%Y-%m-%d}"
        key = "session_id"
    print(f"period {label}: {_iso(start)} .. {_iso(end)}")

    # 2. Fetch and keep the eligible traces.
    traces = fetch_window(start, end)
    if args.period:
        wanted = monitoring_scenario_ids()
        eligible = [t for t in traces if t["meta"].get("scenario_id") in wanted]
        found = {t["meta"]["scenario_id"] for t in eligible}
        if found != wanted:
            missing = sorted(wanted - found)
            raise SystemExit(f"rejected: {len(missing)} scenario id(s) missing, e.g. {missing[:5]}")
    else:
        eligible = [t for t in traces if t["meta"].get("session_id")]
    print(f"  {len(traces)} traces in window, {len(eligible)} eligible")

    base_record = {
        "label": label,
        "from": _iso(start),
        "to": _iso(end),
        "judge_id": config["judge_id"],
        "model": model,
        "trace_count": len(eligible),
    }
    if not eligible:
        record = {**base_record, "conversation_count": 0, "random_count": 0,
                  "risk_count": 0, "judge_calls": 0, "raw": None, "corrected": None}
        save_output(label, record)
        print("  no eligible conversations: recorded a zero count, judge not called")
        return 0

    # 3. Validate the model, build conversations.
    check_models(eligible, model)
    conversations = build_conversations(eligible, key)
    if args.period and len(conversations) != len(monitoring_scenario_ids()):
        raise SystemExit(f"rejected: expected 50 conversations, built {len(conversations)}")
    print(f"  {len(conversations)} conversations, model {model}")

    # 4. Sample.
    groups = {name: DEFAULT_RISK_GROUPS[name] for name in config["risk_groups"]}
    plan = select_traces(conversations, config["random_rate"], groups, seed=label_seed(label))
    risk_ids = list(dict.fromkeys(c["id"] for members in plan["risk_groups"].values() for c in members))
    print(f"  random sample: {len(plan['random'])}")
    for name, members in plan["risk_groups"].items():
        print(f"  risk group {name}: {len(members)}")
    overlap = len({c["id"] for c in plan["random"]} & set(risk_ids))
    from monitoring.run_judges import load_monitoring_judge

    judge_model = load_monitoring_judge(config["judge_id"])["model"]
    print(f"  to judge (union): {len(plan['to_judge'])} conversations "
          f"({overlap} in both) = {len(plan['to_judge'])} judge calls on {judge_model}")

    output = {
        **base_record,
        "seed": label_seed(label),
        "random": [{"id": c["id"], key: c[key]} for c in plan["random"]],
        "risk_groups": {
            name: [{"id": c["id"], key: c[key]} for c in members]
            for name, members in plan["risk_groups"].items()
        },
    }
    if args.dry_run or not _confirm(args.yes, len(plan["to_judge"]), judge_model):
        print(f"  plan saved to {save_output(label, output).relative_to(ROOT)}; judge not called")
        return 0

    # 5. Judge the union once; split the verdicts by membership.
    from monitoring.run_judges import judge_sample, judge_test_data

    verdicts = judge_sample(
        config["judge_id"], [{"id": c["id"], "text": c["text"]} for c in plan["to_judge"]]
    )
    random_verdicts = {c["id"]: verdicts[c["id"]] for c in plan["random"]}
    risk_verdicts = {trace_id: verdicts[trace_id] for trace_id in risk_ids}

    # 6. Correct the random-sample rate for the judge's known errors.
    from monitoring.correct import corrected_mode_prevalence

    test_labels, test_preds = judge_test_data(config["judge_id"])
    estimate = corrected_mode_prevalence(list(random_verdicts.values()), test_labels, test_preds)

    # 7. Scores to Langfuse (stable ids: a rerun updates, never duplicates).
    from monitoring.write_scores import build_score_records, post_scores

    scores = build_score_records(config["judge_mode"], random_verdicts, risk_verdicts, estimate, label)
    monitor_trace = attach_to_monitor_trace(
        scores, label, config["judge_mode"], {**base_record, **estimate}
    )
    written = post_scores(scores)

    # 8. Local output, history, chart.
    for entry in output["random"]:
        entry["verdict"] = random_verdicts[entry["id"]]
    for members in output["risk_groups"].values():
        for entry in members:
            entry["verdict"] = risk_verdicts[entry["id"]]
    output["estimate"] = estimate
    save_output(label, output)

    risk_flags = sum(risk_verdicts.values())
    record = {
        **base_record,
        "conversation_count": len(conversations),
        "random_count": len(random_verdicts),
        "risk_count": len(risk_verdicts),
        "judge_calls": len(verdicts),
        "random_flags": sum(random_verdicts.values()),
        "risk_flags": risk_flags,
        "raw": estimate["raw"],
        "corrected": estimate["corrected"],
        "ci_low": estimate["ci_low"],
        "ci_high": estimate["ci_high"],
        "failure_sensitivity": estimate["failure_sensitivity"],
        "pass_specificity": estimate["pass_specificity"],
        "threshold": config["threshold"],
        "crossed_threshold": estimate["corrected"] > config["threshold"],
        "monitor_trace_id": monitor_trace,
        "run_at": _iso(datetime.now(timezone.utc)),
    }
    upsert_history(record)
    write_chart(config)
    print(f"  raw {estimate['raw']}  corrected {estimate['corrected']} "
          f"[{estimate['ci_low']}, {estimate['ci_high']}]  threshold {config['threshold']}")
    print(f"  risk flags {risk_flags}/{len(risk_verdicts)}; {written} scores written to Langfuse")
    return 0


if __name__ == "__main__":
    sys.exit(main())
