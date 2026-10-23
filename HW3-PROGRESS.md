# HW3 progress note

Model: `claude-haiku-4-5` (same value in `.env` `CARTWHEEL_MODEL` and runner `--model`).
Branch: `hw3-scenarios`.

## Done
- 2026-10-21: Read handout, SPEC.md, scenarios/skill/SKILL.md. Concepts covered (scenario,
  extra metadata, dimension, tuple, coverage vs challenge, pilot).
- 2026-10-21: A1, read the 6 damaged records (`data_quality_cases`):
  - `dq-order-missing-delivery-date`: order 8002, delivered with no date. Don't compute a deadline.
  - `dq-order-reversed-dates`: order 8001, shipped after delivered. Flag it and escalate.
  - `dq-order-store-mismatch`: order 8003, store differs from the product's store. Keep auth checks and escalate.
  - `dq-product-duplicate-title`: product 2 (same title as 1). Use IDs or ask before claiming a match.
  - `dq-product-invalid-price`: product 4, negative price. Don't present it as a valid offer.
  - `dq-product-missing-title`: product 3, empty title. Don't invent a name.

- 2026-10-21: A2, dimension plan APPROVED by Balaji (review point 1). Balaji proposed policy + tools,
  and chose to make authorization boundary its own dimension.

## Approved dimension plan (tuple field: values; source)
1. `role`: shopper, merchant, support (AUTH-1)
2. `applicable_policy`: cw-returns, cw-refunds, cw-cancellations, cw-disputes, cw-shipping, cw-payouts,
   cw-restocking-fees, cw-account-security, store override stricter (Juniper 14 / Meridian 21 / Saltbox 7),
   store override looser (Northwind 45), restocking opt-in (Cascade Audio, Second Stitch), none
   (facts.yaml store_overrides; RESP-1)
3. `tools_needed`: none, one_lookup, multi_lookup, lookup_then_write (SPEC section 4)
4. `intent`: order_status, return_eligibility, refund, cancellation, policy_question, product_search,
   dispute, account_change, payout_question, out_of_scope (SCOPE-1/2, ESC-2/3)
5. `record_state`: order in_window_eligible / past_window / above_threshold / placed / shipped /
   already_refunded / cancelled; product; damaged order/product (6 dq cases); store policy page; none
6. `access_scope` (extra dimension, AUTH-1): own_record, other_user_record, other_store_record,
   any_record (support), public (products/policies/no record)
7. `difficulty`: well_specified, ambiguous, missing_information, edge_case, mid_conversation_change
8. `user_style`: the 8 validator values (RESP-5)
Turn count = 1 + followups (recorded, not a dimension). Damaged records appear in record_state +
data_quality_case_id, and must use own_record or any_record access.

World facts: today = 2026-07-01 (meta.world_asof). Only 35 placed orders (cancellable), 480
refund-eligible, 7151 orders > $100.

- 2026-10-22: B0 smoke test PASSED. Reseeded, sent shopper user 1 "What's the status of my last order?"
  with scenario_id `smoke-0001`. Trace `35ddd569b776...` has user msg + reply (order 4455), model
  `anthropic/claude-haiku-4-5`, `list_my_orders` tool + result, `cartwheel.scenario_id=smoke-0001`.
  Token usage/cost are empty (usageDetails {}) for Anthropic via this instrumentation; optional per
  SKILL Step 1, so smoke report token/cost rows will read 0. Reseeded again afterwards.

- 2026-10-22: B1 tuples APPROVED by Balaji (15 coverage / 15 challenge). Balaji questioned whether plain
  auth rejections (26, 27) are challenge; chose to make them 2-turn social-pressure boundary cases.
- 2026-10-22: B1 generated `scenarios/pilot_scenarios.jsonl` (validates: 30, 15/15, 5 dq cases).
  Scratch tools (not committed): scratchpad `hw3/plans.py` (grounded plans + expected),
  `hw3/generate.py` (claude-sonnet-4-5 generator + critic, 4 workers, never sees `expected`;
  run with `uv run --with anthropic`). Manual critic fixes: 0028 opening restored granola mistake,
  0029 turn 2 removed leaked "already shipped", 0019 turn 2 now disambiguates (cheap one, Blue Heron).

- 2026-10-22: B1 review gate: Balaji kept 0027's invented "dashboard" reference on purpose (to see if it
  throws the model off); reworded 0003 (the "just give me the amount" line was unrealistic for granola).
  Revalidated OK.

- 2026-10-22: Reseeded + ran pilot: 30/30 completed -> scenarios/pilot-results.jsonl. Triage helper
  scratchpad `hw3/triage.py` (tools per scenario from Langfuse) -> `hw3/pilot_triage.json`.
  Claude's triage (NOT verdicts; Balaji decides): strong candidates 0010 (no tool, "no access to payout
  schedules" vs cw-payouts), 0025 ($99.75 escalated instead of auto refund), 0027 (turn 2 "Done", implies
  human may push cross-store refund; turn 1 confirms order is another store's), 0014 (escalated, no
  account-settings explanation). Medium: 0022, 0029, 0016, 0017. Validity questions: 0018 (get_order
  doesn't expose product's store, so mismatch invisible), 0020 (search_products needs a query + store name;
  never reached product 3), 0017 (find_order with store name in query returned []), 0021 (user only asked
  "is it too late", so offering instead of refunding is reasonable).

- 2026-10-22: REVIEW POINT 2 DONE (Balaji's verdicts). scenarios/pilot_review.jsonl: 12 reviewed,
  9 confirmed failures (0010, 0025, 0027, 0014, 0022, 0029, 0016, 0021, 0026), 1 invalid (0020:
  request can't reach product 3; change = ask for cheapest vases/pitchers). 0017, 0018 valid, no failure.
  Balaji's calls: 0026 is a failure (advising partner's login) even though SPEC doesn't spell it out;
  0018 scenario OK as is (a support user wouldn't name the store).
  Carry into Part C: 5 dq-order-store-mismatch final scenarios hit the same wall (get_order hides the
  product's store) unless the request gives a conflicting signal; dq-product-missing-title requests need
  a product-type query; merchant store filter takes a name but the prompt gives only the id.
  HW4 notes (do NOT group in HW3): agent mirrors user tone/length; offers unrequested options/escalations;
  attributes invented rules to policies; deflects instead of searching help center.

- 2026-10-22: Part B committed (76d9d65). Part C distribution APPROVED by Balaji ("distribution and
  coverage is key"). Monitoring = selection of 50 for HW7 rerun, not a manual review (scripted).
  Store-mismatch mix approved: 2 merchant + 2 shopper notice the conflict, 1 support plain.
- 2026-10-22: Reseeded; scratchpad `hw3/build_final.py` builds 250 grounded plans (seeded rng, no order
  reused, pilot orders excluded, expected from SQL/eligibility/policy docs/dq table). Swapped Juniper
  day-15 edge (no such order) for Saltbox day 8. Turns: 195x1, 42x2, 11x3, 2x4. Generation running ->
  `hw3/final_raw.jsonl`.

- 2026-10-22: Generated 250 (generate.py now caches per scenario + parses first JSON object; fallback to
  draft when critic changes turn count). lint.py flagged template openers (11x "I need a refund", 11x
  "Hi there, so I'm"...); diversify.py rewrote 47 openings. Fixed 0040 ("my account" -> roommate's account).
  scenarios/support_scenarios.jsonl written; `--final` passes.
- 2026-10-22: REVIEW POINT 3 (Balaji, 15 reviewed: 0002 0075 0020 0022 0059 0070 0013 0099 0031 0081 0014
  0101 0040 0058 0170). Accept 10. Revise 0070 (vague "bar" query; key said "cheapest" but merchant asked
  for all) -> "shampoo bar" listings, key lists all 8. Revise 0058 (approval question unnatural) -> plain
  refund ask, same key ($98.50 auto). Reject 0099 (key led with days, not the double charge) -> replaced
  by support-0251 (duplicate-charge dispute, key leads with escalate + no reversal claim; order 22).
  0170 (reject: "should not return unnamed product, ask instead") PENDING Balaji: revise criterion vs reject.
  Revisions applied; `--final` passes.

- 2026-10-22: 0170 -> option (a), criterion clarified (asking or id/description-only both OK; inventing
  a name fails). support_review.jsonl: 11 accept / 3 revise / 1 reject. monitoring_scenarios.jsonl: 50
  (35 cov / 15 chal; 25 shopper / 13 merchant / 12 support; 10 intents; 6 dq; 8 multi-turn).
  Part C committed (90c0a9b). Reseeded; final run started -> scenarios/final-results.jsonl.

- 2026-10-22: Final run DONE: scenarios/final-results.jsonl 250/250 completed (coverage 175, challenge 75),
  250 unique ids, no errors, no reruns needed.

- 2026-10-22: Part E: reports/smoke-output.txt written (whole project incl. pilot: roles shopper 252 /
  merchant 73 / support 47; 41 escalations; 13 permission denials; tokens/cost 0 as noted in B0; the 2
  errors + 2 blank-role traces are HW2 dev traces from 2026-10-20, NameError 'ctx', no scenario id).
  Export: traces/support_traces.json, 320 traces, 250/250 unique support-* ids.
  Observations for HW4 (not judged): issue_refund called only 7 times across all runs; 0014 T1 escalated
  the shears before the correction; 0075 merchant refund made no issue_refund call.
- 2026-10-22: Balaji checked 3 traces (0014, 0101, 0075): scenario id, model, tool activity all present.
  Balaji spotted in 0075: agent says a $35 refund "may go through human review" (false: cw-refunds, <=$100
  auto) and re-asks amount + reason the merchant already gave. Hypothesis for HW4: system prompt
  (agent/agent.py "Escalation") mentions "the auto-approval threshold" but never states $100 (only code +
  cw-refunds do), so the model hedges or escalates (cf. pilot-0025 $99.75). Do NOT fix before HW4.

## Next (RESUME HERE)
- 2026-10-22: Parts D+E committed (9d1e1ee). Re-verified: 9 files tracked, 250/250 completed,
  jq count = 250 (works as-is in PowerShell), Langfuse up.
- 2026-10-23: Video recorded (Balaji): https://www.loom.com/share/361a2a251a2d4bc380287dacfd46a2b7
- Remaining: PR into fork main, merge, Discord.

## Day plan (target Fri 2026-10-23); stopped Wed night after Part A
- Thu 10-22 (~4 h): B0 smoke test; B1 30 pilot scenarios + sample review; reseed; run pilot;
  REVIEW POINT 2 (>=10 reviewed, >=5 failures; add 20 challenge + rerun if short).
  C: generate 250 final, `--final` validate, REVIEW POINT 3 (15 reviews), 50 monitoring.
  Reseed and start the final run before stopping (can run overnight).
- Fri 10-23 (~1.5 h): resume or rerun any failures, smoke report, export, open 3 traces,
  commit, video, PR, Discord.

## Video & write-up prep (fill in as each part finishes)
Video list (exactly these, <=5 min): (1) one failed pilot scenario + its extra metadata + evidence;
(2) one final scenario revised after review; (3) one complete final trace: scenario id + tool activity;
(4) live `jq '[.traces[].cartwheel_scenario_id] | unique | length' traces/support_traces.json`.
All shown live from committed files / Langfuse; no screenshots. Never `docker compose down -v` (wipes traces).
- (1) pilot failure candidates: **0025** (trace 06bd21d5d083b42a05a28c4030472aa4; $99.75 escalated, clean
  objective metadata: threshold $100) or **0027** (traces 9ac43e32..., d9dd7f63...; "Done" + promised
  cross-store refund). Both single clear evidence lines in pilot_review.jsonl.
- (2) revised final scenario candidates: **support-0070** (before: "Show me my bar listings NOW...",
  key = cheapest 5 'bar' items; after: shampoo bar listings, key = all 8 with prices) or **support-0058**
  (dropped "does someone have to approve it?"). Show the support_review.jsonl line + the scenario line.
- (3) final trace candidates: **support-0101** (one trace e7ce7830dc20b867b5f70ef9d493cc99; get_order +
  escalate_to_human; dq store mismatch) is the cleanest single trace for the video; **support-0014**
  (4 traces: 522ee256..., 42aea1a6... has cancel_order, df035289..., eb987ba9...) for multi-turn.
- Write-up notes: B0 token usage/cost empty for Anthropic in Langfuse (smoke report rows read 0).

## Deliverables checklist
- [x] A: dimension plan approved
- [x] B: scenarios/pilot_scenarios.jsonl (30, validated)
- [x] B: scenarios/pilot-results.jsonl (30/30 completed)
- [x] B: scenarios/pilot_review.jsonl (12 reviewed, 9 confirmed failures)
- [x] C: scenarios/support_scenarios.jsonl (175 cov / 75 chal, 5 per dq case, new ids, `--final` passes)
- [x] C: scenarios/support_review.jsonl (15; both groups, 3 roles, every intent; revisions applied)
- [x] C: scenarios/monitoring_scenarios.jsonl (50; both groups, 3 roles)
- [x] D: reseed, then scenarios/final-results.jsonl (250 completed)
- [x] E: reports/smoke-output.txt
- [x] E: traces/support_traces.json (250 unique scenario ids); [x] 3 traces opened (Balaji)
- [x] Video (Balaji)
- [ ] PR into fork main, merge, Discord post
