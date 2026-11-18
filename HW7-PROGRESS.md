# HW7 progress: monitor agent behavior after deployment

Branch `hw7-monitoring`. Handout: `homework/module-3/hw7.md`. Prepped 2026-11-13; start 11-14 or 11-15.
Agent model: `claude-haiku-4-5` (same as HW3, so the two periods are comparable).

## The big picture (why HW7 exists)

HW6 gates *known* cases before a merge. HW7 watches *unknown* traffic after deployment: sample traces, run a
validated judge on the sample, correct the judge's raw flag rate for its known errors, and track that corrected
rate over time against a threshold. Two complete runs of the same 50 scenarios stand in for two deployment periods.

## Decision 1: which frozen judge (blocking; Balaji decides)

The monitor corrects the raw flag rate with Rogan-Gladen:
`corrected = (raw + pass_specificity - 1) / (failure_sensitivity + pass_specificity - 1)`.
The denominator must be positive (the judge must beat a coin flip in the TPR + TNR sense).

| judge | model | failure sensitivity (= HW5 TNR) | pass specificity (= HW5 TPR) | sens + spec - 1 | usable? |
|---|---|---|---|---|---|
| our `unsupported_commitment-v0` | gpt-4o-mini | 6/17 = 0.35 | 19/36 = 0.53 | **-0.12** | no: the correction is undefined/inverted; `correct.py` must raise |
| reference `unsupported_policy_claim-v3` | claude-opus-4-6 | 10/12 = 0.83 | 36/38 = 0.95 | 0.78 | yes (staff-accepted) |

Both are registered as `frozen` in `analysis/state/judges/`, and `judge_test_data()` loads both (checked 2026-11-13).
The handout's own fallback is the reference judge ("if you did not ... choose a judge"); our HW5 verdict was
"would not use". Revalidating our prompt on another model = a new HW5 (handout line 50): not worth it.
Recommendation: reference judge. `hw5-reference.patch` only adds its readable prompt + test report (applies cleanly).
Day-1 check: one cheap call to `claude-opus-4-6` with our ANTHROPIC_API_KEY.

## Decision 2: where the scheduled workflow runs (Part D; Balaji decides)

Langfuse is local (localhost:3000); a GitHub-hosted runner cannot reach it. Options:
- **Self-hosted runner on this PC** (handout's suggestion). Docker + Langfuse must be running when it fires.
  The fork is PUBLIC: keep the workflow on `schedule` + `workflow_dispatch` only, and leave "require approval for
  fork PRs" on, so nobody else's code runs on this machine.
- Langfuse Cloud: GitHub-hosted runner works, but our traces live locally, so the 24 h window would be empty
  (the handout's zero-count path), and the dashboard would be split across two Langfuse instances.

## Decision 3: threshold (Balaji; BEFORE seeing any judge results)

Corrected failure rate that triggers a new error analysis. Starter suggests 0.15. Reference judge's
500-trace store: raw 0.18 (from the judge record). Pick and commit it in `config.json` before Part B runs.

## Facts found during prep (2026-11-13)

- `scenarios/monitoring_scenarios.jsonl`: 50 ids, all in the HW3 final run (`final-results.jsonl`).
- HW3 export (`traces/support_traces.json`): the 50 ids = 60 traces, 2026-10-23 04:17:13Z .. 05:04:06Z; the whole
  final run spans 04:16:30Z .. 05:04:36Z. Candidate "before" period: 2026-10-23T04:16:00Z .. 05:05:00Z.
  Day-1 check against LIVE Langfuse: no retry/duplicate traces of the 50 ids inside that window, and every trace
  model = claude-haiku-4-5. (Live Langfuse also holds pilot + HW2 traces outside the window.)
- Starter files: `monitoring/sample.py` (select_traces: TODO), `correct.py` (corrected_mode_prevalence: TODO),
  `write_scores.py` (build_score_records: TODO), `run_judges.py` (judge_sample, judge_test_data: given),
  `chart.py` (given). `monitoring/run.py`, `config.json`, `README.md`, `.github/workflows/monitor.yml`: to create.
- `judge_sample` feeds the judge the normalized conversation text (`{trace_id, content}`) and flips the verdict to
  1 = failure. Day-1 check: which text format the reference judge's test set used, so our records match it
  (handout: exact prompt, model, inputs, parser).
- Langfuse images are `langfuse:3` (v3 has custom dashboards; check the widget options on day 1).

## Paid runs (ask before each)

- Part A "after" period: 50 scenarios on claude-haiku-4-5 (some multi-turn).
- Judge: claude-opus-4-6 on the union per period (10 random + risk-group traces). Count the risk group first.
- Before / after / after-again (score idempotency; DocETL may serve the cache) + 1 manual workflow run.

## Day 1 results (2026-11-17)

Decisions (Balaji): judge = reference `unsupported_policy_claim-v3` (claude-opus-4-6); runner = self-hosted on
this PC; threshold = **0.15** (chosen before any judge output). `hw5-reference.patch` applied (prompt + test report).
Live Langfuse, before window 2026-10-23T04:16:00Z..05:05:00Z: 320 traces (whole HW3 run); 60 carry the 50
monitoring ids (all 50 present), all `anthropic/claude-haiku-4-5`; session_id on all 60. run.py must filter the
window to the 50 ids. Tool names are clean (`get_policy`, `search_help_center`, ...), so DEFAULT_RISK_GROUPS work.
policy_lookup risk group: ~6-8 conversations in the before period (search_help_center 6 + get_policy 2 traces).
Normalized text (`normalize_trace(...)["text"]`) carries tool results with `policy_id`s, which matches the judge
prompt's "policy documents ... each with its doc id".

## Next session (Part B)

1. Balaji types `select_traces` in monitoring/sample.py from scratch (steps: validate rate/ids; k = max(1, round(rate*n));
   random.Random(seed).sample; risk groups via dict comprehension in original order; to_judge = random first, then
   groups, dedup by id with a seen set; don't mutate inputs). Test: `uv run pytest --runxfail tests/test_hw_holes.py -k hw7_sampling`.
2. Claude writes monitoring/run.py (plumbing): Langfuse trace.list(from_timestamp, to_timestamp) -> normalize ->
   filter to the 50 ids -> group by scenario id -> 50 records (id = final trace id, text = ordered turns, tools,
   turn_count) -> select_traces -> show counts -> ask approval -> judge_sample on the union.
3. Before Part B's judge run: start Docker Desktop + Langfuse (`docker compose -f observability/docker-compose.yml up -d`).

## Plan (one part at a time)

- [x] Day 1: decisions 1-3; checks above; apply hw5-reference.patch if reference judge.
- [x] A: after-period run (approve first); config.json with both UTC windows.
      2026-11-18T06:23:51Z..06:32:03Z, 50/50 completed (scenarios/hw7-after-results.jsonl); Langfuse window =
      60 traces, all 50 ids, all haiku-4-5. Opus 4.6 ping OK. Note: Langfuse reports the model as
      `anthropic/claude-haiku-4-5`; run.py must strip the provider prefix when comparing to config "model".
- [ ] B: select_traces (Balaji types: small, teaches sampling); run.py (Claude: plumbing); hw7_sampling test.
- [ ] C: corrected_mode_prevalence (Balaji types: Rogan-Gladen + bootstrap); build_score_records; tests;
      run both periods (approve judge calls); history.jsonl; prevalence.svg; idempotency rerun.
- [ ] D: monitor.yml (schedule + dispatch), secrets/variable, runner; Langfuse dashboard; one manual run.
- [ ] E: monitoring/README.md (4 answers: Balaji).
- [ ] Video (6 items), PR to fork main, merge, Discord, delete branch.
