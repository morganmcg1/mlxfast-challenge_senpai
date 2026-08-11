#!/usr/bin/env python3
"""Price the MoE re-routing confound from the paired ship/d1 dumps.

Estimator: for each step index i, delta_i = t_ship(i) - t_d1(i)  (positive =
d1 faster).  Label step i divergent if the d1 run's token at i differs from the
ship run's token at i.  Then

    c_hat = median(delta_i | not divergent) - median(delta_i | divergent)

is the extra cost, in us/step, that a divergent step imposes on d1 beyond the
dose's own saving.  If c_hat is ~0 the confound is not there.  If c_hat > 0 the
dose arm's whole-run median saving is depressed by  c_hat * (fraction divergent)
and the corrected saving is  S_obs + c_hat * f.

Pairing by step index is what makes this work: divergent steps are not randomly
located (they depend on the prompt), so an unpaired comparison would confound
"divergent" with "hard token".  The paired difference removes any per-step effect
that is common to both arms.
"""
import argparse
import glob
import os
import statistics
import sys


def read_floats(p):
    with open(p) as fh:
        return [float(x) for x in fh if x.strip()]


def read_ints(p):
    with open(p) as fh:
        return [int(x) for x in fh if x.strip()]


def med(v):
    return statistics.median(v) if v else float("nan")


def boot_ci(a, b, n=20000, seed=118):
    """Percentile CI for median(a) - median(b) by independent resampling."""
    import random
    r = random.Random(seed)
    if not a or not b:
        return (float("nan"), float("nan"))
    out = []
    la, lb = len(a), len(b)
    for _ in range(n):
        sa = med([a[r.randrange(la)] for _ in range(la)])
        sb = med([b[r.randrange(lb)] for _ in range(lb)])
        out.append(sa - sb)
    out.sort()
    return (out[int(0.025 * n)], out[int(0.975 * n)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--boot", type=int, default=20000)
    args = ap.parse_args()

    ships = sorted(glob.glob(os.path.join(args.dir, "*_ship.steps")))
    doses = sorted(glob.glob(os.path.join(args.dir, "*_d1.steps")))
    if not ships or not doses:
        print(f"need *_ship.steps and *_d1.steps in {args.dir}")
        return 1

    # Pair run 1 with run 4 and run 2 with run 3 (the palindrome), i.e. pair the
    # ship and d1 runs that are equidistant from the session midpoint.
    pairs = list(zip(ships, doses[::-1])) if len(ships) == len(doses) else \
        [(ships[0], doses[0])]

    all_div, all_non = [], []
    print(f"{'ship run':>28} {'d1 run':>26} {'steps':>6} {'div':>5} "
          f"{'med|non us':>11} {'med|div us':>11} {'c_hat us':>9}")
    for sp, dp in pairs:
        ts, td = read_floats(sp), read_floats(dp)
        tok_s = read_ints(sp.replace(".steps", ".tokens"))
        tok_d = read_ints(dp.replace(".steps", ".tokens"))
        n = min(len(ts), len(td), len(tok_s), len(tok_d))
        div, non = [], []
        for i in range(args.warmup, n):
            d = (ts[i] - td[i]) * 1000.0          # ms -> us, positive = d1 faster
            (div if tok_s[i] != tok_d[i] else non).append(d)
        all_div += div
        all_non += non
        c = med(non) - med(div)
        print(f"{os.path.basename(sp):>28} {os.path.basename(dp):>26} "
              f"{n - args.warmup:>6} {len(div):>5} {med(non):>11.2f} "
              f"{med(div):>11.2f} {c:>9.2f}")

    f = len(all_div) / max(1, len(all_div) + len(all_non))
    c = med(all_non) - med(all_div)
    lo, hi = boot_ci(all_non, all_div, n=args.boot)
    print(f"\npooled: {len(all_non)} non-divergent, {len(all_div)} divergent "
          f"(f = {f:.3f})")
    print(f"c_hat = median(delta|non) - median(delta|div) = {c:+.2f} us/step, "
          f"95 % CI [{lo:+.2f}, {hi:+.2f}]")
    if lo <= 0.0 <= hi:
        print("=> interval contains zero: no measurable re-routing cost. "
              "The dose arm's saving is not depressed by the confound.")
    else:
        print(f"=> re-routing costs {c:+.2f} us on a divergent step. "
              f"d1's whole-run saving is depressed by c*f = {c * f:+.2f} us/step; "
              f"add that back before comparing to the bar.")
    print(f"\n(worst-case correction to add to d1's saving: "
          f"{max(0.0, hi) * f:+.2f} us/step at the 95 % upper end of c)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
