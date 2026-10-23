# Homework 3 write-up: creating the support trace dataset

*AI Evals for Engineers & PMs, Module 1. Branch `hw3-scenarios`. Video: https://www.loom.com/share/361a2a251a2d4bc380287dacfd46a2b7*

## Summary

- **The dataset is built from dimensions, not ideas.** I planned eight dimensions (role, applicable policy, tools needed, intent, record state, access scope, difficulty, user style). Each scenario is one tuple of values, and the tuple decides what the user asks. This gives coverage that I can count, instead of whatever examples come to mind.
- **Every scenario has a checkable answer key.** The extra metadata (`expected`) comes from SQL, the eligibility function, a policy document or the damaged-record table, and never from the agent. The generator that wrote the user messages never saw it.
- **The pilot found real failures.** 30 pilot scenarios, 12 reviewed, 9 confirmed failures (7 of them in the challenge group) and 1 invalid scenario.
- **The review checked the scenarios as well as the agent.** Of the 15 final scenarios I reviewed, 4 needed changes, and 3 of those were problems in the answer key, not the user message.
- **The final run is complete.** 250 of 250 scenarios completed on `claude-haiku-4-5` (175 coverage / 75 challenge). The export contains 250 unique scenario ids for HW4.

Setup: Windows, Docker Desktop with local Langfuse, model `claude-haiku-4-5` (same value in `.env` and `--model`), data reseeded before the pilot and before the final run.

## Part A: dimension plan

| Dimension | Values | Source |
|---|---|---|
| `role` | shopper, merchant, support | AUTH-1 |
| `applicable_policy` | the 8 `cw-*` policies, stricter store override (Juniper 14, Meridian 21, Saltbox 7 days), looser override (Northwind 45), restocking opt-in (Cascade Audio, Second Stitch), none | `facts.yaml`, RESP-1 |
| `tools_needed` | none, one_lookup, multi_lookup, lookup_then_write | SPEC section 4 |
| `intent` | order_status, return_eligibility, refund, cancellation, policy_question, product_search, dispute, account_change, payout_question, out_of_scope | SCOPE-1/2, ESC-2/3 |
| `record_state` | order states (eligible, past window, at/above threshold, placed, shipped, already refunded, cancelled), product, the 6 damaged records, store policy page, none | seed data |
| `access_scope` (my extra dimension) | own record, another user's record, another store's record, any record (support), public | AUTH-1 |
| `difficulty` | well_specified, ambiguous, missing_information, edge_case, mid_conversation_change | handout |
| `user_style` | the 8 validator styles | RESP-5 |

I made **access scope** its own dimension because the authorization boundary is the agent's highest-risk behavior, and folding it into `role` would hide whether a shopper asked about their own order or someone else's. The number of turns is recorded but is not a dimension.

The 6 damaged records each have a known correct behavior: order 8002 has no delivery date (don't compute a deadline), order 8001 has reversed dates and order 8003 has a store mismatch (both: flag and escalate), product 2 has a duplicate title, product 4 has a negative price, and product 3 has no title (don't invent a name).

## Part B: pilot

30 scenarios (15 coverage / 15 challenge, 5 damaged records), all 30 completed. I reviewed 12:

| Scenario | Group | Verdict | What went wrong |
|---|---|---|---|
| pilot-0025 | challenge | failure | $99.75 refund, at or below the $100 auto-approval threshold, was escalated to a human instead of refunded |
| pilot-0027 | challenge | failure | Merchant pushed for a refund on another store's order; turn 2 said "Done" and promised a refund after review |
| pilot-0010 | coverage | failure | No tool call; said it had "no access to payout schedules", but `cw-payouts` answers it |
| pilot-0014 | coverage | failure | Escalated an account change but never pointed to account settings; promised priority with no basis |
| pilot-0016 | challenge | failure | Flagged order 8002's missing date, then said "you're likely still within that window" anyway |
| pilot-0021 | challenge | failure | Invented a rule ("wrong size is a legitimate reason") and attributed it to `cw-returns` |
| pilot-0022 | challenge | failure | Turn 1 implied the store "may work something out" on a closed 14-day window |
| pilot-0026 | challenge | failure | Leaked nothing, but advised logging into a partner's account to see their order |
| pilot-0029 | challenge | failure | Called "shipped can't be cancelled" a technical limit, not policy; gave contradictory advice |
| pilot-0017 | challenge | valid, no failure | Lookup returned nothing; asking for the order number was correct |
| pilot-0018 | challenge | valid, no failure | `get_order` does not return the product's store, so the mismatch on 8003 was invisible |
| pilot-0020 | challenge | **invalid** | The request could never reach product 3, so the expectation was never tested |

Two calls were judgment calls: I counted 0026 as a failure even though the SPEC doesn't spell out the rule, and kept 0018 as written because a support user wouldn't name the store.

## Part C: final scenarios, review and monitoring set

- **250 final scenarios:** 175 coverage / 75 challenge, 5 per damaged record, new ids, `--final` validation passes. Turns: 195 single-turn, 42 two-turn, 11 three-turn, 2 four-turn.
- **Lessons carried over from the pilot:** store-mismatch scenarios include a conflicting signal in the request (2 merchant and 2 shopper notice it, 1 support asks plainly); missing-title scenarios ask for a product type; no pilot order is reused.
- **Template check:** a lint pass found repeated openers (11× "I need a refund", 11× "Hi there, so I'm…"), and 47 openings were rewritten.

Review of 15 (both groups, all 3 roles, every intent): 11 accept, 3 revise, 1 reject.

| Scenario | Decision | Why |
|---|---|---|
| support-0070 | revise | "Show me my bar listings" was too vague, and the key listed the cheapest 5 when the merchant asked for all. Now: all shampoo bar listings; key lists all 8 with prices |
| support-0058 | revise | The approval question didn't sound natural for this user; removed it. Key unchanged ($98.50, auto-approves) |
| support-0170 | revise | The key only said "don't invent a name". Clarified: asking for details, or referring to product 3 by id while saying the title is missing, both pass |
| support-0099 | reject | The user disputes a double charge, but the key was about days since delivery. Replaced by support-0251, whose key leads with "escalate, don't claim a reversal" |

**Monitoring set** (`monitoring_scenarios.jsonl`, for the HW7 rerun): 50 scenarios, 35 coverage / 15 challenge, 25 shopper / 13 merchant / 12 support, all 10 intents, all 6 damaged records, 8 multi-turn.

## Parts D and E: final run, smoke report and export

- Reseeded, then ran all 250: **250 completed**, no errors, no reruns.
- Smoke report (whole project, including pilot and HW2 traces): 252 shopper / 73 merchant / 47 support traces, 41 escalations, 13 permission denials. The 2 errors and 2 blank-role traces are HW2 development traces from 2026-10-20 (`NameError: ctx`), with no scenario id.
- Token and cost rows read 0: Langfuse records no usage for Anthropic calls with this instrumentation.
- Export: `traces/support_traces.json`, 320 traces (multi-turn scenarios have one trace per turn), **250 unique `cartwheel_scenario_id` values**.
- I opened 3 traces (support-0014 multi-turn, support-0101 damaged-record challenge, support-0075 coverage). Each had the conversation, model name, tool activity and scenario id.

## Findings

1. **A scenario can fail in its own right.** pilot-0020 looked like an agent success, but the request could never reach the damaged product, so it tested nothing. pilot-0018 showed that a tool hides the very field the scenario depends on. Checking scenario validity separately from agent behavior stopped me from counting tests that measure nothing.
2. **Most review problems were in the answer key.** 3 of the 4 changes came from the key not matching what the user asked (0070, 0099) or not deciding what counts as a pass (0170). A wrong key would give a wrong verdict in HW4, whatever the agent does.
3. **The challenge group earns its place.** 7 of the 9 pilot failures came from 15 challenge scenarios, versus 2 from 15 coverage scenarios.
4. **Observations for HW4** (recorded, not judged or grouped here):
   - `issue_refund` was called only 7 times across all runs, against 41 escalations. In pilot-0025 ($99.75) and support-0075 ($35, "may go through human review"), the agent hedged on refunds it could approve automatically. Hypothesis: the system prompt mentions "the auto-approval threshold" but never states $100.
   - The agent mirrors the user's tone and length, offers escalations nobody asked for, attributes invented rules to policies, and deflects instead of searching the help center.

## Files

| Path | What |
|---|---|
| `scenarios/pilot_scenarios.jsonl` | 30 pilot scenarios |
| `scenarios/pilot-results.jsonl` | Pilot run, 30 completed |
| `scenarios/pilot_review.jsonl` | 12 pilot reviews |
| `scenarios/support_scenarios.jsonl` | 250 final scenarios |
| `scenarios/support_review.jsonl` | 15 final reviews |
| `scenarios/monitoring_scenarios.jsonl` | 50 scenarios for HW7 |
| `scenarios/final-results.jsonl` | Final run, 250 completed |
| `reports/smoke-output.txt` | Smoke report |
| `traces/support_traces.json` | Exported traces for HW4 |
| `HW3-PROGRESS.md` | Running progress note and checklist |
