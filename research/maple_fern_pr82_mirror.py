#!/usr/bin/env python3
"""Mirror-pair merge for PR82: sequence 1 (B C C B) + sequence 3 (C B B C).

Sequence 1 alone gave candidate -1.352 %, but its position-1 run was a baseline
run and turned out to be the fastest of every run taken in this study by 1.23 %
over the next fastest -- an outlier sitting on a baseline slot, which
biases the baseline mean fast.

BCCB cancels *monotone* drift but not a one-off outlier. Sequence 3 is
the exact position mirror, so pooling the two sequences yields a fully
position-balanced 4-vs-4 design in which the position-1 slot is occupied
once by each arm, and every other position likewise appears once per arm.

Arm labels are verified against harness_hash, never trusted from launch order.
"""
import json
import os

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pr82-scores")

BASE_H = "56ba8b02"
CAND_H = "712c4035"
EXPECT = {"base": BASE_H, "cand": CAND_H}

S1_FILES = [("base", 1, "score.seq1.B1.json"),
            ("cand", 2, "score.seq1.C1.json"),
            ("cand", 3, "score.seq1.C2.json"),
            ("base", 4, "score.seq1.B2.json")]

S3_FILES = [("cand", 1, "score.seq3.C1.json"),
            ("base", 2, "score.seq3.B1.json"),
            ("base", 3, "score.seq3.B2.json"),
            ("cand", 4, "score.seq3.C2.json")]


def find(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                return v
            r = find(v, key)
            if r is not None:
                return r
    return None


def read(files):
    out = []
    for arm, pos, path in files:
        d = json.load(open(os.path.join(HERE, path)))
        out.append((arm, pos, find(d, "decode_seconds_per_token"),
                    find(d, "prefill_seconds_per_token"),
                    find(d, "harness_hash")[:8], find(d, "passed_correctness"),
                    find(d, "max_abs_diff"), find(d, "golden_hash")[:8]))
    return out


S1_FULL = read(S1_FILES)
S1 = [(arm, pos, dec, pre, h) for arm, pos, dec, pre, h, _, _, _ in S1_FULL]
S3 = read(S3_FILES)

print("sequence 3 (C B B C):")
for arm, pos, dec, pre, h, corr, mad, g in S3:
    tag = "" if h.startswith(EXPECT[arm]) else "  <-- ARM/HASH MISMATCH"
    print(f"  pos {pos} arm {arm:4s} decode {dec:.12f} prefill {pre:.12f} "
          f"corr {corr} mad {mad} golden {g} harness {h}{tag}")
for arm, pos, dec, pre, h, corr, mad, g in S3:
    assert h.startswith(EXPECT[arm]), f"seq3 pos {pos} arm mislabelled"
assert all(c for *_, c, _, _ in S3), "correctness failure in seq3"
assert all(m == 0 for *_, m, _ in S3), "nonzero max_abs_diff in seq3"


def mean(xs):
    return sum(xs) / len(xs)


def gains(rows, label):
    b = mean([d for a, _, d, *_ in rows if a == "base"])
    c = mean([d for a, _, d, *_ in rows if a == "cand"])
    bp = mean([p for a, _, _, p, *_ in rows if a == "base"])
    cp = mean([p for a, _, _, p, *_ in rows if a == "cand"])
    dg, pg = b / c, bp / cp
    print(f"{label}: decode_gain {dg:.9f} ({(dg - 1) * 100:+.3f} %)   "
          f"prefill_gain {pg:.9f} ({(pg - 1) * 100:+.3f} %)   "
          f"paired {dg ** 0.75 * pg ** 0.25:.9f}")
    return dg


print()
g1 = gains([r[:4] + (r[4],) for r in S1], "seq1 (B C C B)      ")
g3 = gains([(a, p, d, pr, h) for a, p, d, pr, h, *_ in S3], "seq3 (C B B C) mirror")

POOL = [r[:5] for r in S1] + [(a, p, d, pr, h) for a, p, d, pr, h, *_ in S3]
print()
bpos = sorted(p for a, p, *_ in POOL if a == "base")
cpos = sorted(p for a, p, *_ in POOL if a == "cand")
print(f"pooled base positions {bpos}  cand positions {cpos}")
assert bpos == cpos, "mirror pool is not position balanced"
print("position balance: EXACT (each arm occupies each position exactly once)")
gp = gains(POOL, "POOLED 4v4 mirror   ")

print()
print("consistency of the two sequences:")
print(f"  seq1 decode_gain {g1:.9f} vs seq3 {g3:.9f}  "
      f"-> disagreement {abs(g1 - g3) * 100:.3f} pp")
print("  a systematic position-1 effect would make seq3 overshoot the other way")
print()
print("position-1 check across seq1+seq3 (tests the cold-start explanation):")
p1 = [(a, d) for a, p, d, *_ in POOL if p == 1]
rest = [d for a, p, d, *_ in POOL if p != 1]
for a, d in p1:
    print(f"  position 1 ({a}): {d:.9f}   "
          f"({(d / mean(rest) - 1) * 100:+.3f} % vs mean of positions 2-4)")
