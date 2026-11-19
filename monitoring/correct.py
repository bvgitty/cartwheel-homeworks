"""Bias-corrected failure prevalence for a monitoring period."""

from __future__ import annotations
import numpy as np

from typing import Any, Sequence

def _sens_spec(labels, preds):
    """Failure sensitivity and pass specificity, or None if a class is missing."""
    fail_preds = [p for l, p in zip(labels, preds) if l == 1]   # predictions on human failures
    pass_preds = [p for l, p in zip(labels, preds) if l == 0]   # predictions on human passes
    if not fail_preds or not pass_preds:
        return None
    sens = sum(fail_preds) / len(fail_preds)            # flagged fraction of failures
    spec = pass_preds.count(0) / len(pass_preds)     # UNflagged fraction of passes
    return sens, spec


def _rogan_gladen(raw, sens, spec):
    """Corrected prevalence, or None when the judge is no better than chance."""
    denom = sens + spec - 1
    if denom <= 0:
        return None
    return (raw + spec - 1) / denom



def corrected_mode_prevalence(
    sample_preds: Sequence[int],
    test_labels: Sequence[int],
    test_preds: Sequence[int],
    confidence: float = 0.95,
    bootstrap_iterations: int = 20000,
    seed: int | None = 7,
) -> dict[str, Any]:
    """Bias-corrected live prevalence for one mode from sampled verdicts.

    The contract, precisely:

      1. ``raw`` is the uncorrected flag rate: ``mean(sample_preds)``.
      2. Compute the frozen judge's failure sensitivity and pass specificity
         from ``test_labels`` and ``test_preds``. Both use the monitoring
         convention that 1 means a failure is present. Failure sensitivity is
         the flagged fraction of human-labeled failures. Pass specificity is
         the unflagged fraction of human-labeled passes.
      3. Compute the Rogan-Gladen point estimate, then resample the held-out
         records and sampled predictions to obtain a percentile-bootstrap
         interval. Use a seeded NumPy generator so the committed result is
         reproducible.
      4. Resample the monitoring predictions and the paired held-out records
         independently with replacement. Keep their original sample sizes.
         Discard a draw if the correction cannot be computed. Clamp each
         retained estimate to [0, 1], then take the percentile interval.
         Raise ``ValueError`` if no replicate is valid.

    Args:
        sample_preds: the judge's 0/1 verdicts over the UNIFORM BASE sample
            only (never the risk strata; they are biased toward failure by
            design).
        test_labels: human labels for the frozen Homework 5 judge's test
            split.
        test_preds: the frozen judge's predictions on that test split.
        confidence: interval confidence level.
        bootstrap_iterations: number of percentile-bootstrap replicates.
        seed: numpy seed for a reproducible interval; None leaves the RNG
            untouched.

    Returns:
        {"raw", "corrected", "ci_low", "ci_high", "confidence",
         "failure_sensitivity", "pass_specificity", "n_sample"}
        with "corrected" clamped to [0, 1] and rates rounded to 4 places.

    Raises:
        ValueError: if an input is empty, the held-out inputs have different
            lengths, a value is not 0 or 1, a class is absent, the judge is
            missing a usable correction, or no bootstrap replicate is valid.
    """
    ### YOUR CODE HERE (hw7)
        # 1. Validate.
    if not sample_preds or not test_labels:
        raise ValueError("inputs must not be empty")
    if len(test_labels) != len(test_preds):
        raise ValueError("test labels and predictions differ in length")
    if any(v not in (0, 1) for v in [*sample_preds, *test_labels, *test_preds]):
        raise ValueError("every value must be 0 or 1")

    # 2. Point estimate.
    rates = _sens_spec(test_labels, test_preds)
    if rates is None:
        raise ValueError("the test set needs both failures and passes")
    sens, spec = rates
    raw = sum(sample_preds) / len(sample_preds)
    point = _rogan_gladen(raw, sens, spec)
    if point is None:
        raise ValueError("the judge has no usable correction (sens + spec - 1 <= 0)")

    # 3. Bootstrap: resample both sources independently, with replacement.
    rng = np.random.default_rng(seed)
    n, m = len(sample_preds), len(test_labels)
    estimates = []
    for _ in range(bootstrap_iterations):
        boot_sample = rng.choice(sample_preds, size=n, replace=True)
        idx = rng.integers(0, m, size=m)                  # m random row numbers into the test set
        boot_rates = _sens_spec([test_labels[i] for i in idx], [test_preds[i] for i in idx])
        if boot_rates is None:
            continue
        est = _rogan_gladen(float(boot_sample.mean()), *boot_rates)
        if est is None:
            continue
        estimates.append(min(1.0, max(0.0, est)))          # clamp to [0, 1]
    if not estimates:
        raise ValueError("no valid bootstrap replicate")

    # 4. Percentile interval.
    alpha = 1 - confidence                                  # 0.05 for 95%
    low, high = np.percentile(estimates, [100 * alpha / 2, 100 * (1 - alpha / 2)])

    return {
        "raw": round(raw, 4),
        "corrected": round(min(1.0, max(0.0, point)), 4),
        "ci_low": round(float(low), 4),
        "ci_high": round(float(high), 4),
        "confidence": confidence,
        "failure_sensitivity": round(sens, 4),
        "pass_specificity": round(spec, 4),
        "n_sample": n,
    }
