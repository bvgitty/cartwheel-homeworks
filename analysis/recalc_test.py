import json
import math

SPLITS = "analysis/state/splits.json"
LABELS = "analysis/state/hw5_labels/unsupported_commitment.jsonl"
JUDGE = "analysis/state/judges/unsupported_commitment-v0.json"

def wilson(successes, total, z=1.96):
    """95% Wilson interval for successes out of total."""
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom 
    return center - margin, center + margin

#which traces are in the test split
with open(SPLITS, encoding="utf-8") as f:
    test_ids = json.load(f)["unsupported_commitment"]["test"]

# Human labels: one JSON object per line (1 = Pass, 0 = Fail)
human = {}
with open(LABELS, encoding="utf-8") as f:
    for line in f:
        row = json.loads(line)
        human[row["trace_id"]] = row["label"]

# Judge verdicts from the frozen v0 record (1 = Pass, 0 = Fail)
with open(JUDGE, encoding="utf-8") as f:
    record = json.load(f)
judge = record["predictions"][record["prompt_hash"]]

print(len(test_ids), "test ids")
print(len(human), "human labels")
print(len(judge), "judge predictions")

#confusion matrix over the test split (Pass = positive)
tp = fn = tn = fp = 0
for trace_id in test_ids:
    h = human[trace_id]
    j = judge[trace_id]
    if h == 1 and j == 1:
        tp += 1
    elif h == 1 and j == 0:
        fn += 1
    elif h == 0 and j == 0:
        tn += 1
    else:
        fp += 1

print(f"TP {tp} FN {fn} TN {tn} FP {fp} (total { tp + fn + tn + fp })")

# Rates: agreement within each human class
pass_total = tp + fn
fail_total = tn + fp
tpr = tp / pass_total
tnr = tn/ fail_total

print(f"TPR {tpr:.3f} ({tp}/{pass_total} human Passes)")
print(f"TNR {tnr:.3f} ({tn}/{fail_total} human Fails)")
print(f"TPR + TNR = {tpr + tnr:.3f}  (1.0 = no better than chance)")

tpr_lo, tpr_hi = wilson(tp, pass_total)
tnr_lo, tnr_hi = wilson(tn, fail_total)
print(f"TPR 95% CI [{tpr_lo:.3f}, {tpr_hi:.3f}]")
print(f"TNR 95% CI [{tnr_lo:.3f}, {tnr_hi:.3f}]")
