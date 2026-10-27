"""HW4 review server: serves the review UI and persists review state.

Standard library only, like the reference ``analysis/server.py``. Sessions
come from the cache written by ``build_cache.py``; everything the reviewer
produces is stored under ``analysis/state/``:

  - ``annotations.json``   open codes and "no failure observed" notes
  - ``patterns.json``      the taxonomy (modes, boundaries, revision history)
  - ``suggestions.json``   AI suggestions with accept/reject decisions
  - ``labels/<mode>.jsonl`` append-only binary judgments, mirrored to Langfuse
  - ``sample_manifest.json`` the review batches (written by the selection step)

Run (from the repo root), then open http://localhost:8020:

    uv run python -m analysis.review_app.server
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agent.agent import SYSTEM_PROMPT_TEMPLATE, prompt_version
from analysis.helpers import _state, langfuse_io
from observability.instrument import load_env

APP_DIR = Path(__file__).resolve().parent
REPO = APP_DIR.parents[1]
CACHE = APP_DIR / "cache" / "sessions.json"
POLICIES = REPO / "data" / "policies"

# Whole-file state the UI reads and replaces. Labels are separate because
# they are append-only and each write also goes to Langfuse.
STATE_FILES = {
    "annotations": ("annotations.json", {"annotations": []}),
    "patterns": ("patterns.json", {"modes": []}),
    "suggestions": ("suggestions.json", []),
}
MODE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
POLICY_ID = re.compile(r"^(cw|store)-[a-z0-9-]+$")
# The course demo label file; a mode with this name would overwrite it.
RESERVED_MODES = {"unsupported_policy_claim"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state(name: str) -> Any:
    filename, default = STATE_FILES[name]
    return _state.read_json(_state.state_path(filename), default=default)


def _live_labels() -> dict[str, dict[str, dict[str, Any]]]:
    """Collapse each mode's label log to the current label per trace."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    labels_dir = _state.state_path("labels")
    modes = {m["name"] for m in _read_state("patterns").get("modes", [])}
    for mode in sorted(modes):
        live: dict[str, dict[str, Any]] = {}
        for row in _state.read_jsonl(labels_dir / f"{mode}.jsonl"):
            if not row.get("superseded_by"):
                live[row["trace_id"]] = row
        out[mode] = live
    return out


def _write_label(body: dict[str, Any]) -> dict[str, Any]:
    """Write one judgment to Langfuse, then append it locally.

    The local record is written even when Langfuse fails, so an outage never
    loses a judgment; its ``langfuse`` field records whether the canonical
    write succeeded, so unsynced labels can be found and resent.
    """
    mode, trace_id, label = body.get("mode"), body.get("trace_id"), body.get("label")
    if not isinstance(mode, str) or not MODE_NAME.match(mode) or mode in RESERVED_MODES:
        raise ValueError(f"invalid mode name: {mode!r}")
    if label not in (0, 1) or not isinstance(trace_id, str):
        raise ValueError("label must be 0 or 1 with a trace_id")

    path = _state.state_path("labels", f"{mode}.jsonl")
    rows = _state.read_jsonl(path)
    n = sum(1 for r in rows if r["trace_id"] == trace_id)
    record = {
        "trace_id": trace_id,
        "label": label,
        "source": "human",
        "ts": _now(),
        "label_id": f"{trace_id}#{n}",
        "session_id": body.get("session_id"),
        "scenario_id": body.get("scenario_id"),
        "evidence": body.get("evidence") or "",
    }
    record["langfuse"] = "skipped (not configured)"
    if langfuse_io.is_configured():
        try:
            langfuse_io.write_label_score(
                trace_id=trace_id,
                mode=mode,
                label=label,
                comment=record["evidence"] or None,
                score_id=f"{trace_id}-{mode}",
            )
            record["langfuse"] = "ok"
        except Exception as exc:  # network path; keep the local copy
            record["langfuse"] = f"error: {exc}"

    for row in rows:
        if row["trace_id"] == trace_id and not row.get("superseded_by"):
            row["superseded_by"] = record["label_id"]
    rows.append(record)
    _state.write_jsonl(path, rows)
    return record


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        return

    def _send(self, data: Any, status: int = 200, content_type: str = "application/json") -> None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send((APP_DIR / "index.html").read_bytes(), content_type="text/html; charset=utf-8")
        elif url.path == "/api/sessions":
            if not CACHE.exists():
                self._send({"error": "no cache; run analysis.review_app.build_cache"}, 503)
                return
            self._send(CACHE.read_bytes())
        elif url.path == "/api/state":
            self._send(
                {
                    **{name: _read_state(name) for name in STATE_FILES},
                    "manifest": _state.read_json(_state.state_path("sample_manifest.json"), default={}),
                    "labels": _live_labels(),
                    "langfuse": langfuse_io.is_configured(),
                }
            )
        elif url.path == "/api/policy":
            policy_id = parse_qs(url.query).get("id", [""])[0]
            path = POLICIES / f"{policy_id}.md"
            if not POLICY_ID.match(policy_id) or not path.exists():
                self._send({"error": f"unknown policy {policy_id!r}"}, 404)
                return
            self._send({"id": policy_id, "text": path.read_text(encoding="utf-8")})
        elif url.path == "/api/prompt":
            self._send(
                {
                    "version": prompt_version(),
                    "template": SYSTEM_PROMPT_TEMPLATE,
                    "policies": sorted(p.stem for p in POLICIES.glob("*.md")),
                }
            )
        else:
            self._send({"error": f"unknown path {url.path}"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        name = urlparse(self.path).path.removeprefix("/api/")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"null")
        except json.JSONDecodeError:
            self._send({"error": "expected JSON"}, 400)
            return
        try:
            if name == "label":
                self._send(_write_label(body))
            elif name in STATE_FILES:
                if name == "patterns":
                    for mode in body.get("modes", []):
                        if not MODE_NAME.match(mode.get("name", "")) or mode["name"] in RESERVED_MODES:
                            raise ValueError(f"invalid mode name: {mode.get('name')!r}")
                _state.write_json(_state.state_path(STATE_FILES[name][0]), body)
                self._send({"ok": True})
            else:
                self._send({"error": f"cannot POST to {name}"}, 404)
        except ValueError as exc:
            self._send({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    load_env()  # LANGFUSE_* from .env, so label writes reach Langfuse
    print(f"Langfuse score sync: {'on' if langfuse_io.is_configured() else 'OFF'}")
    print(f"state dir: {_state.state_root()}")
    print(f"open http://localhost:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
