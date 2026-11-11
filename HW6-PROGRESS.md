# HW6 progress: CI for agent evaluations

Branch `hw6-ci-evals`. Handout: `homework/module-3/hw6.md`. Target: start Sun 2026-11-08 or Mon 11-09, finish Thu 11-12.
Agent model: `claude-haiku-4-5` (same as HW3, for baseline, CI and Part E).

## Decisions (proposed 2026-11-06; confirm on day 1)

- **No LLM judge, code checks only.** The HW5 judge (v0) is marked frozen, but the HW5 verdict was "would not
  use" (TPR + TNR < 1), and the handout allows only an *accepted* judge. The reference judge covers a different
  mode. Code-only also means no judge calls and no OpenAI key in CI.
- **Modes: `fails_to_escalate` (7 cases) and `skips_available_tool` (5 cases).** Both are HW4 modes that code
  checks can decide (`tool_called`, `refund_status`, `no_write_tools`, ...). Out: `malformed_tool_query` (no
  check inspects tool arguments); `unsupported_commitment`, `confusing_reply` and `tone_mismatch` (need a judge).
- **Both outcomes seeded.** 8 cases come from HW3 traces where the failure was observed (likely capability);
  4 come from traces where the agent got it right (e-006, e-007, e-011, e-012: likely regression).
  These are guesses; the classification comes only from the five baseline runs.

## Draft cases: `eval_cases/hw6_draft_cases.jsonl`

Drafted from HW4 labels + HW3 scenarios. Not yet in `cases.jsonl`. Each has an extra `source_scenario` key
(check that the exporter accepts it, or drop it). The current `cases.jsonl` holds the course's sample `e-001`,
which needs judge `uninformative_response` that we don't have: replace it.

| id | mode | from | HW3 result | checks |
|---|---|---|---|---|
| e-001 | fails_to_escalate | 0243 dispute | failed (no escalation) | tool_called escalate_to_human, no_write_tools |
| e-002 | fails_to_escalate | 0184 dispute | failed | tool_called escalate_to_human, no_write_tools |
| e-003 | fails_to_escalate | 0217 phone change | failed | tool_called escalate_to_human |
| e-004 | fails_to_escalate | 0031 address change | failed | tool_called escalate_to_human |
| e-005 | fails_to_escalate | 0225 refund $154.75 | failed (no issue_refund) | refund_status 8134 queued_for_approval |
| e-006 | fails_to_escalate | 0043 dispute | passed | tool_called escalate_to_human, no_write_tools |
| e-007 | fails_to_escalate | 0032 store mismatch | passed | tool_called escalate_to_human, no_refund_row 8003 |
| e-008 | skips_available_tool | 0042 cancel delivered | failed (no eligibility tool) | tool_called check_return_eligibility, order_not_status 9380 cancelled |
| e-009 | skips_available_tool | 0234 merchant journals | failed (no search) | tool_called search_products |
| e-010 | skips_available_tool | 0175 payout timing | failed (no help center) | tool_called search_help_center, reply_contains "2 business days" |
| e-011 | skips_available_tool | 0053 refund $12.50 | passed | tool_called check_return_eligibility |
| e-012 | skips_available_tool | 0006 return question | passed | tool_called check_return_eligibility, no_write_tools |

Review points for Balaji: e-005 tests ESC-1 through the DB, which is our HW4 decision that issue_refund queues
over $100. e-008 and e-011 require the eligibility tool even when get_order could answer: is that the behavior
you want to lock in? Is e-010's `reply_contains` too brittle ("two business days")?

## Day 1 (2026-11-09)

Decisions confirmed by Balaji: code checks only; keep e-001 and e-005 (a reply that only asks a clarifying question
fails, matching the HW4 labels and ESC-3/ESC-1); e-008/e-011 require check_return_eligibility; e-010 checks
`reply_contains "business day"` (was "2 business days"). Drafts moved to `cases.jsonl` (draft file removed).
Fix: merchant cases need `input.store_id` (AuthContext raises without it): e-009 store 7, e-010 store 20.
All 12 HW3 source conversations were single-turn, so Harbor's one-message run matches them (no followups).

## Day-1 checks

- [x] Smoke run one case. Harbor 0.23.0 installed (`uv tool install`); Docker image builds and the agent runs on
  Windows. First smoke run: `invalid x-api-key` (old key revoked; Balaji replaced it). `hw6-smoke2-e-006`: 1 trial,
  0 exceptions, reward 0 (real: agent asked questions instead of escalating). Smoke runs are not baseline evidence.
  The exec bit on test.sh does not matter (Harbor runs it with sh).

## Baseline (`.harbor/jobs/hw6-baseline`, one job, 12 tasks x 5, approved 2026-11-09)

- Adapter fix: Harbor 0.23.0's job result.json has no `trial_results` (per-trial result.json files only), so the
  summarizer matched nothing. Added `load_trials()` in harbor_adapter/summary.py (falls back to per-trial files,
  ordered by started_at); analysis.py uses it too. Upstream has no fix (checked upstream/main 2026-11-09).
- First pass: 48 valid trials, 12 infra errors, all in the verifier (agent finished): 8 VerifierTimeoutError (uvx
  downloads 123 packages per verifier; 4 concurrent > 300 s) and 4 RewardFileNotFoundError (DNS error), in groups of
  4 = the concurrency. Backup of those 12 trial dirs + original config in the session scratchpad.
- Fix (Balaji approved rerunning only the 12; no verdict existed, so not cherry-picking). `harbor jobs resume` does
  not work for this: changing the timeout fails "trial config does not match", changing concurrency fails the
  lock.json check (both failed before any run; the first one deleted the 12 errored dirs). Original config restored.
  Used two fill-in jobs instead (-n 2, --verifier-timeout-multiplier 3): `hw6-baseline-fill1` (e-005..e-008 x1),
  `hw6-baseline-fill2` (e-009..e-012 x2). `scripts/summarize_harbor_job.py` now takes several job dirs and pools them:
  `... summarize_harbor_job.py .harbor/jobs/hw6-baseline .harbor/jobs/hw6-baseline-fill1 .harbor/jobs/hw6-baseline-fill2 --expected-attempts 5 --classify`.
  Verifier timing at concurrency 4: 230-280 s of the 300 s limit; at the end of the job (fewer running) 120-135 s.
- Fill-in jobs: 12/12 valid, 0 errors. Pooled baseline (60 valid trials), recorded by Balaji's decision "as observed":
  regression e-007, e-011, e-012 (5/5); capability e-001, e-003, e-004, e-005, e-006, e-008, e-010 (0.0), e-002 (0.6),
  e-009 (0.2). Both modes have a regression (e-007 escalate; e-011/e-012 tool). Every failed trial was read: all
  are real instances of the mode (no broken checks). Video clip: e-009 says it can "search the product catalog"
  and still claims it has no tool for listings. pass@3 vs pass^3 example: e-002 (3/5) = 1.00 vs 0.10.
- Windows fix in harbor_adapter/export.py: `_move_into_place` retries the rename (Defender locks freshly written
  files; WinError 5) and falls back to copytree. No effect on Linux.
- CI note: use `--verifier-timeout-multiplier` in evals.yml too (verifier installs 123 packages per trial).
- [x] Harbor world (`generate_world(scale="dev")`) matches `data/cartwheel.db`: all draft orders/users/stores exist, no refunds.
- [x] Enable Actions on the fork; add secret `ANTHROPIC_API_KEY` and variable `CARTWHEEL_MODEL`.

## Next session (Part C)

- Balaji: fork Settings -> Secrets and variables -> Actions: secret `ANTHROPIC_API_KEY` (new key), variable
  `CARTWHEEL_MODEL` = `claude-haiku-4-5`; make sure Actions is enabled on the fork.
- Claude: draft the `complete-evaluations` steps in .github/workflows/evals.yml (install harbor==0.23.0, export,
  harbor run --n-attempts 5 --job-name hw6-evals, verifier timeout multiplier, summarize with if: always(),
  upload .harbor/jobs/hw6-evals with if: always()). Each full CI run = 60 agent runs (~$1-3): ask before pushing.
- Local Docker: Docker Desktop may need starting (`docker info`); Harbor needs `$env:PYTHONPATH = $PWD.Path`.

## Part C (2026-11-10)

- evals.yml `complete-evaluations` steps drafted: install harbor 0.23.0 (+ uv tool bin on PATH), export, harbor run
  (--n-attempts 5, --verifier-timeout-multiplier 3, -n default 4, --yes), summarize (if: always(); exit 1 = a
  regression run failed or infra problem), upload .harbor/jobs/hw6-evals (if: always()). Export locally: 12 tasks.
- Fork: Actions enabled; repo secret ANTHROPIC_API_KEY and repo variable CARTWHEEL_MODEL=claude-haiku-4-5 added
  (verified by name, 2026-11-10).
- Plan to save a paid run: Part C has no separate CI run. Open the PR with the regression commit already in it
  (run 1 = regression), then revert (run 2). 2 x 60 = 120 agent runs on claude-haiku-4-5, 0 judge calls.

## Part D (PR #6, 2026-11-10)

- Regression commit 16f3924 (prompt line "Answer return and refund questions from get_order alone. Never call
  check_return_eligibility."), prompt hash 34ba29ac44be. Run 1: https://github.com/bvgitty/cartwheel-homeworks/actions/runs/42959072000
  -> red. 60/60 trials rewarded, no infra problems. e-011 0/5, e-012 0/5 (block): no trial called
  check_return_eligibility; one e-011 trial (7mb27xU) issued a refund without the eligibility check. e-007 5/5.
  Capability drift vs baseline (same model, different prompt, n=5): e-002 0/5 (was 3/5), e-005 1/5 (0), e-006 2/5 (0),
  e-010 2/5 (0). Artifact downloaded to the session scratchpad (run1/).
- Revert commit 6951663 (agent.py identical to 85b280d; hash back to 11bf9b5e1b26). Run 2: https://github.com/bvgitty/cartwheel-homeworks/actions/runs/42961451793
  -> green. 60/60 rewarded. e-007/e-011/e-012 5/5. Capability: e-002 1/5, e-005 2/5, e-006 3/5, e-010 1/5, rest 0.
- ci-runs.json drafted (case e-011); "explanation" is a DRAFT for Balaji to rewrite.
- Push only once, at the end (Balaji 2026-11-10): every push to PR #6 reruns the paid job. Uncommitted locally
  until then.

## Part E (2026-11-10)

- Balaji picked e-006 (0/5, 2/5, 3/5 across baseline/run1/run2). Local job .harbor/jobs/hw6-capability-15:
  15/15 rewarded, 0 exceptions, 22 min, verifier multiplier 3. 6/15 passed.
- eval_results/e-006-15.json: n=5 2/5 pass@1/3/5 0.400/0.900/1.000; n=10 4/10 0.400/0.833/0.976;
  n=15 6/15 0.400/0.815/0.958, pass@10 = pass@15 = 1.000. Interpretation is Balaji's.
- Fixed analysis.py's trial_order label (claimed trial_results; Harbor 0.23.0 order is per-trial started_at).
- 2026-11-11: Balaji filled all write-up judgments (Part E: stable from 10 to 15 runs, but not precise; Wilson
  95% for 6/15 = 0.20-0.64; 0/5 and 3/5 samples are consistent with p ~ 0.36, i.e. noise). Remaining: video ->
  Loom link (write-up line 3) -> one commit + push (ask: [skip ci] or not) -> merge -> Discord -> delete branch.
- HW6-WRITEUP.md skeleton drafted (facts filled; Balaji's judgments are "> **(Balaji: ...)**" placeholders).
  ci-runs.json explanation rewritten by Balaji.
- Pooled across all e-006 observations (same prompt): baseline 0/5 + run2 3/5 + 15-run 6/15 = 9/25.

## Next session (2026-11-12): concept review before the video

Balaji wants a full concept review before recording (video Thu 11-12 or Fri 11-13). Topics, using our own numbers:
1. Regression vs capability: why 5/5 decides it, and why a capability case never blocks CI (e-006 0/5 -> 9/25).
2. pass@k vs pass^k: formulas, why one rises and one falls with k (e-002 3/5; e-006 n=15), which is for product vs CI.
3. The CI gate: p^(5r), what a red run means (Part D), why failures are kept as evidence and not rerun.
4. n vs k, stability vs precision (Part E table, Wilson intervals, 0/5 as ordinary noise).
5. Code checks vs judges: why no judge here (HW5 verdict), what a check can and cannot see.
Then: video (handout's 5 items) -> Loom link -> one commit/push ([skip ci]?) -> merge -> Discord -> delete branch.

## Checklist

- [x] A: review drafts -> cases.jsonl; 60 baseline runs (approve first); classify (Balaji)
- [x] B: passk.py (Balaji typed) + 3 supplied tests pass
- [x] C: evals.yml
- [x] D: regression push + revert on one PR; ci-runs.json (explanation: Balaji to rewrite)
- [x] E: one capability case x15; eval_results/<id>-15.json (interpretation: Balaji)
- [ ] Write-up, video, PR, merge, Discord, delete branch
