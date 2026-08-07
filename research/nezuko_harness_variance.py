#!/usr/bin/env python3
"""Is the official `harness_hash` a real blocking factor for receipt noise?

Motivation
----------
My two receipts were measured under different `harness_hash` values
(`18d98ccb...` for c03dc117, `e2d7ce70...` for df9613a8).  Before treating
their difference as a candidate-code effect I have to know whether the
harness build itself moves the measurement scale.

`harness_hash` turns out to be high-cardinality and time-clustered: the
organizers rebuild the harness constantly, so each build sees only a handful
of submissions.  That makes it a *mechanistically motivated* blocking factor,
and a much sharper one than the wall-clock adjacency tested in section 19: two
receipts minutes apart usually share a build, but not always, and two receipts
days apart occasionally do.

The baseline arm is the ideal probe.  It is byte-identical pinned code, so any
variance it shows that tracks harness identity is pure instrument change.

Method
------
One-way random-effects ANOVA over harness groups with n >= 2:

    MS_within  = SS_within  / (N - k)
    MS_between = SS_between / (k - 1)
    n0         = (N - sum(n_g^2)/N) / (k - 1)      # unbalanced design
    var_harness = max(0, (MS_between - MS_within) / n0)

`var_harness / (var_harness + MS_within)` is the intraclass correlation: the
share of a single draw's variance that a same-harness control would remove.
That number is directly comparable with the adjacency benefit measured in
section 19, and it feeds the same estimator economics.

A bare "F < 1, no effect" is not actionable, so the F test is calibrated two
ways, both by simulation rather than by special functions:

  * a permutation null (shuffle rows across the observed group-size profile)
    gives the exact reference distribution of F;
  * injecting a synthetic harness effect of known ICC and finding the largest
    ICC whose 5th percentile of F still exceeds the observed F gives a
    one-sided 95% upper bound on the real ICC.

That upper bound is the operationally meaningful number: it is the most a
same-harness control could possibly buy, and it is directly comparable with
the 29.3% break-even derived in section 19.3.

No GPU, no repo state, no receipt cost.

Usage: python3 research/nezuko_harness_variance.py [cached_submissions.json]
"""
import json
import math
import os
import random
import statistics as st
import subprocess
import sys

SEED = 20260807
NPERM = 4000

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
R1_HARNESS = "18d98ccb"
R2_HARNESS = "e2d7ce70"


def load(argv):
    if len(argv) > 1:
        return json.load(open(argv[1]))
    tok = next((os.environ[k] for k in
                ("MLXFAST_API_TOKEN", "YUKON_API_TOKEN", "SUPABASE_ACCESS_TOKEN")
                if os.environ.get(k)), None)
    if not tok:
        sys.exit("NO_TOKEN_FOUND")
    url = f"https://api.mlx.fast/api/benchmarks/{BENCH}/submissions"
    out = subprocess.run(["curl", "-s", "-H", f"Authorization: Bearer {tok}", url],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def anova(groups):
    """Unbalanced one-way random-effects ANOVA. groups: list of value lists."""
    groups = [g for g in groups if len(g) >= 2]
    k = len(groups)
    ns = [len(g) for g in groups]
    N = sum(ns)
    grand = sum(sum(g) for g in groups) / N
    ss_w = sum(sum((x - st.mean(g)) ** 2 for x in g) for g in groups)
    ss_b = sum(len(g) * (st.mean(g) - grand) ** 2 for g in groups)
    ms_w = ss_w / (N - k)
    ms_b = ss_b / (k - 1)
    n0 = (N - sum(n * n for n in ns) / N) / (k - 1)
    var_h = max(0.0, (ms_b - ms_w) / n0)
    return dict(k=k, N=N, grand=grand, ms_w=ms_w, ms_b=ms_b, n0=n0,
                var_h=var_h, F=ms_b / ms_w if ms_w else float("nan"),
                icc=var_h / (var_h + ms_w) if (var_h + ms_w) else 0.0)


def f_only(groups):
    return anova(groups)["F"]


def regroup(flat, sizes, rng):
    xs = flat[:]
    rng.shuffle(xs)
    out, i = [], 0
    for n in sizes:
        out.append(xs[i:i + n])
        i += n
    return out


def calibrate(groups, f_obs, rng):
    """Permutation null for F, plus a one-sided 95% upper bound on the ICC."""
    groups = [g for g in groups if len(g) >= 2]
    sizes = [len(g) for g in groups]
    flat = [x for g in groups for x in g]
    mu, sd = st.mean(flat), st.stdev(flat)

    null = sorted(f_only(regroup(flat, sizes, rng)) for _ in range(NPERM))
    p_lo = sum(1 for f in null if f <= f_obs) / len(null)

    def pct5_given(icc):
        """5th percentile of F when a harness effect of this ICC is present."""
        sd_h = sd * math.sqrt(icc)
        sd_w = sd * math.sqrt(1.0 - icc)
        fs = []
        for _ in range(600):
            # one shared harness offset per group, plus per-draw noise
            sim = [[mu + off + rng.gauss(0, sd_w) for _ in range(n)]
                   for n, off in ((n, rng.gauss(0, sd_h)) for n in sizes)]
            fs.append(f_only(sim))
        fs.sort()
        return fs[int(0.05 * len(fs))]

    lo, hi = 0.0, 0.60
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        if pct5_given(mid) > f_obs:
            hi = mid
        else:
            lo = mid
    return dict(p_lo=p_lo, null_med=null[len(null) // 2],
                null_p05=null[int(0.05 * len(null))],
                null_p95=null[int(0.95 * len(null))], icc_hi=hi)


def report(name, groups, single_sd_pct_of=None, rng=None):
    a = anova(groups)
    sd_w = math.sqrt(a["ms_w"])
    sd_h = math.sqrt(a["var_h"])
    sd_tot = math.sqrt(a["var_h"] + a["ms_w"])
    ref = single_sd_pct_of if single_sd_pct_of else a["grand"]
    print(f"--- {name} ---")
    print(f"  harness groups with n>=2 : {a['k']}   rows used: {a['N']}")
    print(f"  effective group size n0  : {a['n0']:.3f}")
    print(f"  within-harness  sd       : {sd_w:.6g}  ({100*sd_w/ref:.4f}% of mean)")
    print(f"  between-harness sd       : {sd_h:.6g}  ({100*sd_h/ref:.4f}% of mean)")
    print(f"  total single-draw sd     : {sd_tot:.6g}  ({100*sd_tot/ref:.4f}% of mean)")
    print(f"  F({a['k']-1}, {a['N']-a['k']})        : {a['F']:.4f}")
    print(f"  ICC (share a same-harness control removes) : {100*a['icc']:.2f}%")
    if a["icc"] > 0:
        print(f"  -> contrast sd shrinks by factor "
              f"{math.sqrt(1-a['icc']):.4f}  "
              f"(= {100*(1-math.sqrt(1-a['icc'])):.2f}% benefit)")
    else:
        print("  -> variance component pinned at zero: no benefit at all")
    if rng is not None:
        c = calibrate(groups, a["F"], rng)
        print(f"  permutation null for F ({NPERM} shuffles):")
        print(f"    median {c['null_med']:.4f}   p05 {c['null_p05']:.4f}   "
              f"p95 {c['null_p95']:.4f}")
        print(f"    P(F_null <= F_obs) = {c['p_lo']:.4f}")
        print(f"  one-sided 95% upper bound on ICC : {100*c['icc_hi']:.2f}%")
        print(f"    -> best-case contrast-sd benefit <= "
              f"{100*(1-math.sqrt(1-c['icc_hi'])):.2f}%")
    print()
    return a


def main():
    doc = load(sys.argv)
    rows = doc["submissions"] if isinstance(doc, dict) else doc
    by_h = {}
    for r in rows:
        m = r.get("officialMetrics") or {}
        h = (m.get("harness_hash") or "")[:8]
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if h and bd and bp:
            by_h.setdefault(h, []).append((bd, bp))

    sizes = sorted((len(v) for v in by_h.values()), reverse=True)
    multi = [s for s in sizes if s >= 2]
    print(f"rows with harness+baseline : {sum(sizes)}")
    print(f"distinct harness builds    : {len(sizes)}")
    print(f"builds with n>=2           : {len(multi)}  "
          f"(covering {sum(multi)} rows)")
    print(f"largest build group        : {sizes[0]}")
    print(f"median group size          : {st.median(sizes)}")
    for h, lbl in ((R1_HARNESS, "receipt #1 c03dc117"),
                   (R2_HARNESS, "receipt #2 df9613a8")):
        print(f"  build {h} ({lbl}): {len(by_h.get(h, []))} row(s) in corpus")
    print()

    rng = random.Random(SEED)
    report("baseline decode_seconds_per_token",
           [[x[0] for x in v] for v in by_h.values()], rng=rng)
    report("baseline prefill_seconds_per_token",
           [[x[1] for x in v] for v in by_h.values()], rng=rng)


if __name__ == "__main__":
    main()
