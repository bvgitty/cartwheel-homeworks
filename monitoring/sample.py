"""Select a random sample for estimation and extra traces for inspection."""

from __future__ import annotations

from typing import Any, Callable
import random

def select_traces(
    traces: list[dict[str, Any]],
    random_rate: float,
    risk_groups: dict[str, Callable[[dict[str, Any]], bool]],
    seed: int = 7,
) -> dict[str, Any]:
    """Select the traces that the LLM judge will review.

    The returned plan keeps two kinds of traces separate:

      1. **Random sample.** Draw
         ``max(1, round(random_rate * len(traces)))`` traces uniformly at
         random without replacement, using
         ``random.Random(seed).sample`` on the traces in their given order.
         Only this sample may be used to estimate the failure rate.
      2. **Risk groups.** For each group in ``risk_groups``, include every
         matching trace. A trace can appear in more than one group.
      3. **All traces to judge.** ``to_judge`` contains every unique trace
         selected by either method. Deduplicate the traces by ``"id"`` and
         keep the random traces first, followed by the risk groups in their
         dictionary order.
      4. Each trace dict is passed through untouched; membership lives in
         the returned plan, not as mutations of the inputs.

    Args:
        traces: the batch, each dict carrying at least an "id".
        random_rate: random sampling rate in (0, 1].
        risk_groups: group name mapped to a predicate over a trace dict.
        seed: RNG seed; the same inputs and seed produce the same plan.

    Returns:
        {"random": [trace, ...],
         "risk_groups": {name: [trace, ...], ...},
         "to_judge": [trace, ...]}

    Raises:
        ValueError: if random_rate is outside (0, 1] or a trace has no "id".
    """
    ### YOUR CODE HERE (hw7)
        # 1. Validate the inputs.
    if not (0 < random_rate <= 1):          # the allowed range is (0, 1]
        raise ValueError("random_rate must be in (0, 1]")
    for trace in traces:
        if not trace.get("id"):                    # the key every trace must carry
            raise ValueError("every trace needs an id")

    # 2. Uniform random sample (the ONLY input to the failure-rate estimate).
    k = max(1, round(random_rate * len(traces)))  # at least one; rate x number of traces
    random_sample = random.Random(seed).sample(traces, k)   # the seed; the list to draw from

    # 3. Risk groups: every matching trace, in original order.
    groups = {
        name: [t for t in traces if rule(t)]       # call the group's rule on the trace
        for name, rule in risk_groups.items()       # the dict method that gives (key, value) pairs
    }

    # 4. Union to judge: random first, then each group; one entry per id.
    to_judge = []
    seen = set()                                  # an empty set
    for trace in random_sample + [t for members in groups.values() for t in members]:  # just the lists
        if trace["id"] not in seen:
            to_judge.append(trace)
            seen.add(trace["id"])

    # 5. The plan. Memberships live here, never on the trace dicts.
    return {"random": random_sample, "risk_groups": groups, "to_judge": to_judge}



# Each function identifies one risk group in the Cartwheel traces.
DEFAULT_RISK_GROUPS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "policy_lookup": lambda t: bool(
        {"get_policy", "search_help_center"} & set(t.get("tools", []))
    ),
    "write_action": lambda t: bool(
        {"issue_refund", "cancel_order"} & set(t.get("tools", []))
    ),
    "multi_turn": lambda t: int(t.get("turn_count", 0)) > 1,
}
