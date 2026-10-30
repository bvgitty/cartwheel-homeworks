# HW4 write-up: failure taxonomy

*AI Evals for Engineers & PMs, Module 2. Branch `hw4-taxonomy`. Video: https://www.loom.com/share/064520be3aa549718813fc8af71d15f0*

The handout fixes where the HW4 notes live, so the full write-up is in `analysis/report/`. This
file only points to it, like the HW1–HW3 write-ups at the repo root.

| What | Where |
|---|---|
| Review summary (sample, modes, labels, SPEC revisions) | [analysis/report/review_summary.md](analysis/report/review_summary.md) |
| Interface comparison (my review app vs. the reference) | [analysis/report/interface_comparison.md](analysis/report/interface_comparison.md) |
| Review app | [analysis/review_app/](analysis/review_app/) |
| Annotations, taxonomy, labels | [analysis/state/](analysis/state/) |
| Video script | [HW4-VIDEO-SCRIPT.md](HW4-VIDEO-SCRIPT.md) |

**Headline.** Over 5 batches I open-coded 107 sessions (146 turn-traces) from my own HW3 run
(`claude-haiku-4-5`) and ended with 7 failure modes. The B4 saturation batch found 0 new modes, and
`access_overreach` was rejected. I wrote 1,022 binary labels (146 traces x 7 modes) and synced them
to Langfuse. SPEC changes: added RESP-6 and ESC-5, and clarified ESC-1 and RESP-5. Part C
(Raindrop Workshop) was optional and skipped, so there is no `workshop_notes.md`.
