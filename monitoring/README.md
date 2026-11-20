# HW7 monitor: unsupported_policy_claim

The monitor samples Cartwheel conversations from a time window and runs the frozen reference judge
`unsupported_policy_claim-v3` (claude-opus-4-6; failure sensitivity 0.83, pass specificity 0.95) on them.
It corrects the raw flag rate with Rogan-Gladen, adds a bootstrap 95% interval, and writes scores to Langfuse.
Only the random sample (20%) feeds the estimate. The `policy_lookup` risk group (conversations that called
`get_policy` or `search_help_center`) is judged and scored separately. Threshold: corrected rate 0.15,
chosen before any judge output.

```bash
uv run python -m monitoring.run --period before --dry-run   # counts only, no judge calls
uv run python -m monitoring.run --period after --yes        # judge, correct, write scores
uv run python -m monitoring.run --last-hours 24 --yes       # scheduled form (.github/workflows/monitor.yml)
```

Periods: `before` = the HW3 run (2026-10-23), `after` = a new run of the same 50 monitoring scenarios
(2026-11-18). Both used claude-haiku-4-5. Per-period results are in `history.jsonl` and `prevalence.svg`.

| period | random flagged | raw | corrected | 95% CI | risk group flagged |
|---|---|---|---|---|---|
| before | 3/10 | 0.30 | 0.317 | [0, 0.77] | 0/6 |
| after | 3/10 | 0.30 | 0.317 | [0, 0.76] | 0/5 |

## 1. Did the corrected failure estimate move between the two periods?

No. Both periods flagged 3 of 10 random conversations, so both corrected estimates are 0.317. The flags came
from different scenarios in each period (before: 0074, 0107, 0093; after: 0043, 0250, 0238). The two periods
reached the same rate from different evidence.

## 2. Do the intervals support a conclusion, or is the result uncertain?

The result is uncertain. With 10 random conversations per period, one flag more or fewer moves the raw rate by
0.10. Dividing by the judge's 0.78 (sensitivity + specificity - 1) widens the interval further. Both intervals
contain 0 and the 0.15 threshold, and they overlap almost completely. So we can neither claim a change between
periods nor claim that the rate is above the threshold.

What we can trust is that the failures are real. I reviewed all 6 flagged conversations, and all 6 are true
unsupported policy claims, so the judge is not over-flagging on this traffic. That review only checks false
positives: the 14 unflagged random conversations were not reviewed, and the sensitivity correction is what
accounts for missed failures. To narrow the interval, raise the random rate or pool several days.

## 3. What did the risk groups reveal that the random estimate did not?

The risk group showed that we were watching the wrong place. `policy_lookup` flagged 0 of 11. None of the 6
flagged conversations called `get_policy` or `search_help_center`. The failure is making policy claims without a
lookup, which the prompt forbids ("Policy answers come from the help center ... cite the policy id"). Three
patterns:

- Cancellation money claims with no source (0093 "you won't be charged"; 0250 and 0238 promise a refund).
  `cancel_order` returns only a status, and no help-center document covers what happens to the money. This is
  a SPEC gap that produces agent failures.
- Policy facts stated without a lookup (0074 "no human review under $100" echoes the user's own "$100";
  0043 "outside the standard return window" without calling `check_return_eligibility`).
- Invented remedies or commitments (0107 "you shouldn't have to send the damaged item back" and review "within a
  few hours", against the 24 h in ESC-5; 0043 hints at an exception).

A better risk group is a policy-sounding claim with no policy tool call. The risk group's 0% cannot be used as a
rate, because the group is a targeted, non-random slice.

## 4. What action should happen if the estimate crosses the threshold?

Start error analysis on the flagged traces: review each one in the review app, confirm or reject it, and
root-cause the confirmed failures. That review was done here (6/6 confirmed). Then:

1. Fix the causes. Have `cancel_order` return the charge or refund outcome, or add a cancellation policy
   document. Add a prompt rule to look up policy before stating it, with no thresholds or windows from memory.
2. Turn confirmed failures into HW6 eval cases: cancelling a placed order (no money promise without a source),
   a refund under $100 (no threshold claim without a document), and a late return (call
   `check_return_eligibility` before any window claim).
3. Rerun the monitor after the fix. Because a point estimate above 0.15 with an interval that includes 0.15 is
   weak evidence, a crossing should first raise the random sample rate if the flagged review does not confirm
   the failures.
