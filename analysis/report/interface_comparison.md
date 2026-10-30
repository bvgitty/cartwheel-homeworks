# Interface comparison: `analysis/review_app/` vs the reference interface

The review app is a standard-library HTTP server (`analysis/review_app/server.py`) and a single page
(`analysis/review_app/index.html`) with four views: Review, Taxonomy, Label and Progress. Run it with
`uv run python -m analysis.review_app.server` and open http://localhost:8020. It reads live Langfuse
traces through a local cache (`build_cache.py`). No offline export was used.

## Retained from the reference: whole-file state behind a thin API

The reference server (`analysis/server.py`) keeps each piece of review state in one JSON file under
`analysis/state/`. The page reads a file with GET and writes it back whole with POST. The review app
keeps that design for `annotations.json`, `patterns.json` and `suggestions.json`. The page stays one
static HTML file with no build step, and the committed state files are exactly what the reviewer saw
and saved. The server only checks mode names, including the reserved demo name
`unsupported_policy_claim`.

Labels are the one exception. Each judgment goes through `POST /api/label`, which writes the Langfuse
score first and then appends to `labels/<mode>.jsonl`. Superseded rows are kept with `superseded_by`,
so a changed judgment never loses the earlier one.

## Changed after inspecting the traces: one session, not one trace, is the review unit

The reference interface shows one trace at a time. Cartwheel writes one Langfuse trace per user turn,
and when I read the traces, later turns often made no sense alone. For example, in support-0110 the
second turn (trace `bdc0ab91`) tells the shopper "I already found it… Order #2341… $380.50" and makes
no tool call. The `find_order` call that found the order is in the first turn (`887b7dea`). Read
alone, the second turn looks like an invented order. Read in order, it is correct.

The Review view therefore:

- groups traces by `cartwheel.session_id` and shows the whole conversation in time order;
- shows each tool call and its result in place, between the user message and the reply that uses it
  (the standard Langfuse view shows tool spans apart from the reply);
- attaches each free-form note to a specific turn's trace, because labels are per trace.

Sampling follows the same logic: batches pick scenarios (sessions), and every turn of a picked session
is reviewed. That gives 107 sessions and 146 traces.

Two other changes came from using the app:

- **Inline reason box.** Accepting or rejecting an AI suggestion asks for a reason in an inline text
  box. The first version used `prompt()`, which VS Code's built-in browser blocks, so the buttons
  silently did nothing.
- **Row-based Label view.** The view has one row per trace and one cell per final mode. Each cell is
  pre-filled with a draft from the review evidence: Fail for positives, Pass with the boundary note
  for close negatives, and Pass marked "unchecked" otherwise. Saving a row writes all seven
  judgments. Drafts are shown dashed and never count as labels until the row is saved.

## Remaining limitation: one evidence box per row

The Label view has one evidence box per row, and its text goes to every cell changed in that row.
When a trace fails several modes, the evidence on some cells describes a different mode. For example,
support-0225 (`b62178d3`) is correctly labeled Fail for `malformed_tool_query` (store name passed in
the product query), but its evidence reads "fail to escalate: order amount > 100". The label is right
and the evidence is misfiled. This matters for Homework 5, where the evidence becomes the critique
for judge examples. The fix is one evidence field per cell, shown when a cell is flipped to Fail.

A smaller one: two rare actions, retracting a note and recording why a mode was edited, still use
`prompt()`. They work in a normal browser but not in VS Code's built-in browser.
