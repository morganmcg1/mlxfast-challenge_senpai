#!/usr/bin/env python3
"""Divergence-free subset estimate of the d1 saving.

`divergence-cost.py` prices what a divergent step costs.  This script answers the
more direct question: *restricted to the steps where the two arms emit the same
token*, how much faster is d1?  On those steps the two runs did identical work
modulo the dose, so the MoE re-routing confound cannot be operating at all.

Estimator: pooled median over non-divergent steps of

    delta_i = t_ship(i) - t_d1(i)     (us, positive = d1 faster)

CI: moving-block bootstrap with block length L over the per-pair step series, so
that serial correlation between neighbouring steps is not thrown away (the i.i.d.
step bootstrap in divergence-cost.py is anti-conservative for exactly that
reason -- see RESULT.md methods caveats, audit finding 8).
"""
import argparse
import glob
import json
import os
import random
import statistics


def read_floats(p):
    with open(p) as fh:
        return [float(x) for x in fh if x.strip()]


def read_ints(p):
    with open(p) as fh:
        return [int(x) for x in fh if x.strip()]


def mbb_sample(series, rng, L):
    """One moving-block-bootstrap resample of a list of per-pair series."""
    out = []
    for s in series:
        n = len(s)
        if n == 0:
            continue
        k = 0
        while k < n:
            j = rng.randrange(max(1, n - L + 1))
            out.extend(s[j:j + L])
            k += L
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--boot", type=int, default=20000)
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1118)
    ap.add_argument("--json", default=None,
                    help="also write the two intervals here, so that the W&B "
                         "run and this log cannot disagree")
    args = ap.parse_args()

    ships = sorted(glob.glob(os.path.join(args.dir, "*_ship.steps")))
    doses = sorted(glob.glob(os.path.join(args.dir, "*_d1.steps")))
    pairs = list(zip(ships, doses[::-1])) if len(ships) == len(doses) else \
        [(ships[0], doses[0])]

    per_pair_non, per_pair_all = [], []
    print(f"{'ship run':>28} {'d1 run':>26} {'steps':>6} {'same-tok':>9} "
          f"{'med|same us':>12} {'med|all us':>11}")
    for sp, dp in pairs:
        ts, td = read_floats(sp), read_floats(dp)
        tok_s = read_ints(sp.replace(".steps", ".tokens"))
        tok_d = read_ints(dp.replace(".steps", ".tokens"))
        n = min(len(ts), len(td), len(tok_s), len(tok_d))
        non, alls = [], []
        for i in range(args.warmup, n):
            d = (ts[i] - td[i]) * 1000.0
            alls.append(d)
            if tok_s[i] == tok_d[i]:
                non.append(d)
        per_pair_non.append(non)
        per_pair_all.append(alls)
        print(f"{os.path.basename(sp):>28} {os.path.basename(dp):>26} "
              f"{n - args.warmup:>6} {len(non):>9} "
              f"{statistics.median(non) if non else float('nan'):>12.2f} "
              f"{statistics.median(alls):>11.2f}")

    flat_non = [x for s in per_pair_non for x in s]
    flat_all = [x for s in per_pair_all for x in s]
    rng = random.Random(args.seed)

    def ci(series, point):
        out = []
        for _ in range(args.boot):
            s = mbb_sample(series, rng, args.block)
            if s:
                out.append(statistics.median(s))
        out.sort()
        n = len(out)
        return out[int(0.025 * n)], out[int(0.975 * n)]

    p_non = statistics.median(flat_non)
    p_all = statistics.median(flat_all)
    lo_n, hi_n = ci(per_pair_non, p_non)
    lo_a, hi_a = ci(per_pair_all, p_all)
    print(f"\npooled non-divergent (same-token) steps: n = {len(flat_non)}")
    print(f"  median saving = {p_non:+.2f} us/step, "
          f"95 % moving-block CI [{lo_n:+.2f}, {hi_n:+.2f}] (L = {args.block})")
    print(f"pooled all steps:                        n = {len(flat_all)}")
    print(f"  median saving = {p_all:+.2f} us/step, "
          f"95 % moving-block CI [{lo_a:+.2f}, {hi_a:+.2f}] (L = {args.block})")
    print("\nThe same-token subset is confound-free by construction: on those "
          "steps both arms emitted the same token, so no re-routing difference "
          "can be carrying the saving.")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({
                "dir": args.dir, "block": args.block, "boot": args.boot,
                "seed": args.seed, "warmup": args.warmup,
                "same_token": {"n": len(flat_non), "median_us": p_non,
                               "ci_lo_us": lo_n, "ci_hi_us": hi_n},
                "all_steps": {"n": len(flat_all), "median_us": p_all,
                              "ci_lo_us": lo_a, "ci_hi_us": hi_a},
            }, fh, indent=1, sort_keys=True)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
