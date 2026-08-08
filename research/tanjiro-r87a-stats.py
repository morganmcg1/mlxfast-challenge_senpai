#!/usr/bin/env python3
"""Aggregate R87-A campaign logs into per-arm and per-kernel delta tables.

Reads the `pNN-ARM.log` files written by `research/tanjiro-r87a-campaign.sh`,
which each contain one `decode_probe.py --profile` report, and reports:

  * per-arm totals (wall, gpu_busy_sum, gpu_busy_union, gap) with run-level SD;
  * the per-kernel delta table advisor comment 5228464233 makes mandatory,
    covering every kernel above `--min-share` of decode busy time in the
    reference arm, including kernels this diff does not touch;
  * the touched-kernel subtotal next to the end-to-end number, so the
    give-back can be read directly rather than inferred.

Replication is at the run level on purpose: run-to-run drift (thermal, clock,
JIT ordering) is the error term that actually threatens a decode claim, and it
strictly dominates within-run step noise.

  python3 research/tanjiro-r87a-stats.py research/r87a-runs/ladder --ref A0
"""
import argparse
import math
import os
import re
import statistics
import sys

STEP_RE = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms \([\d.]+% of wall\) "
    r"cbs=([\d.]+) dispatches=([\d.]+)"
)
ROW_RE = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s\s(.+)$")
TOTALS = ("wall_us", "busy_sum_us", "busy_union_us", "gap_us", "cbs", "dispatches")


def parse_log(path):
    """Return (totals dict, {kernel: us_per_step}) for one probe log."""
    totals, kernels = {}, {}
    with open(path, errors="replace") as fh:
        for line in fh:
            m = STEP_RE.search(line)
            if m:
                totals = {
                    "wall_us": float(m.group(1)) * 1e3,
                    "busy_sum_us": float(m.group(2)) * 1e3,
                    "busy_union_us": float(m.group(3)) * 1e3,
                    "gap_us": float(m.group(4)) * 1e3,
                    "cbs": float(m.group(5)),
                    "dispatches": float(m.group(6)),
                }
                continue
            m = ROW_RE.match(line.rstrip("\n"))
            if m and not m.group(5).startswith("..."):
                kernels[m.group(5).strip()] = float(m.group(1))
    return totals, kernels


def welch(a, b):
    """(delta, half-width of the 95% interval on b - a), or (delta, nan)."""
    d = statistics.mean(b) - statistics.mean(a)
    if len(a) < 2 or len(b) < 2:
        return d, float("nan")
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    se = math.sqrt(va + vb)
    if se == 0.0:
        return d, 0.0
    df = (va + vb) ** 2 / (
        va**2 / (len(a) - 1) + vb**2 / (len(b) - 1)
    )
    # Two-sided 95% t quantile, adequate for the df range this rig produces.
    t = 1.96 + 2.4 / max(df, 1.0)
    return d, t * se


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--ref", default="A0")
    ap.add_argument("--min-share", type=float, default=1.0,
                    help="report every kernel at or above this %% of reference "
                         "arm busy time (advisor 5228464233 mandates ~1%%)")
    ap.add_argument("--drop-warmup", action="store_true", default=True)
    ap.add_argument("--touched", default="top8keys_r1",
                    help="substring identifying kernels this diff edits")
    args = ap.parse_args()

    runs = []  # (arm, position, totals, kernels)
    for d in args.dirs:
        for name in sorted(os.listdir(d)):
            m = re.fullmatch(r"p(\d+)-([A-Za-z0-9]+)\.log", name)
            if not m:
                continue
            pos, arm = int(m.group(1)), m.group(2)
            if args.drop_warmup and pos == 0:
                continue
            totals, kernels = parse_log(os.path.join(d, name))
            if not totals:
                print(f"WARN: no profile block in {name}", file=sys.stderr)
                continue
            runs.append((arm, pos, totals, kernels))

    if not runs:
        print("no usable runs", file=sys.stderr)
        return 1

    arms = sorted({r[0] for r in runs})
    if args.ref not in arms:
        print(f"reference arm {args.ref} absent; have {arms}", file=sys.stderr)
        return 1

    print(f"runs={len(runs)} arms={arms} ref={args.ref}\n")
    print(f"{'arm':>5} {'n':>2} " + " ".join(f"{k:>14}" for k in TOTALS))
    for arm in arms:
        sel = [r for r in runs if r[0] == arm]
        cells = []
        for k in TOTALS:
            v = [r[2][k] for r in sel]
            sd = statistics.stdev(v) if len(v) > 1 else 0.0
            cells.append(f"{statistics.mean(v):9.1f}±{sd:4.1f}")
        print(f"{arm:>5} {len(sel):>2} " + " ".join(cells))

    ref_runs = [r for r in runs if r[0] == args.ref]
    ref_busy = statistics.mean(r[2]["busy_sum_us"] for r in ref_runs)
    ref_k = {}
    for r in ref_runs:
        for k, v in r[3].items():
            ref_k.setdefault(k, []).append(v)
    reported = sorted(
        (k for k, v in ref_k.items()
         if statistics.mean(v) / ref_busy * 100.0 >= args.min_share),
        key=lambda k: -statistics.mean(ref_k[k]),
    )

    for arm in arms:
        if arm == args.ref:
            continue
        sel = [r for r in runs if r[0] == arm]
        print(f"\n=== {arm} vs {args.ref}  (us/step, 95% CI, + is slower) ===")
        print(f"{'delta':>9} {'ci95':>9} {'ref':>9} {'share':>7}  kernel")
        touched = untouched = 0.0
        for k in reported:
            a = ref_k[k]
            b = [r[3][k] for r in sel if k in r[3]]
            if not b:
                # A renamed variant: fold it into the same family by substring.
                fam = [kk for r in sel for kk in r[3]
                       if _family(kk) == _family(k)]
                b = [r[3][kk] for r in sel for kk in r[3]
                     if _family(kk) == _family(k)]
                if not b:
                    print(f"{'--':>9} {'--':>9} "
                          f"{statistics.mean(a):9.1f} "
                          f"{statistics.mean(a)/ref_busy*100:6.2f}%  {k} "
                          "(absent in arm)")
                    continue
                del fam
            d, ci = welch(a, b)
            if args.touched in k:
                touched += d
            else:
                untouched += d
            flag = "*" if args.touched in k else " "
            print(f"{d:9.2f} {ci:9.2f} {statistics.mean(a):9.1f} "
                  f"{statistics.mean(a)/ref_busy*100:6.2f}% {flag} {k}")
        for key in ("busy_sum_us", "busy_union_us", "wall_us"):
            d, ci = welch([r[2][key] for r in ref_runs],
                          [r[2][key] for r in sel])
            print(f"{d:9.2f} {ci:9.2f} {'':>9} {'':>7}    TOTAL {key}")
        print(f"{touched:9.2f} {'':>9} {'':>9} {'':>7}    subtotal touched "
              f"({args.touched})")
        print(f"{untouched:9.2f} {'':>9} {'':>9} {'':>7}    subtotal untouched "
              "(give-back)")
    return 0


def _family(name: str) -> str:
    """Strip R87-A variant suffixes so an arm's renamed kernel matches stock."""
    return re.sub(r"(_pfin\d+|_b\d+|_e0)+", "", name)


if __name__ == "__main__":
    sys.exit(main())
