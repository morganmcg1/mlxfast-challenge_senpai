#!/usr/bin/env python3
"""Final PR82 estimate: every base-tree and candidate-tree run in the study.

The K arm of the attribution sequence is the *same tree* as the baseline
(harness 56ba8b02), so it contributes base-tree observations too. The KI arm is
a third tree and is excluded here, as is the mis-armed position-4 run of that
sequence. Arms are keyed by harness_hash throughout, never by launch order.
"""
import json
import os
import statistics as st

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pr82-scores")

BASE = "56ba8b02"
CAND = "712c4035"

# (sequence, position, expected arm-hash, score file)
RUNS = [
    ("seq1", 1, BASE, "score.seq1.B1.json"),
    ("seq1", 2, CAND, "score.seq1.C1.json"),
    ("seq1", 3, CAND, "score.seq1.C2.json"),
    ("seq1", 4, BASE, "score.seq1.B2.json"),
    ("seq2", 1, BASE, "score.attrib.K1.json"),
    ("seq2", 5, BASE, "score.attrib.K2.json"),
    ("seq3", 1, CAND, "score.seq3.C1.json"),
    ("seq3", 2, BASE, "score.seq3.B1.json"),
    ("seq3", 3, BASE, "score.seq3.B2.json"),
    ("seq3", 4, CAND, "score.seq3.C2.json"),
]


def load(path):
    d = json.load(open(os.path.join(HERE, path)))
    return d.get("metrics", d)


b, c = [], []
for seq, pos, arm, path in RUNS:
    m = load(path)
    assert m["harness_hash"].startswith(arm), f"{seq} pos {pos} arm mislabelled"
    assert m["passed_correctness"] and m["max_abs_diff"] == 0, f"{seq} pos {pos}"
    (b if arm == BASE else c).append(m["decode_seconds_per_token"])

print(f"base-tree decode runs (n={len(b)}): " + " ".join(f"{x:.9f}" for x in sorted(b)))
print(f"cand-tree decode runs (n={len(c)}): " + " ".join(f"{x:.9f}" for x in sorted(c)))
print()
print(f"mean   base {st.mean(b):.12f}  cand {st.mean(c):.12f}  "
      f"gain {st.mean(b)/st.mean(c):.9f} ({(st.mean(b)/st.mean(c)-1)*100:+.3f} %)")
print(f"median base {st.median(b):.12f}  cand {st.median(c):.12f}  "
      f"gain {st.median(b)/st.median(c):.9f} "
      f"({(st.median(b)/st.median(c)-1)*100:+.3f} %)")
print(f"min    base {min(b):.12f}  cand {min(c):.12f}  "
      f"gain {min(b)/min(c):.9f} ({(min(b)/min(c)-1)*100:+.3f} %)")

allruns = sorted(b + c)
rest = allruns[1:]
print()
print(f"all-run decode spread: {(allruns[-1]/allruns[0]-1)*100:+.3f} % "
      f"({allruns[0]:.9f} .. {allruns[-1]:.9f})")
print(f"the single fastest run is {(rest[0]/allruns[0]-1)*100:.3f} % below the "
      f"next fastest; runs 2-10 span only {(rest[-1]/rest[0]-1)*100:.3f} %")
trimmed = [x for x in b if x != allruns[0]]
print(f"excluding it, base-tree mean {st.mean(trimmed):.12f} "
      f"-> gain {st.mean(trimmed)/st.mean(c):.9f} "
      f"({(st.mean(trimmed)/st.mean(c)-1)*100:+.3f} %)")
