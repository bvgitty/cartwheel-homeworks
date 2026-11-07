# HW5 judge report: `unsupported_commitment`

*AI Evals for Engineers & PMs, Module 2. Branch `hw5-judge`. Judge model `gpt-4o-mini`. Video: [Loom](https://www.loom.com/share/268764cd55f4466a809e9d2b116c63ca)*

## Failure mode

Does the assistant's reply commit to an outcome, follow-up, timing or exception that the trace's
tool results and Cartwheel policy do not support? Full definition, with Pass/Fail rules and the
boundary with neighboring HW4 modes: [hw5_failure_definition.md](hw5_failure_definition.md).

I chose it because it was the most frequent HW4 mode (32 of 146 traces, 21.9%), because it needs
judgment (a code check cannot tell "a human will review your case" from "a human will approve your
refund"), and because it carries real risk: a customer told a refund is coming acts on it.

## Labels and inputs (Parts A, B)

- **Labels.** HW4 gave 107 labeled sessions. To get more failures I added one `next_to_label`
  enrich batch (H1, 25 sessions, 38 traces; 14 Fail sessions). All labels are mine.
- **One input per conversation.** Cartwheel writes one trace per turn. Each judge record is the
  session's first Fail turn (else its last turn), with the earlier turns stitched in front as
  context: 132 records, saved once in `analysis/state/hw5_trace_inputs.json` and reused by every
  prompt version.
- **Split** (20/40/40, stratified, seed 7, run once):

| Split | Records | Pass | Fail | Use |
|---|---|---|---|---|
| Train | 26 | 15 | 11 | Source of prompt examples only |
| Dev | 53 | 35 | 18 | Iteration (36 / 17 at split time; 3 labels corrected during review) |
| Test | 53 | 36 | 17 | Scored once, after freezing |

Before writing v0 I re-read the train labels and corrected three (0057, 0011, 0238 -> Fail). Train
examples in the prompt: 0245 (Fail, clear), 0088 (Pass, clear), 0208 (Pass, borderline), 0059
(Fail, borderline); v1 and v2 add 0142 and 0039 (Pass).

## Judge development (Part C)

Pass is the positive class: TPR = share of my Passes the judge also passed; TNR = share of my
Fails the judge caught. Intervals are 95% Wilson. All rows are scored against the final dev labels.

| Version | Change | Dev TPR | Dev TNR | Correct of 53 |
|---|---|---|---|---|
| **v0** | First prompt: definition, policy reference, 4 train examples | **0.63** [0.46, 0.77] | **0.89** [0.67, 0.97] | **38** |
| v1 | Outcome-vs-process section, narrower Fail rules, more Pass cases, a decision rule, 2 train examples | 0.57 [0.41, 0.72] | 0.89 [0.67, 0.97] | 36 |
| v2 | Same rules; critique becomes a tagged list (SUPPORTED / PROCESS / UNSUPPORTED), Fail only on an UNSUPPORTED tag | 0.54 [0.38, 0.70] | 0.83 [0.61, 0.94] | 34 |

**Disagreement review (v0).** I reviewed all 18 dev disagreements in the Judge tab of my HW4 review
app, which shows the judge's verdict and critique beside my label. Decisions are saved in
`analysis/state/hw5_disagreements.json`.

- **12 judge errors.** 11 were false Fails in four groups: offering or opening an escalation
  treated as a promise; a completed check or obvious next step ("you're all set"); an action the
  assistant can take itself (a $10.75 refund "right away"); a conditional policy ("may charge a fee
  if the store opted in"). The judge's critiques flagged risk ("could lead the user to expect…")
  rather than a commitment.
- **6 label errors; 3 changed labels** (0106, 0080 -> Fail; 0139 -> Pass), re-exported before the
  next run. A third of the disagreements were my mistakes, not the judge's.
- **Definition clarified.** The boundary is *outcome versus process*: promising a result (approval,
  an exception, a date) fails; describing a review, an escalation offer or the assistant's own next
  step does not. Exception hints still fail even when framed as a reason to escalate (0111). Example
  disagreement: 0218, "they can verify the delivery date and give your customer a confirmed
  deadline". I first called it a Fail, then kept it a Pass because it is the same as train example
  0208: it says what the human will check, not what the deadline will be.

**Why I stopped revising.** The handout allows two revisions, and neither helped. Both revisions
scored below v0, and every difference is inside the overlapping intervals. The results were also
unstable: 23 of the 53 dev verdicts changed at least once across the three versions, including
cases no revision touched. The judge helper sets no temperature, so `gpt-4o-mini` samples at its
default. Six cases were wrong in every version (0027, 0035, 0043, 0066, 0094, 0249). In 0249, v2
was told a refund of $100 or less "right away" is the assistant's own action and still failed it.
These are limits of the judge model, not of the prompt wording. I froze **v0**, the best on dev.

## Test result (Part D)

Frozen `unsupported_commitment-v0`, scored once on 53 held-out records (36 Pass, 17 Fail).
Recomputed from the saved predictions by [analysis/recalc_test.py](../recalc_test.py).

| | Judge Pass | Judge Fail |
|---|---|---|
| **Human Pass (36)** | TP 19 | FN 17 |
| **Human Fail (17)** | FP 11 | TN 6 |

| Rate | Test | Dev (same prompt) |
|---|---|---|
| TPR | **0.53** [0.37, 0.68] | 0.63 [0.46, 0.77] |
| TNR | **0.35** [0.17, 0.59] | 0.89 [0.67, 0.97] |
| TPR + TNR | 0.88 | 1.52 |

**Would I use this judge? No.** On test it caught 6 of 17 real failures, and it failed 17 of 36
good replies. TPR + TNR is below 1, so on test it separates Pass from Fail no better than chance,
and the Rogan-Gladen correction for a production failure rate is undefined (its denominator,
TPR + TNR - 1, is negative). Even the top of the TNR interval (0.59) would miss four in ten
failures.

**Why test is so far below dev.** The two TNR intervals do not overlap, so this is more than
sampling noise. v0 was the first prompt, not tuned to dev, so it is not overfitting either. Two
likely causes:

1. **Only dev labels were reviewed.** The dev review found that a third of the disagreements were
   my labeling errors. Test labels never had that review, and correcting them after seeing test
   predictions would leak, so test measures the judge against noisier labels.
2. **An unstable judge.** At the default temperature, verdicts change between runs (23 of 53 on
   dev), and the judge twice returned a malformed result ("Not found"; one dev case for v2 and one
   test case, both resumed after clearing the DocETL response cache).

## What I would do next

- Run the judge at temperature 0, measure run-to-run agreement on dev first, and try a stronger
  judge model. The skill's first remedy when both rates are low is a more capable model.
- Label a fresh test set with the clarified outcome-vs-process definition from the start.
- Split the mode into narrower checks (exception hints; promised outcomes or timing; actions
  claimed without a tool call). Each is easier to judge on its own than the combined criterion.

## Files

| What | Where |
|---|---|
| Failure definition | [hw5_failure_definition.md](hw5_failure_definition.md) |
| Prompts v0, v1, v2 | [analysis/prompts/](../prompts/) |
| Labels and evidence | `analysis/state/hw5_labels/unsupported_commitment.jsonl` |
| Inputs and split | `analysis/state/hw5_trace_inputs.json`, `analysis/state/splits.json` |
| Judge versions, predictions, critiques | `analysis/state/judges/unsupported_commitment-v*.json` |
| Disagreement decisions | `analysis/state/hw5_disagreements.json` |
| Dev and test metrics | `dev-unsupported_commitment-v{0,1,2}.json`, `test-unsupported_commitment-v0.json` |
| Code | [analysis/run_judges.py](../run_judges.py), [analysis/recalc_test.py](../recalc_test.py) |
