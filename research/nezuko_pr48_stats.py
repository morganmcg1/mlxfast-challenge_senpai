#!/usr/bin/env python3
"""Research-only analysis for the six-arm PR #48 fusion deconfound ABBA sweep.

  python3 research/nezuko_pr48_stats.py /tmp/nez298/abba [--warmup 8]

Reads the `bNN_sMM_ARM.steps` files written by `research/nezuko_pr48_abba.sh`
(one per-step decode latency in ms per line), drops the leading warm-up steps,
and reports every deconfounding contrast two ways:

  * block-paired: each arm appears twice per palindromic block, so the block
    mean already cancels monotone drift; the across-block spread gives an
    assumption-light CI with df = blocks - 1.
  * two-way fixed effects: run mean ~ block + arm, residual df = n - B - 5.
    Much tighter, valid when run-to-run noise is exchangeable within a block.
"""
import argparse
import math
import os
import re
import statistics
import sys

ARMS = ["0", "RV", "V", "G", "R", "N"]
ARM_DESC = {
    "0": "sg2  nf0   stock geometry, no fold",
    "RV": "sg2  nf3   stock geometry, redundant reduction (rmsnorm still dispatched)",
    "V": "sg2  nf1   stock geometry, fold replaces the rmsnorm dispatch",
    "G": "sg16 nf0   fused geometry, no fold",
    "R": "sg16 nf3   fused geometry, redundant reduction",
    "N": "sg16 nf1   fused geometry, fold replaces the rmsnorm dispatch (== PR #48)",
}
CONTRASTS = [
    ("G-0", "G", "0", "geometry cost alone (16 simdgroups, no fold)"),
    ("R-G", "R", "G", "redundant reduction cost at fused geometry (640 TGs)"),
    ("RV-0", "RV", "0", "redundant reduction cost at stock geometry (5120 TGs)"),
    ("V-RV", "V", "RV", "dispatch/barrier refund with ZERO geometry change"),
    ("N-R", "N", "R", "dispatch/barrier refund at fused geometry (assignment falsifier)"),
    ("N-G", "N", "G", "net fold effect holding geometry fixed at 16 simdgroups"),
    ("V-0", "V", "0", "net fold effect holding geometry fixed at stock"),
    ("N-0", "N", "0", "PR #48 mode 1 reproduced (geometry + fold confounded)"),
]

# two-sided 95% Student-t quantiles
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086,
        25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t95(df: int) -> float:
    if df < 1:
        return float("nan")
    keys = sorted(_T95)
    for k in keys:
        if df <= k:
            return _T95[k]
    return 1.960


def trimmed_mean(vals, frac):
    """Upper-trimmed mean. Host interference only ever inflates a step, so
    trimming one-sided keeps far more signal than a symmetric trim."""
    if frac <= 0:
        return statistics.mean(vals)
    k = int(len(vals) * frac)
    return statistics.mean(sorted(vals)[:len(vals) - k]) if k else statistics.mean(vals)


def load(outdir: str, warmup: int, trim: float):
    """-> ordered list of (idx, block, arm, estimate_us, sd_us, n, raw_mean_us)."""
    runs = []
    pat = re.compile(r"^b(\d+)_s(\d+)_(0|RV|V|G|R|N)\.steps$")
    for name in sorted(os.listdir(outdir)):
        m = pat.match(name)
        if not m:
            continue
        blk, idx, arm = int(m.group(1)), int(m.group(2)), m.group(3)
        with open(os.path.join(outdir, name)) as fh:
            vals = [float(x) * 1e3 for x in fh if x.strip()]  # ms -> us
        vals = vals[warmup:]
        if len(vals) < 32:
            print(f"  skip {name}: only {len(vals)} usable steps", file=sys.stderr)
            continue
        runs.append((idx, blk, arm, trimmed_mean(vals, trim), statistics.pstdev(vals),
                     len(vals), statistics.mean(vals)))
    runs.sort()
    return runs


def interference_report(runs):
    """Flag runs whose within-run sd is far above the cohort median. A quiet run
    on this host sits near 40 us; a run with a scheduler or thermal event shows
    hundreds. Such a run biases whichever arm it landed on."""
    sds = sorted(r[4] for r in runs)
    med = statistics.median(sds)
    bad = [r for r in runs if r[4] > 4 * med]
    print(f"\nwithin-run sd: median {med:8.1f} us   max {sds[-1]:8.1f} us")
    if not bad:
        print("  no run exceeds 4x the median within-run sd")
        return
    print(f"  {len(bad)} run(s) above 4x median -> host interference, "
          f"not an arm effect:")
    for idx, blk, arm, est, sd, n, raw in bad:
        print(f"    b{blk:02d}_s{idx:02d}_{arm:<2s}  sd={sd:8.1f}  "
              f"mean={raw:8.1f}  trimmed={est:8.1f}  (trim moves it "
              f"{est - raw:+.1f} us)")


def block_paired(runs, blocks):
    per = {}
    for _, blk, arm, mean, _, _, _ in runs:
        per.setdefault((blk, arm), []).append(mean)
    out = {}
    for name, a, b, _ in CONTRASTS:
        deltas = []
        for blk in blocks:
            xa, xb = per.get((blk, a)), per.get((blk, b))
            if xa and xb:
                deltas.append(statistics.mean(xa) - statistics.mean(xb))
        out[name] = deltas
    return per, out


def ols(runs, blocks):
    """run_mean ~ intercept + block dummies + arm dummies (arm '0' as reference)."""
    arms = [a for a in ARMS if a != "0"]
    cols = ["1"] + [f"blk{b}" for b in blocks[1:]] + [f"arm{a}" for a in arms]
    X, y = [], []
    for _, blk, arm, mean, _, _, _ in runs:
        row = [1.0]
        row += [1.0 if blk == b else 0.0 for b in blocks[1:]]
        row += [1.0 if arm == a else 0.0 for a in arms]
        X.append(row)
        y.append(mean)
    p, n = len(cols), len(X)
    xtx = [[sum(X[i][r] * X[i][c] for i in range(n)) for c in range(p)] for r in range(p)]
    xty = [sum(X[i][r] * y[i] for i in range(n)) for r in range(p)]
    aug = [xtx[r][:] + [1.0 if c == r else 0.0 for c in range(p)] + [xty[r]]
           for r in range(p)]
    for c in range(p):  # Gauss-Jordan with partial pivoting
        piv = max(range(c, p), key=lambda r: abs(aug[r][c]))
        aug[c], aug[piv] = aug[piv], aug[c]
        d = aug[c][c]
        if abs(d) < 1e-12:
            raise ValueError("design is rank deficient; every arm needs runs in "
                             "at least two blocks")
        aug[c] = [v / d for v in aug[c]]
        for r in range(p):
            if r != c and aug[r][c]:
                f = aug[r][c]
                aug[r] = [v - f * w for v, w in zip(aug[r], aug[c])]
    inv = [row[p:2 * p] for row in aug]
    beta = [row[2 * p] for row in aug]
    resid = [y[i] - sum(X[i][k] * beta[k] for k in range(p)) for i in range(n)]
    df = n - p
    s2 = sum(r * r for r in resid) / df
    idx = {c: k for k, c in enumerate(cols)}

    def effect(arm):
        return 0.0 if arm == "0" else beta[idx[f"arm{arm}"]]

    def se_diff(a, b):
        v = 0.0
        ia = idx.get(f"arm{a}")
        ib = idx.get(f"arm{b}")
        for k1, s1 in ((ia, 1.0), (ib, -1.0)):
            for k2, s2_ in ((ia, 1.0), (ib, -1.0)):
                if k1 is not None and k2 is not None:
                    v += s1 * s2_ * inv[k1][k2]
        return math.sqrt(max(v, 0.0) * s2), df

    return effect, se_diff, df, math.sqrt(s2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--trim", type=float, default=0.0,
                    help="upper-trim fraction for the per-run estimator "
                         "(0.05 discards the slowest 5%% of steps)")
    args = ap.parse_args()

    runs = load(args.outdir, args.warmup, args.trim)
    runs = [r for r in runs if r[1] > 0]  # block 0 is the discarded primer
    if not runs:
        print("no usable runs", file=sys.stderr)
        return 1
    blocks = sorted({r[1] for r in runs})
    est = "mean" if args.trim <= 0 else f"upper-{args.trim:.0%}-trimmed mean"
    print(f"{len(runs)} runs over blocks {blocks}, warmup={args.warmup} steps dropped, "
          f"{runs[0][5]} steps/run kept, per-run estimator = {est}\n")
    interference_report(runs)
    print()

    print("arm    n  mean_us   sd_of_run_means  within_run_sd   description")
    per_arm = {}
    for arm in ARMS:
        ms = [r[3] for r in runs if r[2] == arm]
        ws = [r[4] for r in runs if r[2] == arm]
        if not ms:
            continue
        per_arm[arm] = ms
        sd = statistics.stdev(ms) if len(ms) > 1 else float("nan")
        print(f"{arm:<4} {len(ms):>3} {statistics.mean(ms):9.1f} {sd:14.1f} "
              f"{statistics.mean(ws):14.1f}   {ARM_DESC[arm]}")

    per, deltas = block_paired(runs, blocks)
    print("\nper-block arm means (us/step)")
    print("block " + "".join(f"{a:>10}" for a in ARMS))
    for blk in blocks:
        row = "".join(f"{statistics.mean(per[(blk, a)]):10.1f}"
                      if (blk, a) in per else f"{'-':>10}" for a in ARMS)
        print(f"{blk:>5} {row}")

    try:
        effect, se_diff, odf, rsd = ols(runs, blocks)
        print(f"\ntwo-way fixed effects: residual sd {rsd:.1f} us over {odf} df")
    except ValueError as exc:
        print(f"\ntwo-way fixed effects skipped: {exc}")
        effect = se_diff = odf = None

    print("\ncontrast      block-paired (us/step)              fixed-effects (us/step)")
    print(f"{'':<12} {'mean':>8} {'sd':>7} {'t':>6} {'95% CI':>18}    "
          f"{'mean':>8} {'se':>6} {'t':>6} {'95% CI':>18}   meaning")
    for name, a, b, desc in CONTRASTS:
        d = deltas.get(name, [])
        if len(d) >= 2:
            m = statistics.mean(d)
            sd = statistics.stdev(d)
            se = sd / math.sqrt(len(d))
            t = m / se if se else float("inf")
            df = len(d) - 1
            h = t95(df) * se
            bp = f"{m:8.1f} {sd:7.1f} {t:6.2f}  [{m - h:7.1f},{m + h:7.1f}]"
        else:
            bp = f"{'':<8} {'':<7} {'':<6} {'':<18}"
        if effect is None:
            print(f"{name:<12} {bp}    {desc}")
            continue
        om = effect(a) - effect(b)
        ose, _ = se_diff(a, b)
        ot = om / ose if ose else float("inf")
        oh = t95(odf) * ose
        print(f"{name:<12} {bp}    {om:8.1f} {ose:6.1f} {ot:6.2f} "
              f" [{om - oh:7.1f},{om + oh:7.1f}]   {desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
