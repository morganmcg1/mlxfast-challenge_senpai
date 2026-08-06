#!/usr/bin/env python3
"""Position-balanced (B C C B) merge of four ./benchmark.sh --local-iterate scores for PR #82."""
import json
import sys


def load(path):
    d = json.load(open(path))
    return d.get("metrics", d)


ORDER = [
    ("B1", "score.local-iterate.baseline.json"),
    ("C1", "score.local-iterate.candidate.json"),
    ("C2", "score.local-iterate.candidate2.json"),
    ("B2", "score.local-iterate.baseline2.json"),
]

runs = {}
for name, path in ORDER:
    runs[name] = load(path)

print("pos arm decode_s_per_tok  prefill_s_per_tok  corr  max_abs_diff  golden8   harness8")
for i, (name, _) in enumerate(ORDER, start=1):
    x = runs[name]
    print(
        "%d   %-2s  %.12f     %.12f     %-5s %s             %s  %s"
        % (
            i,
            name,
            x["decode_seconds_per_token"],
            x["prefill_seconds_per_token"],
            x["passed_correctness"],
            x["max_abs_diff"],
            x["golden_hash"][:8],
            x["harness_hash"][:8],
        )
    )

bd = (runs["B1"]["decode_seconds_per_token"] + runs["B2"]["decode_seconds_per_token"]) / 2
cd = (runs["C1"]["decode_seconds_per_token"] + runs["C2"]["decode_seconds_per_token"]) / 2
bp = (runs["B1"]["prefill_seconds_per_token"] + runs["B2"]["prefill_seconds_per_token"]) / 2
cp = (runs["C1"]["prefill_seconds_per_token"] + runs["C2"]["prefill_seconds_per_token"]) / 2

dg = bd / cd
pg = bp / cp
print()
print("mean baseline decode  = %.12f" % bd)
print("mean candidate decode = %.12f" % cd)
print("mean baseline prefill  = %.12f" % bp)
print("mean candidate prefill = %.12f" % cp)
print("decode_gain     = %.9f  (%+.3f %%)" % (dg, (dg - 1) * 100))
print("prefill_gain    = %.9f  (%+.3f %%)" % (pg, (pg - 1) * 100))
print("paired_estimate = %.9f" % (dg ** 0.75 * pg ** 0.25))
print()
print("adjacent pair B1/C1 decode_gain = %.9f" % (runs["B1"]["decode_seconds_per_token"] / runs["C1"]["decode_seconds_per_token"]))
print("adjacent pair B2/C2 decode_gain = %.9f" % (runs["B2"]["decode_seconds_per_token"] / runs["C2"]["decode_seconds_per_token"]))
print("baseline repeat spread B2/B1-1 = %+.3f %%" % ((runs["B2"]["decode_seconds_per_token"] / runs["B1"]["decode_seconds_per_token"] - 1) * 100))
print("candidate repeat spread C2/C1-1 = %+.3f %%" % ((runs["C2"]["decode_seconds_per_token"] / runs["C1"]["decode_seconds_per_token"] - 1) * 100))

golds = {runs[n]["golden_hash"] for n, _ in ORDER}
print()
print("distinct golden_hash values across all four runs: %d" % len(golds))
print("all passed_correctness: %s" % all(runs[n]["passed_correctness"] for n, _ in ORDER))
print("all max_abs_diff == 0: %s" % all(runs[n]["max_abs_diff"] == 0 for n, _ in ORDER))
sys.exit(0)
