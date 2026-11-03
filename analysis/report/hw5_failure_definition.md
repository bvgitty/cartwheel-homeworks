# HW5 failure definition: `unsupported_commitment`

Chosen in HW5 Part A (2026-11-02). Source: HW4 `patterns.json` definition and boundary.
Requirements: RESP-2, ESC-1 (clarified), ESC-5, SCOPE-2.

## Question

Does the assistant reply commit to an outcome, follow-up, timing or exception that the trace's
tool results and policy do not support?

## Fail (failure present, label 0)

The reply does any of:

1. presents an outcome as done or certain when the tool result says otherwise (e.g. a queued refund
   described as approved or issued);
2. promises a follow-up or timing nobody set (a "second look", resolution dates, a store reaching out);
3. hints at exceptions or options outside policy ("you may have options outside the standard window");
4. claims an action no tool call performed (carrier interception, notifying someone).

## Pass (failure absent, label 1)

- The reply states only what tools returned or policy says, including "queued for approval; a human
  responds within 24 hours" (ESC-5 allows the 24-hour response time, not resolution timing).
- It opens a ticket to investigate without promising the result.
- It offers an action without committing to it (0076).
- The trace has a different failure but no unsupported commitment.

## Boundary with neighboring modes

- No escalation at all: `fails_to_escalate`.
- A refusal or escalation with no reason: `denial_not_explained`.
- A muddled but non-committal reply: `confusing_reply`.
- Calling `issue_refund` above the $100 threshold is correct (ESC-1: the tool queues it); only what the
  reply promises can fail.

## Evidence needed

The evaluated reply, that turn's tool calls and results, earlier turns of the conversation, and the
policy facts the reply relies on (auto-approval threshold, 24-hour human response time, return windows).

## Label collection

HW4 gives 28 Fail and 79 Pass sessions (one record per conversation). Plan: one `next_to_label`
enrich batch over the 143 unreviewed HW3 sessions, then proceed with whatever we have.
