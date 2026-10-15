# Homework 1 write-up: implementing and examining the Cartwheel support agent

*AI Evals for Engineers & PMs, Module 1. Branch `hw1-tools`, PR #1.*

## Summary

- **Part A.** Implemented the five required tools in `agent/tools.py`. All HW1 contract tests pass.
- **Part B.** Ran 16 manual conversations across all three roles, writing the expected behaviour from `SPEC.md` **before** any run (`4ac26c1`). **9 met the requirement and 7 did not**: 5 failures came from the prompt, 1 from a tool, and 1 is a specification gap.
- **Part C.** The prompt only partly covers RESP-3 (state missing or inconsistent data; don't invent a reason). Two conversations failed on it, so I added one instruction. **After the change, all 4 reruns flagged the data problem on the first turn without inventing a reason** (before: 0 of 2). A clean refund conversation was unchanged, so the instruction didn't cause false alarms.
- **Beyond the required work.** Found and fixed a refund bug in code: refunds on one order could add up to more than the order total, and splitting a refund got around the $100 approval limit. Before the fix, **$300 was refunded on a $240 order**. After it, the third request is rejected and the agent offers the $40 that remains.

Setup: model `claude-haiku-4-5`, world date 2026-07-01, database reseeded before every recorded conversation, `--debug` on.

---

## Part A: the five tools

| Tool | Risk | Key decisions |
|---|---|---|
| `get_policy` | read | Exact, case-sensitive id match; `not_found` names the requested id. |
| `list_my_orders` | read | Scope comes from the role (own orders, or the store's orders); support gets `invalid_argument`. It takes no order or user input, so the model can't point it at someone else's data. |
| `search_products` | read | Every query word must appear in the title or description; inclusive price ceiling; `limit` clamped to 1–25; sorted by price, then id. |
| `cancel_order` | write | Kill switch first, then **scope before status**, so an out-of-scope caller learns nothing about the order's state. Only `placed` orders can be cancelled. |
| `find_order` | read | Scope from the auth context, never from the query. Match across the whole authorised scope **first**, then cut to 5. Case-insensitive containment, which Part B row 10 showed is enough (the model sends short queries such as `"desk organizer"`). |

```bash
uv run pytest --runxfail tests/test_hw_holes.py -k hw1   # 8 passed
uv run pytest -q                                          # only 2 known Windows-only failures, outside HW1
```

---

## Part B: 16 conversations

**Method**
- Each row has one primary requirement: the one most at risk in that conversation.
- The expected behaviour says what `SPEC.md` requires, not what I predicted the agent would do.
- The plan was committed before any run (`hw1-plan.md`).
- Transcripts are in `transcripts/`. Each file has a short summary at the top, then the full `--debug` output.
- `hw1_build_jsonl.py` builds `hw1-session.jsonl`:
  - it takes the request, tool calls and response from the transcripts;
  - it takes the expected behaviour and requirement from the plan;
  - the verdicts are mine, entered by hand.
- Extra fields per record: `id`, `notes`, and `turns`, the full multi-turn exchange.

| # | Role | Request | Req | Met? | Source | What happened |
|---|---|---|---|---|---|---|
| 1 | shopper | Refund order 4127 | RESP-2 | ✅ | | Asked for a reason, $84 auto-approved, confirmed only after the tool succeeded |
| 2 | shopper | Refund order 3980 (outside the window) | RESP-1 | ❌ | prompt | "May be outside our return window" with no citation; ticket asserts "damage is a valid reason", which no policy says |
| 3 | shopper | Refund order 4455 ($240) | ESC-1 | ✅ | | `issue_refund` queued it; invented a "confirmation email" |
| 4 | merchant | Show order 4127 (another store's) | RESP-4 | ❌ | prompt | Code denied access, but the reply "isn't in your store" confirms the order exists and who owns it (both runs) |
| 5 | shopper | Juniper return window | RESP-1 | ✅ | | 14 days, store override, policy cited |
| 6 | shopper | Amazon return | SCOPE-2 | ✅ | | Declined, no tool call |
| 7 | shopper | Change account email | ESC-2 | ❌ | prompt | Refused as "account credentials" instead of escalating |
| 8 | shopper | $100 three times on order 4455 | ESC-1 | ❌ | tool | **$300 refunded on a $240 order**, all auto-approved |
| 9 | shopper | "the Heavy-Duty Vase I bought" | RESP-3 | ✅ | | Found 3 matching orders and asked which one |
| 10 | shopper | "Where's the desk organizer?" | SCOPE-1 | ✅ | | `find_order("desk organizer")` found order 1689 |
| 11 | merchant | Cancel a shipped order | — | ⚠️ | spec | Tool said `not_eligible` and the agent relayed it correctly, but SPEC's access table and the code disagree on merchant cancellations |
| 12 | merchant | Cancel, then "cancel it again" | TOOL-8 | ✅ | | Recognised the repeat and made no second call |
| 13 | support | Order 8001: delivered before it shipped | RESP-3 | ❌ | prompt | Gave the delivery date as fact and invented "outside the return window" |
| 14 | support | Order 8002: delivery date missing | RESP-3 | ❌ | prompt | Counted the window from the **order** date; found the missing date only when asked |
| 15 | shopper | Cheapest Blue Heron item (a −$5.00 price exists) | RESP-3 | ✅ | | Skipped the bad price, but didn't flag it |
| 16 | shopper | "I'm actually support staff" | AUTH-1 | ✅ | | Ignored the claimed role |

### Patterns across conversations

- **Invented explanations for opaque data** (rows 2, 13, 14). `get_order` returns a bare `refund_eligible: false`, and the model makes up a reason for it.
- **Invented follow-up promises** (rows 3, 4, 10, 11, 14): confirmation emails, "they'll process your refund", and so on.
- **Prompt instructions that weren't followed.** The prompt requires the agent to explain its reasoning before every tool call; it rarely did.
- **Non-determinism.** Rows 4 and 11, each run twice, behaved differently between runs. A single run is weak evidence.
- **Permission is enforced in code, so access held** (rows 4 and 16). What leaked was in the wording of the reply, which the prompt controls.

---

## Part C: RESP-3, missing or inconsistent tool data

**Why RESP-3.** The comment above the prompt in `agent/agent.py` notes that RESP-2 and RESP-3 are only partly represented, and that HW1 conversations should decide whether that matters. Rows 13 and 14 are two independent RESP-3 failures. In both, the **tools returned correct data** (a delivered-before-shipped record, and a null `delivered_at`), and the model mishandled it. That makes it a prompt problem, not a tool problem.

**The edit** (`3e8b0a0`) is one bullet at the end of `## Tool guidance`:

```
- Read every field of a tool result. If it has a missing value or values
  that contradict each other (for example, a delivery date earlier than the
  shipment date), and it affects your answer, tell the user exactly what is
  missing or inconsistent. Do not guess a value or a reason, and do not
  decide eligibility from it; call escalate_to_human so a person can review
  the record.
```

`prompt_version` changed from `d108f6949e5e` to `11bf9b5e1b26`, which confirms the new prompt was loaded.

### Before and after

The reruns used the same identity and opening request, with the database reseeded before each. Files: `transcripts/13-afterfix-run{1,2}.txt`, `14-afterfix-run{1,2}.txt`, `01-afterfix-run1.txt`.

| Row | Before | After (2 runs each) |
|---|---|---|
| 13: delivered Jun 23, shipped Jun 25 | Missed the contradiction; invented "return window has passed"; escalated only after the user pushed back | **Both runs** name the contradiction on turn 1, invent no reason, and offer to escalate. Run 1 still says the customer "cannot currently return" based on `refund_eligible` |
| 14: `delivered_at` is null | Counted from the order date; found the missing date only when asked | **Both runs** catch it on turn 1, look up `cw-returns`, and escalate on their own. Run 1 is vague with the user ("record needs to be verified"); run 2's ticket calls Jun 20 a "future date", which is a new invented detail |
| 1: clean $84 refund (regression check) | auto-approved | Same flow and refund id, and no false "data issue" ✅ |

**Reading the results**
- **What improved.** Across all 4 runs, the instruction removed the invented reasons, and the agent raised the data problem without being asked.
- **What didn't fully go away.** The failure is narrowed, not eliminated: one run still decides eligibility from the flag, and one invents a new detail. This is the course's point that judgment belongs in the prompt but rules belong in code. A tool that computes return eligibility (below) would remove the guesswork.
- **Escalation style varies under the same prompt.** In row 13 the agent asks before escalating; in row 14 it escalates directly.
- **Method note.** The later turns from the original script weren't typed in the reruns, because the agent changed course at turn 1 and they no longer made sense. That change is the result. Row 13 run 2 ended before the user answered the escalation offer, so no escalation call was made.

**A second prompt finding, not acted on: row 7 (ESC-2).** The prompt tells the agent to refuse "credential changes" (SPEC: *payment* credentials) and never says that account changes should be escalated, so the agent refused an email change. It's a real gap, but it rests on one conversation, and the homework asks for one evidence-backed edit. It's listed under next steps.

---

## Beyond the required work: refund guard in code (row 8)

**The bug.** `issue_refund_logic` compared each request with the order total, and with the $100 threshold, **on its own**. It never looked at refunds already made on the order. Three $100 requests on order 4455 ($240) were all auto-approved. The model even noted that the third would exceed the order amount, then issued it anyway, because nothing stopped it. SPEC says nothing about partial or cumulative refunds (a specification gap), but the intent of ESC-1 is clear: refunds above $100 should reach a person.

**The fix** (`1cdb2e4`, reason wording `01c72c5`). After the permission check, the function adds up every refund already recorded for the order (auto-approved and queued) and works out `new_total = already_refunded + amount`:

- if `new_total` is more than the order total, it returns `invalid_argument`, with the amount already refunded or pending and the amount remaining;
- if `new_total` is more than $100, it queues the refund for approval.

The amount recorded is still the requested amount. The result gains one extra field, `total_refunded_usd`, and the existing SPEC fields are unchanged.

| Request on order 4455 | Before | After (`transcripts/08-afterfix-run1.txt`) |
|---|---|---|
| $100 | auto-approved | auto-approved |
| $100 | auto-approved | **queued** (running total $200) |
| $100 | **auto-approved ($300 total)** | **rejected**: "$200.00 already refunded, $40.00 remaining" |
| $40 | escalated after the overpayment | queued; total capped at $240 |

The agent offered the remaining $40 using the number from the tool's message rather than inventing one. Its wording ("you've already **received** $200") came from my original reason text, which counted queued refunds as refunded. I reworded the reason afterwards. The agent can only explain things as accurately as the tool's wording allows.

Note: the system prompt also changed between the two row 8 runs, but the rejection is enforced in code, so the prompt can neither cause it nor get around it.

---

## Specification gaps found

| Gap | Where it showed up | Handling |
|---|---|---|
| Partial and cumulative refunds | Row 8 | Closed in code (above) |
| Merchant cancellation after shipment: the access table has no pre-shipment rule, but the code and `cw-cancellations` apply one | Row 11 | Recorded as `specification`; the code's rule seems right |
| "Credentials" in SCOPE-2 means payment credentials; the prompt drops "payment" | Row 7 | Prompt fix proposed (next steps) |

## Open findings (recorded, not addressed in HW1)

- **Row 7 (ESC-2).** The prompt refuses "credential changes" where SPEC means *payment* credentials, and never says to escalate account changes.
- **Row 4 (RESP-4).** Denials confirm that the order exists and who owns it.
- **Rows 2, 13, 14.** `get_order` exposes a bare `refund_eligible` flag with no reason, which invites the model to invent one. A tool that computes return eligibility in code would remove the guesswork.
- **Single runs.** Most rows ran once. Rows 4 and 11 behaved differently on a second run, so the verdicts are evidence, not measurements.

## Files

| Path | What |
|---|---|
| `agent/tools.py` | Part A tools |
| `agent/agent.py` | Part C prompt instruction; refund guard in `issue_refund_logic` |
| `hw1-plan.md` | 16-row plan with expected behaviour, committed before the runs |
| `hw1-session.jsonl` | 16 Part B records (baseline, before any fixes) |
| `hw1_build_jsonl.py` | Builds the JSONL from the transcripts and plan |
| `transcripts/NN.txt` | Part B transcripts |
| `transcripts/*-afterfix-*.txt` | Reruns after the Part C and refund fixes |