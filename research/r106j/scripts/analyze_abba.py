#!/usr/bin/env python3
"""R106-J Stage 1 estimator for the T0/T1 ABBA sweep.

Primary metric is the exact score log-contrast

    d(ln score) = -0.75 * d(ln decode_s_per_token) - 0.25 * d(ln prefill_s_per_token)

which is dimensionless and therefore immune to the M4/M5 step-time mismatch
that makes an absolute us/step delta untransferable.

Each ABBA block (T0 T1 T1 T0 or its mirror) contributes one drift-cancelling
contrast; blocks are the independent unit and dof = nblocks - 1.
"""

import math
import statistics
import sys

TSV = sys.argv[1] if len(sys.argv) > 1 else "research/artifacts/maple-fern-r106j/abba/runs.tsv"
# two-sided 97.5% Student-t quantiles by dof
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}


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


def block_contrasts(rows, key):
    out = []
    for b in range(len(rows) // 4):
        blk = rows[4 * b:4 * b + 4]
        t0 = [math.log(float(r[key])) for r in blk if r["arm"] == "T0"]
        t1 = [math.log(float(r[key])) for r in blk if r["arm"] == "T1"]
        if len(t0) != 2 or len(t1) != 2:
            continue
        out.append(sum(t1) / 2 - sum(t0) / 2)
    return out


def summarise(name, vals, unit="%"):
    if not vals:
        print(f"{name}: no complete blocks")
        return
    n = len(vals)
    m = statistics.fmean(vals)
    if n == 1:
        print(f"{name}: {100*m:+.4f}{unit}  (n=1 block, no interval)")
        return
    sd = statistics.stdev(vals)
    sem = sd / math.sqrt(n)
    t = T975.get(n - 1, 1.96)
    lo, hi = m - t * sem, m + t * sem
    signs = sum(1 for v in vals if v > 0)
    print(f"{name}: {100*m:+.4f}{unit}  CI95 [{100*lo:+.4f}, {100*hi:+.4f}]  "
          f"sd={100*sd:.4f}{unit} n={n} dof={n-1} positive_blocks={signs}/{n}")
    return m, lo, hi


def read_rows(path=None):
    rows = load(path or TSV)
    return [r for r in rows if r["rc"] == "0" and r["decode_s_per_token"] != "nan"]


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


def analyse(rows):
    dec = block_contrasts(rows, "decode_s_per_token")
    pre = block_contrasts(rows, "prefill_s_per_token")
    score = [-0.75 * d - 0.25 * p for d, p in zip(dec, pre)]
    within = {}
    for arm in ("T0", "T1"):
        for key in ("decode_s_per_token", "prefill_s_per_token"):
            v = [float(r[key]) for r in rows if r["arm"] == arm]
            if len(v) > 1:
                within[(arm, key)] = {
                    "mean": statistics.fmean(v),
                    "cv": 100 * statistics.stdev(v) / statistics.fmean(v),
                    "n": len(v),
                }
    return {
        "n_runs": len(rows),
        "n_blocks": len(rows) // 4,
        "failures": len([r for r in rows if r["passed"] != "True"
                         or r["max_abs_diff"] not in ("0", "0.0")]),
        "golden": sorted({r["golden_hash"] for r in rows}),
        "within": within,
        "blocks": {"d_ln_decode": dec, "d_ln_prefill": pre, "d_ln_score": score},
        "d_ln_decode": estimate(dec),
        "d_ln_prefill": estimate(pre),
        "d_ln_score": estimate(score),
    }


def main():
    rows = read_rows()
    print(f"usable runs: {len(rows)}  complete ABBA blocks: {len(rows)//4}")

    bad = [r for r in rows if r["passed"] != "True" or r["max_abs_diff"] not in ("0", "0.0")]
    print(f"correctness failures: {len(bad)}")
    goldens = sorted({r["golden_hash"] for r in rows})
    print(f"distinct golden_hash values: {len(goldens)} -> {goldens}")
    for arm in ("T0", "T1"):
        shas = sorted({r["worker_sha256"][:12] for r in rows if r["arm"] == arm})
        print(f"  {arm} worker sha256 prefixes: {shas}")

    for arm in ("T0", "T1"):
        for key in ("decode_s_per_token", "prefill_s_per_token"):
            v = [float(r[key]) for r in rows if r["arm"] == arm]
            if len(v) > 1:
                cv = statistics.stdev(v) / statistics.fmean(v)
                print(f"  within-arm {arm} {key}: mean={statistics.fmean(v):.9f} "
                      f"cv={100*cv:.4f}% n={len(v)}")

    print("\n-- ABBA block contrasts, T1 minus T0, natural log --")
    dec = block_contrasts(rows, "decode_s_per_token")
    pre = block_contrasts(rows, "prefill_s_per_token")
    summarise("d(ln decode)   ", dec)
    summarise("d(ln prefill)  ", pre)

    score = [-0.75 * d - 0.25 * p for d, p in zip(dec, pre)]
    print("\n-- PRIMARY: d(ln score), T1 minus T0, positive means T1 better --")
    res = summarise("d(ln score)    ", score)

    if res and len(score) > 1:
        m, lo, hi = res
        print("\n-- verdict against the preregistered margins --")
        print(f"  superiority (CI excludes 0 positive): {'YES' if lo > 0 else 'no'}")
        print(f"  inferiority  (CI excludes 0 negative): {'YES' if hi < 0 else 'no'}")
        print(f"  non-inferior at -0.40% of score      : {'YES' if lo > -0.004 else 'no'}")
        print(f"  per-block d(ln score) %: "
              + ", ".join(f"{100*s:+.4f}" for s in score))


if __name__ == "__main__":
    main()
