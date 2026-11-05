# HW5 write-up: LLM judge for `unsupported_commitment`

*AI Evals for Engineers & PMs, Module 2. Branch `hw5-judge`. Video: (link)*

The full write-up is in `analysis/report/`, next to the metrics files the handout requires. This
file only points to it, like the HW1–HW4 write-ups at the repo root.

| What | Where |
|---|---|
| Judge report (labels, split, revisions, test result, verdict) | [analysis/report/hw5_judge_report.md](analysis/report/hw5_judge_report.md) |
| Failure definition | [analysis/report/hw5_failure_definition.md](analysis/report/hw5_failure_definition.md) |
| Prompts | [analysis/prompts/](analysis/prompts/) |
| Live recalculation script | [analysis/recalc_test.py](analysis/recalc_test.py) |

**Headline.** I built a `gpt-4o-mini` judge for the most frequent HW4 failure mode, from 132
conversation-level labels (train 26 / dev 53 / test 53). Reviewing the 18 v0 dev disagreements found
12 judge errors and 6 of my own labeling errors, and it sharpened the definition (outcome versus
process). Two revisions did not beat v0 on dev, so I froze v0. On test it scored TPR 0.53
[0.37, 0.68] and TNR 0.35 [0.17, 0.59]. TPR + TNR is below 1, so I would not use this judge.
