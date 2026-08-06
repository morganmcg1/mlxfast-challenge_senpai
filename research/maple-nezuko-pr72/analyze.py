#!/usr/bin/env python3
"""Paired same-host decode/prefill analysis for the PR #72 new-base campaign."""
import glob
import itertools
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "newbase"
M4_TO_M5 = 0.399          # M4 us/step saved -> M5 us/step saved
MS_TO_SCORE_PCT = 14.862  # M5 ms saved -> % of normalised score


def load(tag):
    out = []
    pattern = f"{PREFIX}_{tag}_r*.json" if PREFIX else f"{tag}_r*.json"
    for path in sorted(glob.glob(os.path.join(HERE, pattern))):
        d = json.load(open(path))["metrics"]
        assert d["passed_correctness"] and d["max_abs_diff"] == 0, path
        out.append((path, d["decode_seconds_per_token"], d["prefill_seconds_per_token"]))
    return out


def summarize(name, base, cand, idx):
    b = [r[idx] for r in base]
    c = [r[idx] for r in cand]
    mb, mc = st.mean(b), st.mean(c)
    pct = (mb - mc) / mb * 100.0
    sb = st.stdev(b) if len(b) > 1 else 0.0
    sc = st.stdev(c) if len(c) > 1 else 0.0
    se = math.hypot(sb / math.sqrt(len(b)), sc / math.sqrt(len(c))) / mb * 100.0
    print(f"\n{name}: base n={len(b)} mean={mb:.10f} sd={sb/mb*100:.3f}%")
    print(f"{name}: cand n={len(c)} mean={mc:.10f} sd={sc/mc*100:.3f}%")
    print(f"{name}: improvement {pct:+.4f}%  SE {se:.4f}%  95% CI "
          f"[{pct-1.96*se:+.4f}%, {pct+1.96*se:+.4f}%]")
    return mb, mc, pct


base, cand = load("base"), load("cand")
for tag, rows in (("base", base), ("cand", cand)):
    for p, d, pf in rows:
        print(f"{tag:5s} {p:32s} decode={d:.12f} prefill={pf:.12f}")

def permutation(name, base, cand, idx):
    """Exact one-sided randomisation test: base slower than cand by chance?"""
    b = [r[idx] for r in base]
    c = [r[idx] for r in cand]
    pool = b + c
    obs = st.mean(b) - st.mean(c)
    total = extreme = 0
    for pick in itertools.combinations(range(len(pool)), len(b)):
        rest = [i for i in range(len(pool)) if i not in pick]
        stat = st.mean([pool[i] for i in pick]) - st.mean([pool[i] for i in rest])
        total += 1
        if stat >= obs - 1e-18:
            extreme += 1
    print(f"{name}: exact permutation p(one-sided) = {extreme}/{total} = {extreme/total:.4f}")


mb, mc, dpct = summarize("decode", base, cand, 1)
permutation("decode", base, cand, 1)
summarize("prefill(control)", base, cand, 2)
permutation("prefill(control)", base, cand, 2)

us_m4 = (mb - mc) * 1e6
us_m5 = us_m4 * M4_TO_M5
print(f"\nM4 us/step saved   = {us_m4:.2f}")
print(f"M5 us/step saved   = {us_m5:.2f}  (x{M4_TO_M5})")
print(f"converted score    = {us_m5/1000.0*MS_TO_SCORE_PCT:+.4f}%  (x{MS_TO_SCORE_PCT}/ms)")
