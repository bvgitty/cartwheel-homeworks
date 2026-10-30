# HW4 review summary: Cartwheel failure taxonomy

*AI Evals for Engineers & PMs, Module 2. Branch `hw4-taxonomy`. Video: https://www.loom.com/share/064520be3aa549718813fc8af71d15f0*

## Reviewed sample

**Source.** Live Langfuse traces from my Homework 3 run. The population is the 250 final HW3
scenarios: 250 sessions, 320 turn-traces, with the agent on `claude-haiku-4-5`. By role, the
sessions are 164 shopper, 51 merchant and 35 support. Two HW2 development traces with no messages
are skipped by the loader.

**Unit.** Batches sample scenarios (one session each), and every turn-trace of a picked session is
reviewed and labeled. Each batch was drawn only from sessions not already in the sample, so no
trace counts toward two batches.

| Batch | Method | Sessions | Traces | Roles (shopper / merchant / support) |
|---|---|---|---|---|
| B1 | 15 uniform + 15 k-means cluster representatives | 30 | 42 | 19 / 7 / 4 |
| B2 | Stratified on user role (chosen before looking at outcomes), 10 per role | 30 | 39 | 10 / 10 / 10 |
| B3 | Depth search: deterministic trigger filters per candidate mode, random within hits, positives and close negatives | 25 | 38 | 23 / 1 / 1 |
| B4 | 15 uniform, after the taxonomy was drafted (saturation check) | 15 | 16 | 11 / 4 / 0 |
| B5 | Second depth search after revising definitions (modes still short of positives or close negatives) | 7 | 11 | 7 / 0 / 0 |
| **Total** | | **107** | **146** | 70 / 22 / 15 |

**Open coding.** Every trace was read with the first-failure stopping rule. The saved state holds:

- 85 open codes, 50 of them marked as the trace's first failure;
- 48 "no failure observed" notes;
- 12 notes flagged as spec gaps (desirable behavior SPEC.md did not require; not counted as
  failures).

**Search suggestions.** B3 and B5 retrieved 32 suggestions. Each one was reviewed by hand: 12
accepted and 20 rejected (`analysis/state/suggestions.json`).

## Final taxonomy (7 modes)

All modes are binary (Fail = failure present). Full definitions, boundaries, positives, close
negatives, source annotations and revision history are in `analysis/state/patterns.json`. All seven
are expected to need an LLM judge.

| Mode | Fail if… | Requirement |
|---|---|---|
| `unsupported_commitment` | the reply commits to an outcome, follow-up or exception that no tool result or policy supports | RESP-2, ESC-1, ESC-5, SCOPE-2 |
| `malformed_tool_query` | a tool gets wrong or misplaced arguments (e.g. store name in `find_order`'s product query), causing extra calls | RESP-6 |
| `skips_available_tool` | the agent guesses, asks the user, or stops when an available tool would have answered | RESP-6, RESP-3 |
| `fails_to_escalate` | an escalation trigger applies and `escalate_to_human` is not called (including sending the user to the store instead) | ESC-1 to ESC-4 |
| `denial_not_explained` | a refusal or escalation omits the policy and the reason | RESP-4 |
| `confusing_reply` | the reply obscures the decision, reason or next step (vague, contradictory, re-asks a settled question) | RESP-5 |
| `tone_mismatch` | the tone conflicts with the user's evident state (cheerful opener to a frustrated user, mirroring hostility) | RESP-5 |

## Sample fractions

Every trace has a saved judgment for every mode: 146 × 7 = 1,022 labels in
`analysis/state/labels/<mode>.jsonl`, each also written to Langfuse as a score. These are **sample
fractions, not prevalence estimates**. B3 and B5 were picked by depth searches for these modes, and
B1 used clustering, so failures are over-represented. Homework 5 estimates prevalence on the full
trace store.

| Mode | Fail traces | Sample fraction (of 146) | Sessions | Pass traces |
|---|---|---|---|---|
| `unsupported_commitment` | 32 | 21.9% | 28 | 114 |
| `malformed_tool_query` | 13 | 8.9% | 13 | 133 |
| `skips_available_tool` | 10 | 6.8% | 10 | 136 |
| `fails_to_escalate` | 10 | 6.8% | 10 | 136 |
| `denial_not_explained` | 4 | 2.7% | 4 | 142 |
| `confusing_reply` | 4 | 2.7% | 4 | 142 |
| `tone_mismatch` | 3 | 2.1% | 3 | 143 |
| Any mode | 55 | 37.7% | | 91 |

## Stability: the final 15 traces

B4 was 15 uniformly sampled sessions (16 traces), reviewed blind after the taxonomy was drafted.
**0 of them produced a previously unseen consequential mode.** Four traces failed, all under
existing modes:

- `skips_available_tool`: 0175 (no help-center search for payout timing) and 0247 (asked the user
  instead of calling `find_order`);
- `malformed_tool_query`: 0167;
- `unsupported_commitment`: 0034 (carrier interception, "expedited options" via a ticket).

B4 did add boundary cases:

- 0223 and 0247 became close negatives for `malformed_tool_query` (vague user wording passed on as
  given);
- 0175 sharpened the line between `skips_available_tool` and `fails_to_escalate`.

## One taxonomy revision: `unclear_reply` → `verbose_or_unrequested_detail` → `confusing_reply`

1. **After B1**, `unclear_reply` failed replies where the user could not tell the decision or next
   step.
2. **In B2**, my own notes treated long replies inconsistently. I marked verbosity as the first
   failure in 0137, 0088 and 0251, but not in similarly long 0133, 0057 and 0094. I renamed the mode
   `verbose_or_unrequested_detail` and tried a rule based on unrequested detail.
3. **Round 3 (B3)** showed the real question was whether length alone is a failure. SPEC.md had no
   brevity requirement, so I decided that length alone is a Pass recorded as a spec gap, and only
   confusion fails. Under that rule, 0007, 0251 and 0088 (length only) became close negatives. 0140
   (re-asks a settled question), 0137 (confusing request for the price) and 0080 ("a certain
   threshold", "$120 is on the larger side" muddle why approval is needed) stayed Fail.
4. **The AgentDebug comparison** then showed the name was unclear. Re-asking a settled question is a
   memory failure there, not verbosity, and since round 3 the Fail line had been confusion anyway.
   The mode became `confusing_reply`.
5. **The brevity gap** is now closed in SPEC.md (RESP-5 revision below). Labels were made under the
   earlier RESP-5, so length alone is still a Pass in this label set. Brevity is a candidate future
   mode.

Other revisions recorded in `patterns.json`:

- **Merges:**
  - `deflects_instead_of_escalating` → `fails_to_escalate`. B2 showed missing escalations with no
    deflection, so deflection is one way of not escalating.
  - `promises_queued_refund` and `acts_on_unverified_claim` → `unsupported_commitment`. One product
    change fixes all of them: state only what tools returned or policy says.
- **Exception hints:** moved from `denial_not_explained` to `unsupported_commitment`. 0022 and 0056
  state the reason clearly; the problem is the hinted exception.
- **Rejected group:** `access_overreach` (AUTH-1, RESP-4) was dropped as a final mode. It had only 2
  positives, and the `permission_denied` pool is exhausted (the B5 search returned 0 new hits). It
  stays recorded as a low-frequency observation to target with synthetic scenarios.

## Rejected search suggestion

One example, `sugg-B3-22`: the B3 depth search for `malformed_tool_query` returned support-0164,
where the agent's `find_order` query included a store name. I rejected it. The user named the
product and store in a way that did not mark the store as a store, and the agent passed the user's
wording on as given.

That decision became part of the boundary: "Pass if the misplaced argument comes from the user's own
ambiguous wording… and the agent passed it on as given." 0164 is a close negative for the mode, and
SPEC RESP-6 carries the same carve-out. All 20 rejections and their reasons are in
`suggestions.json`.

## AgentDebug comparison

I compared the taxonomy with AgentDebug (arXiv 2509.25370), which groups failures under Memory,
Reflection, Planning, Action and System modules.

| Our mode | AgentDebug type |
|---|---|
| `malformed_tool_query` | Parameter Error |
| `skips_available_tool` | Retrieval Failure |
| `fails_to_escalate` | Constraint Ignorance (partial) |
| `unsupported_commitment` | Hallucination + Outcome Misinterpretation |
| `denial_not_explained` | Over-simplification (partial) |
| `confusing_reply`, `tone_mismatch` | no counterpart (user-facing communication, which AgentDebug does not cover) |

The comparison led to two decisions:

- **Unclear name** (acted on): the `confusing_reply` rename above.
- **Possible split** (not taken): `unsupported_commitment` spans two AgentDebug types. A queued
  refund read as done is Outcome Misinterpretation; invented exceptions and timing are
  Hallucination. I kept it merged because one product change fixes both.

No mode was added. AgentDebug's other types (e.g. system errors, step limits) did not appear in my
annotations.

## SPEC.md revisions and motivating annotations

| Revision | Motivating annotations |
|---|---|
| **RESP-6 (new).** Call the read tool that returns the fact before guessing or asking. Pass each argument in its intended field (`find_order` takes only the product description); pass the user's ambiguous wording on as given. Source for `skips_available_tool` and `malformed_tool_query`, which had no SPEC ID. | ann-774vbtr9 (0042, return window guessed without `check_return_eligibility`), ann-33dsxjcs (0247), ann-17xsqv0s (0175); ann-rng8ixu1 (0103), ann-ir5ngqdn (0167), ann-07m8jsw2 (0216) |
| **ESC-1 (clarified).** For an eligible above-threshold refund, call `issue_refund` (which queues it) and do not also call `escalate_to_human`. The reply says it is queued and does not promise approval. | ann-lzfusqsg (0110), ann-ikje54a9 (0225) |
| **ESC-5 (new).** A reply may state the 24-hour human response time (`sla_hours`, cw-escalations) but not promise resolution timing. | Label decision on 2026-10-28: "reach out / follow up within 24 hours" in 0066 and 0105 is a Pass; 0014 stays a Fail for its exception hint, not the 24 hours |
| **RESP-5 (extended).** Keep replies brief: decision, reason, next step; no unrequested detail. | Spec-gap notes ann-5numnldv (0007), ann-hdzzwob9 (0106), ann-7e9mr1vv (0138), ann-xum76jkg (0061) |

**Root cause found during review.** The system prompt contradicts ESC-1. `agent/agent.py:81-83`
says to call `escalate_to_human` for "a refund above the auto-approval threshold", and the prompt
never states the $100 threshold. This likely explains many `unsupported_commitment` and
`fails_to_escalate` cases on refunds over $100: in HW3, `issue_refund` was called 7 times against
41 escalations. The prompt fix belongs to a later homework.

**Spec gaps recorded but not adopted:**

- greet the user by name (ann-zbdpnln1 in 0153, ann-ekgeys6p in 0215);
- `issue_refund` should record the refund-initiated date (ann-1tc4u3p9, 0010);
- a tool to look up the user's open tickets (ann-0464acd7, 0039);
- quote the policy snippet, not only its ID (ann-12ou4edw, 0020).

## Preparing for Homework 5

Homework 5 needs at least 30 Pass and 30 Fail labels per mode. Every mode has more than 100 Pass
labels. Only `unsupported_commitment` reaches 30 Fail (32), with little to spare across splits. The
other six modes have 3 to 13 Fail labels and need synthetic scenarios targeting the failure, and so
does `access_overreach` if it is revived.

## Not done

Part C (Raindrop Workshop) was skipped, so there is no `workshop_notes.md`.
