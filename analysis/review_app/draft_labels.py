"""Part E: draft one Pass/Fail per (reviewed trace, final mode) from the review evidence.

Drafts are not labels. The Label view shows them pre-selected; a label exists
only once the reviewer saves the row, which writes labels/<mode>.jsonl and the
Langfuse score. Basis per cell:

  fail       trace is a positive example of the mode (evidence: the note)
  close_neg  trace is a close negative of the mode (evidence: the boundary note)
  unchecked  neither; drafted Pass, but the first-failure stopping rule means
             nobody has checked this mode on this trace yet

Also prints first-failure annotations whose trace is not a positive of any
final mode, so none is silently dropped.

Usage: uv run python -m analysis.review_app.draft_labels
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analysis.helpers import _state

CACHE = Path(__file__).resolve().parent / "cache" / "sessions.json"
FINAL = {"candidate", "confirmed"}


def main() -> None:
    sessions = {s["scenario_id"]: s for s in json.loads(CACHE.read_text(encoding="utf-8"))["sessions"]}
    manifest = _state.read_json(_state.state_path("sample_manifest.json"))
    modes = [m for m in _state.read_json(_state.state_path("patterns.json"))["modes"] if m["status"] in FINAL]
    anns = [a for a in _state.read_json(_state.state_path("annotations.json"))["annotations"] if a.get("status") != "retracted"]
    suggs = _state.read_json(_state.state_path("suggestions.json"))

    review = [it["scenario_id"] for b in manifest["batches"] for it in b["items"]]
    traces = [t["trace_id"] for sid in review for t in sessions[sid]["turns"]]

    def note_for(mode: dict[str, Any], tid: str, decided: str) -> str:
        """Best human-written evidence for this trace and mode."""
        for a in anns:
            if a["trace_id"] == tid and a["id"] in mode["annotation_ids"] and a.get("note"):
                return a["note"]
        for g in suggs:
            if g.get("mode") == mode["name"] and g.get("trace_id") == tid and g.get("status") == decided:
                return g.get("decision_note") or ""
        for a in anns:
            if a["trace_id"] == tid and a.get("kind") == "open_code" and a.get("note"):
                return a["note"]
        return ""

    drafts: dict[str, dict[str, dict[str, str | int]]] = {}
    counts: dict[str, dict[str, int]] = {}
    for m in modes:
        pos, neg = set(m["example_trace_ids"]), set(m["close_negative_trace_ids"])
        drafts[m["name"]], c = {}, {"fail": 0, "close_neg": 0, "unchecked": 0}
        for tid in traces:
            if tid in pos:
                d = {"label": 1, "basis": "fail", "evidence": note_for(m, tid, "accepted")}
            elif tid in neg:
                d = {"label": 0, "basis": "close_neg", "evidence": note_for(m, tid, "rejected")}
            else:
                d = {"label": 0, "basis": "unchecked", "evidence": ""}
            drafts[m["name"]][tid] = d
            c[d["basis"]] += 1
        counts[m["name"]] = c

    out = _state.state_path("label_drafts.json")
    _state.write_json(out, {"modes": [m["name"] for m in modes], "drafts": drafts})
    print(f"{len(review)} sessions, {len(traces)} traces, {len(modes)} modes -> {out}")
    for name, c in counts.items():
        print(f"  {name:28} fail {c['fail']:3}  close_neg {c['close_neg']:3}  unchecked {c['unchecked']:3}")

    positives = {tid for m in modes for tid in m["example_trace_ids"]}
    unmapped = [a for a in anns if a.get("first_failure") and a["trace_id"] not in positives and a["scenario_id"] in review]
    print(f"\nfirst-failure annotations not a positive of any final mode: {len(unmapped)}")
    for a in sorted(unmapped, key=lambda a: a["scenario_id"]):
        print(f"  {a['scenario_id']} {a['trace_id'][:8]} [{a.get('batch')}] {a['note'][:110]}")


if __name__ == "__main__":
    main()
