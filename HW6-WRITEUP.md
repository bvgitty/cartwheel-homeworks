# HW6 write-up: CI for agent evaluations

*AI Evals for Engineers & PMs, Module 3. Branch `hw6-ci-evals`, PR [#6](https://github.com/bvgitty/cartwheel-homeworks/pull/6). Video: [Loom](https://www.loom.com/share/d7961984344f447ea68f85b3563fdf45)*

Agent model for every run in this homework: `claude-haiku-4-5`, prompt version `11bf9b5e1b26` (except the
intentional regression, `34ba29ac44be`). No LLM judge: every case is decided by code checks.

| Deliverable | File |
|---|---|
| 12 evaluation cases | [eval_cases/cases.jsonl](eval_cases/cases.jsonl) |
| pass@k, pass^k, CI rule | [tests/eval/passk.py](tests/eval/passk.py) |
| CI workflow | [.github/workflows/evals.yml](.github/workflows/evals.yml) |
| Regression and revert runs | [ci-runs.json](ci-runs.json) |
| 15-run analysis of e-006 | [eval_results/e-006-15.json](eval_results/e-006-15.json) |

## Part A: cases and baseline classification

12 cases from two HW4 failure modes. Both modes are decided by exact tool calls or database values, so code checks
are enough. I did not use the HW5 judge: its test result (TPR 0.53, TNR 0.35) was "would not use".

> Both the failure modes, 1. Skips available tools was picked as we noticed that the agent sometimes skips check_return_eligibility. It can lead to errors and we can easily ensure the tool calls check_return_eligibility after find_order . 2. fails_to_escalate again was seen when agent sometimes does not escalate to human. Hence these two modes were picked over the other failure modes as they have a clear pass/fail criteria so a judge is not needed.

| Case | Mode | Source (HW3) | Checks | Baseline (5 runs) | Kind |
|---|---|---|---|---|---|
| e-001 | fails_to_escalate | support-0243 | tool_called escalate_to_human, no_write_tools | 0/5 | capability |
| e-002 | fails_to_escalate | support-0184 | tool_called escalate_to_human, no_write_tools | 3/5 | capability |
| e-003 | fails_to_escalate | support-0217 | tool_called escalate_to_human | 0/5 | capability |
| e-004 | fails_to_escalate | support-0031 | tool_called escalate_to_human | 0/5 | capability |
| e-005 | fails_to_escalate | support-0225 | refund_status 8134 queued_for_approval | 0/5 | capability |
| e-006 | fails_to_escalate | support-0043 | tool_called escalate_to_human, no_write_tools | 0/5 | capability |
| e-007 | fails_to_escalate | support-0032 | tool_called escalate_to_human, no_refund_row 8003 | 5/5 | **regression** |
| e-008 | skips_available_tool | support-0042 | tool_called check_return_eligibility, order_not_status 9380 cancelled | 0/5 | capability |
| e-009 | skips_available_tool | support-0234 | tool_called search_products | 1/5 | capability |
| e-010 | skips_available_tool | support-0175 | tool_called search_help_center, reply_contains "business day" | 0/5 | capability |
| e-011 | skips_available_tool | support-0053 | tool_called check_return_eligibility | 5/5 | **regression** |
| e-012 | skips_available_tool | support-0006 | tool_called check_return_eligibility, no_write_tools | 5/5 | **regression** |

Baseline: 60 valid trials (jobs `hw6-baseline` plus two fill-in jobs that reran only the 12 trials whose verifier
hit an infrastructure error; no verdict existed for those trials). Every failed trial was read: each one is a
real instance of its mode, not a broken check. Each mode has at least one regression case.

> An example of the failure mode (skips_available_tool) is scenario e-009, where the merchant is asking for the following "I need to see my journal listings and prices. Just the list, no extra info." The tool exists for this search_products, but the agent does no tool call and responds "I don't have access to a tool that retrieves your store's product listings or inventory. My available tools let me search the product catalog, look up individual orders, and handle returns and refunds—but not view your store's full catalog or journal.
For managing your store's product listings and prices, you'd need to use your merchant dashboard directly. …" It even states that it can search the product catalog but does no such action. A clear failure scenario for this mode.

## Part B: pass@k and pass^k

`pass_at_k(n, c, k) = 1 - C(n-c, k) / C(n, k)`: the chance that at least one of k attempts succeeds.
`pass_hat_k(n, c, k) = C(c, k) / C(n, k)`: the chance that all k attempts succeed. A regression case blocks CI on
any failed run; a capability case never blocks.

Example from the baseline: e-002 passed 3 of 5. pass@3 = 1.00, pass^3 = 0.10.

> In a case where the agent is dealing with a lot of customers and it has to get the action right every single time, using Pass^k helps reliably block CI if there is a failure and is indicating a regression. However, Pass@k is only tracking capability and a Pass@3 of 1.00 doesn't guarantee the same in a larger sample and cannot be used reliably to block CI.

## Parts C and D: CI runs on PR #6

The `complete-evaluations` job installs Harbor 0.23.0, exports the classified tasks, runs 12 tasks x 5 attempts in
Docker (verifier timeout x3, learned from the baseline), summarizes with `if: always()` (exit 1 when a regression
case fails), and uploads `.harbor/jobs/hw6-evals` with `if: always()`.

| Run | Commit | e-011 | e-012 | e-007 | CI |
|---|---|---|---|---|---|
| [Regression](https://github.com/bvgitty/cartwheel-homeworks/actions/runs/42959072000) | 16f3924: "Never call check_return_eligibility." | 0/5 | 0/5 | 5/5 | **fail** (block) |
| [Revert](https://github.com/bvgitty/cartwheel-homeworks/actions/runs/42961451793) | 6951663 | 5/5 | 5/5 | 5/5 | pass |

Both runs: 60/60 trials rewarded, no infrastructure errors. In the regression run no e-011/e-012 trial called
`check_return_eligibility`, and one e-011 trial issued a refund without the eligibility check.

Capability cases moved between samples of the same system (5 runs each):

| Case | Baseline | Regression run | Revert run |
|---|---|---|---|
| e-002 | 3/5 | 0/5 | 1/5 |
| e-005 | 0/5 | 1/5 | 2/5 |
| e-006 | 0/5 | 2/5 | 3/5 |
| e-010 | 0/5 | 2/5 | 1/5 |

> We were able to successfully modify the instruction and introduce a regression for e-011/e-012 such that in the first run, no trial called check_return_eligibility and one trial even issued a refund without the eligibility check, which we want to avoid. After the revert, e-011 and e-012 passed 5/5 again, so the original behavior returned. The capability cases on the other hand moved considerably between runs. It's not indicative of a pattern given the small sample size.

## Part E: e-006 after 5, 10 and 15 runs

Local job `hw6-capability-15`, 15/15 trials rewarded, 6 passed. Trial order is each trial's `started_at`
(Harbor 0.23.0 writes no `trial_results`): `0 0 0 1 1 | 0 1 0 0 1 | 1 0 0 1 0`.

| n | passes | pass@1 | pass@3 | pass@5 | pass@10 | pass@15 | pass^3 | pass^5 |
|---|---|---|---|---|---|---|---|---|
| 5 | 2 | 0.400 | 0.900 | 1.000 | | | 0.000 | 0.000 |
| 10 | 4 | 0.400 | 0.833 | 0.976 | | | 0.033 | 0.000 |
| 15 | 6 | 0.400 | 0.815 | 0.958 | 1.000 | 1.000 | 0.044 | 0.002 |

pass@10 and pass@15 at n = 15 are 1.000 by construction: only 9 failures were observed, so every 10-run subset
contains a pass. All e-006 observations on the same prompt: 0/5 (baseline) + 3/5 (revert run) + 6/15 = 9/25.

> The estimate held steady from 10-15 runs, with a narrow -0.018 change. So, yes it was stable. However, this is still not a precise one as the plausible true rate narrows with each block but is still wide at 15. We can't really tell from these runs alone.

## Costs

Agent runs on `claude-haiku-4-5`: 60 baseline (plus the 12 reruns) + 120 CI + 15 Part E. Judge calls: 0.
