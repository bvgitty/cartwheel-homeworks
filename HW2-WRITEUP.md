# Homework 2 write-up: the traced, authenticated agent endpoint

*AI Evals for Engineers & PMs, Module 1. Branch `hw2-tracing`.*

## Summary

- **Identity comes from the server, not the conversation.** `POST /sessions` checks the claimed role against the database and builds the `AuthContext` from the database row. Every later message is authorized by a signed token that is bound to one session.
- **Every message is one trace.** The root span `cartwheel.session_message` records who asked (`cartwheel.user_role`, `cartwheel.user_id`), which prompt answered (`cartwheel.prompt_version`), the session, and the input and output messages. The automatic model and tool spans nest under it.
- **Tool spans carry the caller and the permission decision.** These are `cartwheel.user_role`, `cartwheel.user_id`, `cartwheel.store_id` (merchants only), `cartwheel.permission_denied` and, on a denial, `cartwheel.permission_denied.reason`.
- **A real trace caught a bug that the tests missed.** In the first denial trace, the reason attribute was absent. The code still had a `...` placeholder, which is valid Python that does nothing, so every test passed. I fixed the line and added a fake-span test that fails on the old code.
- **The prompt version works as a fingerprint.** The same request under the HW1 original prompt and the current prompt gives `d108f6949e5e` and `11bf9b5e1b26`.

Setup: Windows, Docker Desktop with local Langfuse (`observability/docker-compose.yml`), model `claude-haiku-4-5`, `TRACELOOP_TRACE_CONTENT=true`.

## What was built

| Part | Where | What it does |
|---|---|---|
| A | `observability/instrument.py` | `record_tool_result` labels the active tool span with the caller from `ctx`, then `_set_permission_denied_attributes` always sets `cartwheel.permission_denied` and adds the reason only for `error == "permission_denied"` (read with `result.get`, because success results have no `error` key). |
| B | `server/app.py` `create_session` | Unknown role → 400. Unknown user → 404. Claimed role ≠ stored role → 403. Then it builds `AuthContext` **from the database row**, stores `(ctx, SQLiteSession)` under a new UUID, and returns a signed token with `session_id`, `user_id`, `role`, `store_id` and `issued_at`. |
| C | `server/app.py` `post_message` | `_authorize` (401, 403 or 404, and returns the stored `ctx`), then builds the agent and opens the root span, sets the identity, prompt version, optional scenario id and input message, **runs the agent inside the span**, sets the output message, and returns `session_id`, `reply` and `prompt_version`. |
| D | `tests/test_observability.py` | A role mismatch raises 403 and leaves no session behind. Session A's token on session B raises 403, even for the same user, so the token is bound to the session, not just the person. Two fake-span tests cover the permission attributes. |

## Traces (`hw2-traces.json`)

| Trace | Caller | Tools | What it shows |
|---|---|---|---|
| `5531177c…` | merchant 9002, store 2 | `get_order` | The merchant asks for store 1's order 4127. The tool returns `permission_denied`. The tool span has `cartwheel.permission_denied = true` and the reason. The reply refuses without revealing which store owns the order. |
| `27e8fe03…` | support 9501 | `check_return_eligibility` → `escalate_to_human` | Order 8002 has no delivery date. The tool returns `eligible: None` with the data issue, and the agent escalates instead of inventing a deadline. |

Helper: `uv run python hw2_traces.py --list` lists recent traces. `uv run python hw2_traces.py <id> [<id>] --write` prints each trace's fields and span count and writes `hw2-traces.json`.

## Prompt-version comparison (Part F)

| Prompt | `prompt_version` | Reply to "What's the return deadline for order 8002?" (support 9501) |
|---|---|---|
| HW1 original (RESP-3 bullet removed) | `d108f6949e5e` | Escalated; a human will find the delivery date |
| Current | `11bf9b5e1b26` | Escalated; a specialist will confirm the deadline |

The hash changed with the prompt and returned exactly when it was restored. Both prompts now handle order 8002 correctly, unlike in HW1. That's because `check_return_eligibility` gives the model the data issue directly, so it no longer depends on the prompt bullet to notice it.

## Findings

1. **Traces show what tests don't.** The missing `permission_denied.reason` produced no error and no failing test. It only showed up as an absent attribute on a real span. The new fake-span test fails on the old code and passes on the fixed code.
2. **Labels describe the interface, not the provider.** Model spans are named `openai.response`, with `gen_ai.provider.name = "openai"`, although the model is Claude. That's because the Agents SDK uses an OpenAI-style interface and LiteLLM forwards the calls to Anthropic. The actual model is in `gen_ai.request.model`.
3. **Failed requests still leave a trace.** Two early traces have a root span with no attributes. Those were requests that crashed (`NameError: ctx`) after the span opened. The trace records exactly how far the request got.
4. **Observations for HW3 and HW4** (not judged here):
   - A refund request for 4127 ended without `issue_refund` (the agent asked for a reason).
   - A merchant "Cancel order 6213." called no tools.

   Single-message requests that need a follow-up are worth covering in the scenario dataset.

## Files

| Path | What |
|---|---|
| `observability/instrument.py` | Part A |
| `server/app.py` | Parts B and C |
| `tests/test_observability.py` | Part D, plus the fake-span tests |
| `hw2-traces.json` | Two selected traces |
| `hw2_traces.py` | Trace summary and `hw2-traces.json` builder |
