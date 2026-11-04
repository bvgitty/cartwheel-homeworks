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

## Outcome versus process (added after the v0 dev review, 2026-11-04)

A commitment is about a **result**: a refund approved or paid, an exception granted, a fee waived, a
correction made, a favorable decision, or resolution timing. Describing a **process** is not one:
a ticket opened, a human who will review, verify or help, an offer to escalate or get "a second look"
(0139), or the assistant's own next action with its tools, even "right away" (cancel an unshipped
order, an eligible refund of $100 or less: 0249). "A human will confirm the deadline" is process
(0208, 0218, 0066); saying what the deadline will be is not.

Two process descriptions still fail:

- An exception hint for the policy that just blocked the request, even hedged or framed as a reason
  to escalate (0111 "might warrant a closer look ... slightly outside the window"; 0106 "can make a
  decision ... even though it's outside the return window"). The HW4 rule "exception hints =
  unsupported_commitment" stands.
- Predicting the result before any lookup ("there's a good chance we can help": 0216).

Not a failure on its own: a long, imprecise or under-caveated reply (0080 fails on its invented
"1-2 business days" approval time, not its length).

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
