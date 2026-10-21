"""Homework 2 helper: list recent Langfuse traces and build hw2-traces.json.

Run on the machine where Langfuse is running (it reads LANGFUSE_* from .env):

    uv run python hw2_traces.py --list                 # recent traces, newest first
    uv run python hw2_traces.py TRACE_ID [TRACE_ID]     # summary + span count
    uv run python hw2_traces.py TRACE_A TRACE_B --write # also write hw2-traces.json

A trace's observations are its spans (the root cartwheel.session_message span,
Agent Workflow, agent, model calls, and tool calls). Tool order comes from the
spans whose gen_ai.operation.name is execute_tool, sorted by start time.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from observability.instrument import load_env

ROOT_SPAN = "cartwheel.session_message"
OUTPUT = Path("hw2-traces.json")


def _plain(value: Any) -> Any:
    """Turn a Langfuse SDK response model into plain JSON data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "json") and hasattr(value, "dict"):
        return json.loads(value.json(by_alias=True))
    return value


def _attributes(observation: dict[str, Any]) -> dict[str, Any]:
    """OpenTelemetry span attributes live under metadata.attributes."""
    metadata = observation.get("metadata") or {}
    attributes = metadata.get("attributes") if isinstance(metadata, dict) else None
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except ValueError:
            attributes = None
    return attributes if isinstance(attributes, dict) else {}


def summarize(trace: dict[str, Any], host: str) -> dict[str, Any]:
    observations = sorted(trace.get("observations") or [], key=lambda o: o.get("startTime") or "")
    root = next((o for o in observations if o.get("name") == ROOT_SPAN and _attributes(o)), {})
    root_attrs = _attributes(root)
    tools = [
        o.get("name")
        for o in observations
        if _attributes(o).get("gen_ai.operation.name") == "execute_tool"
    ]
    errored = any(o.get("level") == "ERROR" for o in observations)
    path = trace.get("htmlPath") or f"/project/{trace.get('projectId', 'cartwheel-dev')}/traces/{trace['id']}"
    return {
        "trace_id": trace["id"],
        "permalink": host.rstrip("/") + path,
        "prompt_version": root_attrs.get("cartwheel.prompt_version"),
        "user_role": root_attrs.get("cartwheel.user_role"),
        "user_id": root_attrs.get("cartwheel.user_id"),
        "tool_order": tools,
        "final_status": "error" if errored else "completed",
        "_span_count": len(observations),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("trace_ids", nargs="*")
    parser.add_argument("--list", action="store_true", help="list recent traces")
    parser.add_argument("--write", action="store_true", help=f"write {OUTPUT}")
    args = parser.parse_args()

    load_env()
    from langfuse import Langfuse

    client = Langfuse()
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")

    if args.list:
        for item in client.api.trace.list(limit=20).data:
            full = _plain(client.api.trace.get(item.id))
            s = summarize(full, host)
            print(f"{full.get('timestamp', '')[:19]}  {s['trace_id']}  {s['user_role']}/{s['user_id']}"
                  f"  v={s['prompt_version']}  tools={s['tool_order']}")
        return

    records = []
    for trace_id in args.trace_ids:
        record = summarize(_plain(client.api.trace.get(trace_id)), host)
        print(json.dumps(record, indent=2))
        print(f"span count for {trace_id}: {record['_span_count']}\n")
        records.append(record)

    if args.write:
        if len(records) != 2:
            raise SystemExit("hw2-traces.json needs exactly two trace ids")
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]
        OUTPUT.write_text(json.dumps(clean, indent=2) + "\n")
        print(f"wrote {OUTPUT} with {len(clean)} traces")


if __name__ == "__main__":
    main()
