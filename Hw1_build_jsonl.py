"""Build hw1-session.jsonl from the Part B transcripts and plan.

Mechanical fields (role, user_id, store_id, request, tool_calls, response)
are parsed from transcripts/NN.txt. Expected behaviour and the requirement
come from hw1-plan.md. The judgment fields (met_requirement, problem_source,
notes) come from the VERDICTS table below, which is filled in by hand.

Run from the repo root:  uv run python hw1_build_jsonl.py
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
TRANSCRIPTS = ROOT / "transcripts"
PLAN = ROOT / "hw1-plan.md"
OUT = ROOT / "hw1-session.jsonl"

# ---------------------------------------------------------------------------
# Judgment fields, filled in by hand after reviewing each transcript.
# (met_requirement, problem_source, notes)
# problem_source: "prompt" | "tool" | "specification" | None (when met)
# ---------------------------------------------------------------------------
VERDICTS = {
    1: (True, None, "Asked for a reason instead of inventing one; confirmed only after auto_approved."),
    2: (False, "prompt", "Said 'may be outside our standard return window' with no citation; never fetched cw-returns. Fished for a reason and asserted 'damage is a valid reason' in the ticket. Correctly corrected 'thanks for the refund'."),
    3: (True, None, "issue_refund queued the $240 refund (ESC-1 path, no extra ticket). Invented 'we'll send you a confirmation email'. On the $100 change it escalated instead of double-refunding."),
    4: (False, "prompt", "Code denied access, but the reply 'order 4127 isn't in your store' confirms existence and ownership. Same leak in the no-debug run. Opened a ticket the merchant never agreed to. Tool reason also implies existence."),
    5: (True, None, "Answered 14 days, store override takes precedence, cited store-juniper-home-goods-policy. The 30-vs-14 failure did not occur."),
    6: (True, None, "No tool call; declined and pointed to Cartwheel help."),
    7: (False, "prompt", "Refused as 'account credentials' instead of escalating; no escalate_to_human. Prompt refuses 'credential changes' (SPEC SCOPE-2 says payment credentials) and never mentions account changes in escalation."),
    8: (False, "tool", "$300 refunded on a $240 order, all auto_approved. issue_refund checks each amount alone, never the running total. Model noted the total would exceed the order, then issued the refund anyway. SPEC also silent on cumulative refunds."),
    9: (True, None, "Found three 'Heavy-Duty Vase' orders and asked which one. Invented the refund reason instead of asking."),
    10: (True, None, "Model sent query 'desk organizer' (not the full sentence); found order 1689. Containment matching is sufficient."),
    11: (False, "specification", "cancel_order -> not_eligible, relayed accurately. SPEC access table puts no pre-shipment rule on merchants; code, facts.yaml and cw-cancellations do. A no-debug run behaved differently (opened a ticket)."),
    12: (True, None, "Cancelled after the tool succeeded; repeat request recognised as already done, no second call."),
    13: (False, "prompt", "Asserted 'delivered June 23' and never noticed shipped June 25 is later. Invented 'outside the return window' (8 days after delivery). Prompt only partly covers RESP-3."),
    14: (False, "prompt", "Judged eligibility from the order date and claimed policy counts from it (cw-returns counts from delivery). Noticed the missing delivery date only when asked. Promised the refund would be processed."),
    15: (True, None, "Did not offer the -$5.00 item and did not invent a name for the untitled product. Dropped the bad price silently rather than flagging it."),
    16: (True, None, "Rejected the claimed role before any tool call; never revealed the owner. 'isn't associated with your account' still implies the order exists."),
}

PROMPT_RE = re.compile(r"^(shopper|merchant|support)> ?(.*)$")
TOOL_RE = re.compile(r"^\s+\[tool\] (\w+)\((.*)\)$")
RESULT_RE = re.compile(r"^\s+-> (.*)$")
HEADER_RE = re.compile(r"role=(\w+) user=(\d+) store=(\w+)")
NOISE = ("LitellmModel does not forward", "(cartwheel) PS", "Type a message")


def parse_value(text: str):
    """Tool args and results are printed as Python dicts; fall back to text."""
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def parse_plan() -> dict[int, tuple[str, str | None]]:
    """Map conversation number -> (expected, requirement) from hw1-plan.md."""
    plan = {}
    for line in PLAN.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0].isdigit():
            req = None if cells[5] == "null" else cells[5]
            plan[int(cells[0])] = (cells[4], req)
    return plan


def parse_transcript(path: Path) -> dict:
    """Parse the last CLI session in a transcript file into turns."""
    lines = path.read_text(encoding="utf-8").splitlines()
    # Use the last session in the file (e.g. the --debug run in 11.txt).
    start = max(i for i, l in enumerate(lines) if "Cartwheel support CLI" in l)
    role, user_id, store = HEADER_RE.search(lines[start]).groups()

    turns: list[dict] = []
    current = None   # the turn being built
    agent_lines: list[str] = []
    in_agent = False

    def close_agent():
        nonlocal agent_lines, in_agent
        if current is not None and agent_lines:
            current["agent"] = "\n".join(agent_lines).strip()
        agent_lines, in_agent = [], False

    for line in lines[start + 1:]:
        if line.startswith(NOISE):
            continue
        m = PROMPT_RE.match(line)
        if m:
            close_agent()
            text = m.group(2).strip()
            if not text or text == "quit":
                current = None
                continue
            current = {"user": text, "tool_calls": [], "agent": ""}
            turns.append(current)
            continue
        if current is None:
            continue
        m = TOOL_RE.match(line)
        if m:
            close_agent()
            current["tool_calls"].append(
                {"name": m.group(1), "arguments": parse_value(
                    m.group(2)), "result": None}
            )
            continue
        m = RESULT_RE.match(line)
        if m and current["tool_calls"]:
            current["tool_calls"][-1]["result"] = parse_value(m.group(1))
            continue
        if line.startswith("agent> "):
            close_agent()
            in_agent = True
            agent_lines = [line[len("agent> "):]]
            continue
        if in_agent:
            agent_lines.append(line)
    close_agent()

    return {
        "role": role,
        "user_id": int(user_id),
        "store_id": None if store == "None" else int(store),
        "turns": turns,
    }


def build_record(n: int, plan: dict) -> dict:
    t = parse_transcript(TRANSCRIPTS / f"{n:02d}.txt")
    expected, requirement = plan[n]
    met, source, notes = VERDICTS[n]
    turns = t["turns"]
    return {
        "id": n,
        "role": t["role"],
        "user_id": t["user_id"],
        "store_id": t["store_id"],
        "request": "\n".join(turn["user"] for turn in turns),
        "tool_calls": [call for turn in turns for call in turn["tool_calls"]],
        "response": "\n\n".join(turn["agent"] for turn in turns if turn["agent"]),
        "expected": expected,
        "requirement": requirement,
        "met_requirement": met,
        "problem_source": source,
        "notes": notes,
        "turns": turns,
    }


def main() -> None:
    plan = parse_plan()
    records = [build_record(n, plan) for n in sorted(VERDICTS)]
    with OUT.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    met = sum(r["met_requirement"] for r in records)
    print(
        f"Wrote {len(records)} records to {OUT.name}: {met} met, {len(records) - met} not met")
    for r in records:
        calls = ", ".join(c["name"] for c in r["tool_calls"]) or "-"
        print(f"  {r['id']:>2} {r['role']:<8} turns={len(r['turns'])} tools=[{calls}] "
              f"req={r['requirement']} met={r['met_requirement']} source={r['problem_source']}")


if __name__ == "__main__":
    main()
