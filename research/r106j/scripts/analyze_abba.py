#!/usr/bin/env python3
"""R106-J estimator for a paired two-arm ABBA sweep.

Primary metric is the exact score log-contrast

    d(ln score) = -0.75 * d(ln decode_s_per_token) - 0.25 * d(ln prefill_s_per_token)

which is dimensionless and therefore immune to the M4/M5 step-time mismatch
that makes an absolute us/step delta untransferable.

Rule 98 / the nax wall (#620 Stage 0): M4 decode reproduces the ranked M5
speedup to +0.15 %, M4 prefill misses it by -43.5 %, because prefill is 94.3 %
nax-divergent and this host is GPU generation 16. So a second, conservative
estimator is reported alongside the primary one:

    d(ln score | prefill neutral) = -0.75 * d(ln decode)

It charges nothing for the prefill half rather than transferring an M4 prefill
delta that the scored machine will not reproduce.

Each ABBA block (A B B A or its mirror) contributes one drift-cancelling
contrast; blocks are the independent unit and dof = nblocks - 1.

Usage: analyze_abba.py [runs.tsv] [control_arm] [candidate_arm]
"""

import math
import statistics
import sys

TSV = sys.argv[1] if len(sys.argv) > 1 else "research/artifacts/maple-fern-r106j/abba/runs.tsv"
# two-sided 97.5% Student-t quantiles by dof
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060}
ARM_ORDER = ["T0", "T1", "T0P", "T1P", "T0U"]


def load(path):
    rows = []
    with open(path) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != len(header):
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def read_rows(path=None):
    rows = load(path or TSV)
    return [r for r in rows if r["rc"] == "0" and r["decode_s_per_token"] != "nan"]


def arms_of(rows, control=None, candidate=None):
    """Return (control, candidate). The control is whichever arm comes first in
    ARM_ORDER, so a contrast always reads `later minus earlier`."""
    present = {r["arm"] for r in rows}
    if control and candidate:
        return control, candidate
    ordered = [a for a in ARM_ORDER if a in present]
    ordered += sorted(present - set(ARM_ORDER))
    if len(ordered) != 2:
        raise SystemExit(f"expected exactly 2 arms, found {sorted(present)}")
    return ordered[0], ordered[1]


def block_contrasts(rows, key, control, candidate):
    out = []
    for b in range(len(rows) // 4):
        blk = rows[4 * b:4 * b + 4]
        a = [math.log(float(r[key])) for r in blk if r["arm"] == control]
        c = [math.log(float(r[key])) for r in blk if r["arm"] == candidate]
        if len(a) != 2 or len(c) != 2:
            continue
        out.append(sum(c) / 2 - sum(a) / 2)
    return out


def estimate(vals):
    if not vals:
        return None
    n = len(vals)
    m = statistics.fmean(vals)
    out = {"mean": 100 * m, "n": n}
    if n > 1:
        sd = statistics.stdev(vals)
        sem = sd / math.sqrt(n)
        t = T975.get(n - 1, 1.96)
        out.update(sd=100 * sd, sem=100 * sem, dof=n - 1,
                   lo=100 * (m - t * sem), hi=100 * (m + t * sem),
                   positive_blocks=sum(1 for v in vals if v > 0))
    return out


def summarise(name, vals, unit="%"):
    est = estimate(vals)
    if est is None:
        print(f"{name}: no complete blocks")
        return None
    if "lo" not in est:
        print(f"{name}: {est['mean']:+.4f}{unit}  (n=1 block, no interval)")
        return None
    print(f"{name}: {est['mean']:+.4f}{unit}  CI95 [{est['lo']:+.4f}, {est['hi']:+.4f}]  "
          f"sd={est['sd']:.4f}{unit} n={est['n']} dof={est['dof']} "
          f"positive_blocks={est['positive_blocks']}/{est['n']}")
    return est["mean"] / 100, est["lo"] / 100, est["hi"] / 100


def analyse(rows, control=None, candidate=None):
    control, candidate = arms_of(rows, control, candidate)
    dec = block_contrasts(rows, "decode_s_per_token", control, candidate)
    pre = block_contrasts(rows, "prefill_s_per_token", control, candidate)
    score = [-0.75 * d - 0.25 * p for d, p in zip(dec, pre)]
    decode_only = [-0.75 * d for d in dec]
    within = {}
    for arm in (control, candidate):
        for key in ("decode_s_per_token", "prefill_s_per_token"):
            v = [float(r[key]) for r in rows if r["arm"] == arm]
            if len(v) > 1:
                within[(arm, key)] = {
                    "mean": statistics.fmean(v),
                    "cv": 100 * statistics.stdev(v) / statistics.fmean(v),
                    "n": len(v),
                }
    return {
        "control": control,
        "candidate": candidate,
        "n_runs": len(rows),
        "n_blocks": len(rows) // 4,
        "failures": len([r for r in rows if r["passed"] != "True"
                         or r["max_abs_diff"] not in ("0", "0.0")]),
        "golden": sorted({r["golden_hash"] for r in rows}),
        "within": within,
        "blocks": {"d_ln_decode": dec, "d_ln_prefill": pre,
                   "d_ln_score": score, "d_ln_score_decode_only": decode_only},
        "d_ln_decode": estimate(dec),
        "d_ln_prefill": estimate(pre),
        "d_ln_score": estimate(score),
        "d_ln_score_decode_only": estimate(decode_only),
    }


def main():
    control = sys.argv[2] if len(sys.argv) > 2 else None
    candidate = sys.argv[3] if len(sys.argv) > 3 else None
    rows = read_rows()
    control, candidate = arms_of(rows, control, candidate)
    print(f"tsv: {TSV}")
    print(f"control={control} candidate={candidate}")
    print(f"usable runs: {len(rows)}  complete ABBA blocks: {len(rows)//4}")

    bad = [r for r in rows if r["passed"] != "True" or r["max_abs_diff"] not in ("0", "0.0")]
    print(f"correctness failures: {len(bad)}")
    goldens = sorted({r["golden_hash"] for r in rows})
    print(f"distinct golden_hash values: {len(goldens)} -> {goldens}")
    for arm in (control, candidate):
        shas = sorted({r["worker_sha256"][:12] for r in rows if r["arm"] == arm})
        print(f"  {arm} worker sha256 prefixes: {shas}")

    for arm in (control, candidate):
        for key in ("decode_s_per_token", "prefill_s_per_token"):
            v = [float(r[key]) for r in rows if r["arm"] == arm]
            if len(v) > 1:
                cv = statistics.stdev(v) / statistics.fmean(v)
                print(f"  within-arm {arm} {key}: mean={statistics.fmean(v):.9f} "
                      f"cv={100*cv:.4f}% n={len(v)}")

    print(f"\n-- ABBA block contrasts, {candidate} minus {control}, natural log --")
    dec = block_contrasts(rows, "decode_s_per_token", control, candidate)
    pre = block_contrasts(rows, "prefill_s_per_token", control, candidate)
    summarise("d(ln decode)   ", dec)
    summarise("d(ln prefill)  ", pre)

    score = [-0.75 * d - 0.25 * p for d, p in zip(dec, pre)]
    print(f"\n-- PRIMARY: d(ln score), {candidate} minus {control}, "
          f"positive means {candidate} better --")
    res = summarise("d(ln score)    ", score)

    print("\n-- CONSERVATIVE (nax wall): prefill charged as neutral --")
    cons = summarise("d(ln score|dec)", [-0.75 * d for d in dec])

    for label, r in (("primary", res), ("conservative", cons)):
        if r and len(score) > 1:
            m, lo, hi = r
            print(f"\n-- verdict, {label} --")
            print(f"  superiority (CI excludes 0 positive): {'YES' if lo > 0 else 'no'}")
            print(f"  inferiority  (CI excludes 0 negative): {'YES' if hi < 0 else 'no'}")
            print(f"  clears the +0.40% bar (point)        : {'YES' if m > 0.004 else 'no'}")
            print(f"  clears the +0.40% bar (CI lower)     : {'YES' if lo > 0.004 else 'no'}")
    if score:
        print("\n  per-block d(ln score) %: "
              + ", ".join(f"{100*s:+.4f}" for s in score))


if __name__ == "__main__":
    main()
