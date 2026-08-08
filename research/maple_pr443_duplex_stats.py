#!/usr/bin/env python3
"""Research-only (PR #443): counterbalanced duplex analysis of SPLIT=1 profiles.

PR #301 (standing rule 36) showed that a plain per-arm mean over ABBA slots can
flip the sign of a sub-1% per-call effect: the *invariant* routed twin moved
-1.16% between slot kinds, i.e. the nuisance is a multiplicative, kernel-specific
clock/thermal factor, not an additive offset. This analyser therefore

  1. works in logs, where that nuisance is additive;
  2. forms the within-run control ratio  M_r = log(T_K,r) - log(T_C,r)  against
     an invariant twin kernel C, which cancels the per-run factor exactly;
  3. contrasts arms inside adjacent counterbalanced duplexes ([AB][BA][AB]...),
     so a monotone slot trend cancels in expectation and only a second-order
     slot x phase interaction survives;
  4. treats the *run* as the unit of analysis - within-run call SE is an order
     of magnitude below between-run sigma, so pooling calls would understate
     the interval by construction.

Reported alongside: the unadjusted (control-free) duplex contrast as a
sensitivity check, and the same contrast on the control kernel alone as a
validity gate (it must not move).

  python3 research/maple_pr443_duplex_stats.py --steps 33 \\
      --arms off halved /tmp/maple-pr443-abba/*.err
"""
import argparse
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_probe import parse_gpuprof_line  # noqa: E402

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_]+)\.err$")
KERNEL = "shared_nvfp4_swiglu_qmv_rows1"
CONTROL = "routed_nvfp4_swiglu_qmv_packed_top8keys"
# Decode score sensitivity on this host: 1 us/step of decode time.
PCT_PER_US_STEP = 0.015280

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
       26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t95(df):
    return T95[min(30, max(1, int(df)))]


def trimmed_mean(values, frac=0.10):
    ordered = sorted(values)
    cut = int(len(ordered) * frac)
    core = ordered[cut:len(ordered) - cut] if cut else ordered
    return statistics.mean(core)


def spans(path, kernel):
    out = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF ") or kernel not in line:
                continue
            rec = parse_gpuprof_line(line)
            if rec is not None:
                out.append((rec[1] - rec[0]) * 1e6)
    return out


def steady(values, per_step, steps, drop):
    """Last `per_step * (steps - drop)` calls: seed forward plus `drop` steps."""
    want = per_step * (steps - drop)
    if len(values) < want:
        raise SystemExit(f"{len(values)} calls, need {want}")
    return values[-want:]


def contrast(pairs, label, unit=""):
    """Mean +/- 95% CI of within-duplex differences (second minus first arm)."""
    n = len(pairs)
    mean = statistics.mean(pairs)
    if n < 2:
        return mean, float("nan")
    hw = t95(n - 1) * statistics.stdev(pairs) / math.sqrt(n)
    print(f"  {label:<34} {mean:+.5f} [{mean - hw:+.5f}, {mean + hw:+.5f}]"
          f" {unit} (n={n}, df={n - 1})")
    return mean, hw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--kernel", default=KERNEL)
    ap.add_argument("--control", default=CONTROL)
    ap.add_argument("--per-step", type=int, default=39)
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--drop-steps", type=int, default=2)
    ap.add_argument("--arms", nargs=2, default=["off", "halved"],
                    help="baseline arm then candidate arm")
    args = ap.parse_args()
    base_arm, cand_arm = args.arms

    runs = []
    for path in args.paths:
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            raise SystemExit(f"cannot parse slot from {path}")
        slot, _rep, arm = int(m.group(1)), int(m.group(2)), m.group(3)
        k_all, c_all = spans(path, args.kernel), spans(path, args.control)
        k = steady(k_all, args.per_step, args.steps, args.drop_steps)
        c = steady(c_all, args.per_step, args.steps, args.drop_steps)
        runs.append(dict(slot=slot, arm=arm, path=os.path.basename(path),
                         set=os.path.basename(os.path.dirname(path)),
                         n_k=len(k_all), n_c=len(c_all),
                         tk=trimmed_mean(k), tc=trimmed_mean(c)))
    runs.sort(key=lambda r: (r["set"], r["slot"]))

    print(f"{'run':>22} {'arm':>8} {'nK':>6} {'nC':>6} {'K us':>8} "
          f"{'C us':>8} {'M=logK-logC':>12}")
    for r in runs:
        r["M"] = math.log(r["tk"]) - math.log(r["tc"])
        print(f"{r['path']:>22} {r['arm']:>8} {r['n_k']:6d} {r['n_c']:6d} "
              f"{r['tk']:8.3f} {r['tc']:8.3f} {r['M']:12.5f}")

    print("\nG2 dispatch parity (per-arm dispatch counts must be equal)")
    ok_parity = True
    for arm in (base_arm, cand_arm):
        nk = {r["n_k"] for r in runs if r["arm"] == arm}
        nc = {r["n_c"] for r in runs if r["arm"] == arm}
        print(f"  {arm:>8} K={sorted(nk)} C={sorted(nc)}")
        ok_parity &= len(nk) == 1 and len(nc) == 1
    all_k = {r["n_k"] for r in runs}
    all_c = {r["n_c"] for r in runs}
    ok_parity &= len(all_k) == 1 and len(all_c) == 1
    print(f"  parity: {'PASS' if ok_parity else 'FAIL'}"
          f" (K={sorted(all_k)}, C={sorted(all_c)})")

    duplexes = []
    for i in range(0, len(runs) - 1, 2):
        a, b = runs[i], runs[i + 1]
        if {a["arm"], b["arm"]} != {base_arm, cand_arm}:
            raise SystemExit(f"slots {a['slot']},{b['slot']} are not a duplex")
        sign = 1.0 if b["arm"] == cand_arm else -1.0
        duplexes.append(dict(
            slots=(a["slot"], b["slot"]),
            order=f"{a['arm']}->{b['arm']}",
            d_ratio=sign * (b["M"] - a["M"]),
            d_raw=sign * (math.log(b["tk"]) - math.log(a["tk"])),
            d_ctrl=sign * (math.log(b["tc"]) - math.log(a["tc"]))))

    print(f"\nduplex contrasts (candidate {cand_arm} minus baseline {base_arm},"
          " log scale, negative = candidate faster)")
    print(f"{'slots':>10} {'order':>16} {'ratio':>10} {'raw K':>10} {'ctrl':>10}")
    for d in duplexes:
        print(f"{str(d['slots']):>10} {d['order']:>16} {d['d_ratio']:+10.5f} "
              f"{d['d_raw']:+10.5f} {d['d_ctrl']:+10.5f}")

    base_us = statistics.mean([r["tk"] for r in runs if r["arm"] == base_arm])
    print(f"\nestimators (baseline {base_arm} K = {base_us:.3f} us/call)")
    delta, hw = contrast([d["d_ratio"] for d in duplexes], "ratio-adjusted (primary)")
    raw, raw_hw = contrast([d["d_raw"] for d in duplexes], "unadjusted K (sensitivity)")
    ctrl, ctrl_hw = contrast([d["d_ctrl"] for d in duplexes], "control C only (G3 gate)")

    def to_us(x):
        return base_us * math.expm1(x)

    lo, hi = to_us(delta - hw), to_us(delta + hw)
    point = to_us(delta)
    print(f"\nprimary effect: {point:+.3f} us/call [{lo:+.3f}, {hi:+.3f}]"
          f"  ({100 * math.expm1(delta):+.2f}%)")
    print(f"  per decode step (x{args.per_step}): {point * args.per_step:+.1f} us"
          f" [{lo * args.per_step:+.1f}, {hi * args.per_step:+.1f}]")
    print(f"  score:                {point * args.per_step * PCT_PER_US_STEP:+.4f}%"
          f" [{lo * args.per_step * PCT_PER_US_STEP:+.4f},"
          f" {hi * args.per_step * PCT_PER_US_STEP:+.4f}]")
    print(f"  sensitivity (unadjusted): {to_us(raw):+.3f} us/call"
          f" [{to_us(raw - raw_hw):+.3f}, {to_us(raw + raw_hw):+.3f}]")

    print("\npre-registered gates")
    half = (hi - lo) / 2
    g3 = abs(ctrl) <= 0.005 and (ctrl - ctrl_hw) <= 0 <= (ctrl + ctrl_hw)
    g4 = half <= 0.12
    print(f"  G2 dispatch parity      : {'PASS' if ok_parity else 'FAIL'}")
    print(f"  G3 control invariance   : {'PASS' if g3 else 'FAIL'}"
          f" (|{100 * math.expm1(ctrl):+.2f}%| <= 0.50%, CI covers 0)")
    print(f"  G4 precision (hw<=0.12) : {'PASS' if g4 else 'FAIL'}"
          f" (half-width {half:.3f} us/call)")
    if hi <= -0.20:
        verdict = "(i) real speedup" + ("" if -0.55 <= point <= -0.23
                                        else " -- outside the bandwidth band")
    elif lo >= -0.10:
        verdict = "(iii) no useful gain" + (" (harmful)" if lo > 0.05 else "")
    elif not g4:
        verdict = "(ii) underpowered: extend to 12 duplexes"
    else:
        verdict = "(ii) inconclusive"
    print(f"\nverdict: {verdict}   (MDE = CI half-width = {half:.3f} us/call)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
