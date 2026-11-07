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

## Day-1 checks

- [ ] Smoke run one case (Windows exec bit on `test.sh`, known `test_harbor_adapter` failure). Fallback: WSL.
- [ ] Confirm the Harbor world (`generate_world(scale="dev")`) matches `data/cartwheel.db` (orders above exist there with no refunds).
- [ ] Enable Actions on the fork; add secret `ANTHROPIC_API_KEY` and variable `CARTWHEEL_MODEL`.

## Checklist

- [ ] A: review drafts -> cases.jsonl; 60 baseline runs (approve first); classify (Balaji)
- [ ] B: passk.py (Balaji types) + 3 supplied tests
- [ ] C: evals.yml
- [ ] D: regression push + revert on one PR; ci-runs.json
- [ ] E: one capability case x15; eval_results/<id>-15.json
- [ ] Write-up, video, PR, merge, Discord, delete branch
