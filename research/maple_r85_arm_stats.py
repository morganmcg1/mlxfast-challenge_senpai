#!/usr/bin/env python3
"""Research-only (PR #457): generalized adjacent-duplex per-label statistics.

`maple_pr443_step_decomposition.py` answers one question for one two-arm ABBA
set: it hard-codes the pairing phase (slots 1-2, 3-4, ...) and refuses any run
sequence whose fixed pairs are not exactly {base, cand}. That is the right
guard for a two-arm set and the wrong tool for two jobs this arm needs:

  * a **noise floor**. An ABBA order like `off halved halved off` also contains
    same-arm adjacent pairs at the *other* pairing phase (slots 2-3, 4-5, ...).
    Those are null duplexes: identical binary, identical arm, same session,
    same adjacency structure as a real duplex. Running the real estimator on
    them measures what it reports when the true effect is zero. This costs no
    GPU time -- the runs already exist.
  * a **multi-arm** set. A placement dose-response needs >=3 arms in one
    session, so the pairing phase alone no longer identifies the contrast.

So: select duplexes by matching arms at either pairing phase, allow the two
arm names to be equal, and report the absolute contrast next to the
ratio-adjusted one. The second point matters here. Ratio adjustment divides by
a control kernel assumed unaffected by the flag; the whole hypothesis under
test is that a flag perturbs kernels it does not touch, which would make the
control an invalid denominator. For a placement arm the absolute total is the
primary estimator and the ratio-adjusted one a diagnostic.

  # noise floor from the existing PR #443 runs (no GPU time)
  python3 research/maple_r85_arm_stats.py --steps 33 --arms off off \\
      --offset 1 /tmp/maple-pr443-abba/[0-9]*.err

  # PR #443's published contrast, reproduced
  python3 research/maple_r85_arm_stats.py --steps 33 --arms off halved \\
      --offset 0 /tmp/maple-pr443-abba/[0-9]*.err
"""
import argparse
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maple_pr443_duplex_stats import CONTROL, PCT_PER_US_STEP, t95  # noqa: E402
from maple_pr443_step_decomposition import label_totals  # noqa: E402

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_0-9]+)\.err$")

# Six kernels PR #443 never touched that nonetheless moved in its ON arm.
GIVEBACK_KERNELS = (
    "routed_shared_nvfp4_down_residual",
    "sliding_fused_attn_ring",
    "full_fused_attn_grow",
    "gate_sp_h48",
    "oproj_act_h64",
    "dense_down_residual",
)


def load_runs(paths, cbs_per_step, steady_steps, strip_infix=()):
    runs = []
    for path in paths:
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            raise SystemExit(f"cannot parse slot from {path}")
        totals, busy = label_totals(path, cbs_per_step, steady_steps)
        # Rule 33 forces an arm-specific kernel name, which then reads as two
        # different labels. Folding the suffix back lets the kernel under test
        # appear in the contrast instead of being dropped as arm-specific.
        for infix in strip_infix:
            folded = {}
            for key, val in totals.items():
                fkey = key.replace(infix, "_")
                folded[fkey] = folded.get(fkey, 0.0) + val
            totals = folded
        runs.append(dict(slot=int(m.group(1)), rep=int(m.group(2)),
                         arm=m.group(3), path=os.path.basename(path),
                         set=os.path.basename(os.path.dirname(path)),
                         totals=totals, busy=busy))
    runs.sort(key=lambda r: (r["set"], r["slot"]))
    return runs


def select_duplexes(runs, base_arm, cand_arm, offset):
    """Adjacent (i, i+1) pairs within one set at the requested pairing phase.

    Returns [(i, sign)]. `sign` is +1 when slot i+1 holds the candidate, so a
    negative contrast always means "candidate faster". Same-arm (null) pairs
    have no candidate, so their sign alternates: that reproduces the sign
    counterbalancing of a real ABBA set, leaving the null point estimate
    unbiased by within-pair drift instead of measuring drift itself.
    """
    out = []
    null = base_arm == cand_arm
    for i in range(offset, len(runs) - 1, 2):
        a, b = runs[i], runs[i + 1]
        if a["set"] != b["set"]:
            continue
        if null:
            if a["arm"] != base_arm or b["arm"] != base_arm:
                continue
            out.append((i, 1.0 if len(out) % 2 == 0 else -1.0))
        else:
            if {a["arm"], b["arm"]} != {base_arm, cand_arm}:
                continue
            out.append((i, 1.0 if b["arm"] == cand_arm else -1.0))
    return out


def contrast(runs, duplexes, getter):
    return [sign * (math.log(getter(runs[i + 1])) - math.log(getter(runs[i])))
            for i, sign in duplexes]


def ci(values):
    n = len(values)
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else float("nan")
    hw = t95(n - 1) * sd / math.sqrt(n) if n > 1 else float("nan")
    return mean, hw, sd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--cbs-per-step", type=int, default=406)
    ap.add_argument("--control", default=CONTROL)
    ap.add_argument("--arms", nargs=2, required=True,
                    help="base cand; equal names select null duplexes")
    ap.add_argument("--offset", type=int, default=0, choices=(0, 1),
                    help="adjacent-pair phase: 0 pairs slots 1-2, 1 pairs 2-3")
    ap.add_argument("--min-us-step", type=float, default=5.0)
    ap.add_argument("--only-giveback", action="store_true",
                    help="restrict the table to the six PR #443 give-back kernels")
    ap.add_argument("--scale-to-n", type=int, default=0,
                    help="also report the CI half-width this SD implies at n duplexes")
    ap.add_argument("--strip-infix", nargs="*", default=["_hs_", "_ps_"],
                    help="arm-specific kernel-name infixes to fold back to _")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    base_arm, cand_arm = args.arms
    steady_steps = args.steps - 1

    runs = load_runs(args.paths, args.cbs_per_step, steady_steps,
                     strip_infix=tuple(args.strip_infix))
    duplexes = select_duplexes(runs, base_arm, cand_arm, args.offset)
    if len(duplexes) < 2:
        raise SystemExit(
            f"only {len(duplexes)} duplex(es) for {base_arm}/{cand_arm} at "
            f"offset {args.offset}; nothing to estimate")

    control = None
    for key in runs[0]["totals"]:
        if args.control in key:
            control = key
            break
    if control is None:
        raise SystemExit(f"control {args.control} not found")

    kind = "NULL" if base_arm == cand_arm else "CONTRAST"
    print(f"{kind}: {cand_arm} minus {base_arm}   offset={args.offset}   "
          f"n_duplex={len(duplexes)}")
    print(f"window: last {args.cbs_per_step * steady_steps} command buffers "
          f"= {args.cbs_per_step}/step x {steady_steps} steady steps")
    for i, sign in duplexes:
        print(f"  duplex {runs[i]['set']} slots {runs[i]['slot']:>2}"
              f"({runs[i]['arm']}) -> {runs[i+1]['slot']:>2}"
              f"({runs[i+1]['arm']})  sign {sign:+.0f}")

    labels = sorted(set().union(*[set(r["totals"]) for r in runs]),
                    key=lambda k: -runs[0]["totals"].get(k, 0.0))
    base_slots = [i if runs[i]["arm"] == base_arm else i + 1
                  for i, _ in duplexes]

    rows = []
    for key in labels:
        if any(key not in r["totals"] for r in runs):
            continue
        base_us = statistics.mean(
            [runs[j]["totals"][key] / steady_steps for j in base_slots])
        keep = (any(k in key for k in GIVEBACK_KERNELS)
                if args.only_giveback
                else base_us >= args.min_us_step or args.control in key)
        if not keep:
            continue
        adj = contrast(runs, duplexes,
                       lambda r, k=key: r["totals"][k] / r["totals"][control])
        raw = contrast(runs, duplexes, lambda r, k=key: r["totals"][k])
        rows.append((key, base_us, ci(adj), ci(raw)))

    hdr = (f"\n{'us/step':>9} {'adj d':>8} {'adj CI':>16} {'abs d':>8} "
           f"{'abs CI':>16} {'absSD':>7} {'sig':>4}  kernel")
    print(hdr)
    tot = {"adj": [0.0, 0.0, 0.0], "raw": [0.0, 0.0, 0.0]}
    for key, base_us, (am, ah, asd), (rm, rh, rsd) in rows:
        d_adj = base_us * math.expm1(am)
        lo_adj = base_us * math.expm1(am - ah)
        hi_adj = base_us * math.expm1(am + ah)
        d_raw = base_us * math.expm1(rm)
        lo_raw = base_us * math.expm1(rm - rh)
        hi_raw = base_us * math.expm1(rm + rh)
        sig = "***" if (rm - rh) * (rm + rh) > 0 else ""
        print(f"{base_us:9.1f} {d_adj:+8.2f} [{lo_adj:+7.2f},{hi_adj:+7.2f}] "
              f"{d_raw:+8.2f} [{lo_raw:+7.2f},{hi_raw:+7.2f}] "
              f"{base_us*rsd:7.2f} {sig:>4}  {key}")
        for name, (d, lo, hi) in (("adj", (d_adj, lo_adj, hi_adj)),
                                  ("raw", (d_raw, lo_raw, hi_raw))):
            tot[name][0] += d
            tot[name][1] += lo
            tot[name][2] += hi

    base_busy = statistics.mean([runs[j]["busy"] / steady_steps
                                 for j in base_slots])
    covered = sum(r[1] for r in rows)
    print(f"\nlabels shown cover {covered:.0f} of {base_busy:.0f} us/step "
          f"({100*covered/base_busy:.1f}%)")
    print(f"sum of shown per-label deltas: adj {tot['adj'][0]:+.1f} "
          f"[{tot['adj'][1]:+.1f}, {tot['adj'][2]:+.1f}]  abs "
          f"{tot['raw'][0]:+.1f} [{tot['raw'][1]:+.1f}, {tot['raw'][2]:+.1f}] "
          "us/step (CI sums are indicative)")

    out = {"kind": kind, "arms": [base_arm, cand_arm], "offset": args.offset,
           "n_duplex": len(duplexes), "base_busy_us_step": base_busy,
           "labels": {}}
    for key, base_us, (am, ah, asd), (rm, rh, rsd) in rows:
        out["labels"][key] = {
            "base_us_step": base_us,
            "adj_us_step": base_us * math.expm1(am),
            "adj_ci": [base_us * math.expm1(am - ah), base_us * math.expm1(am + ah)],
            "abs_us_step": base_us * math.expm1(rm),
            "abs_ci": [base_us * math.expm1(rm - rh), base_us * math.expm1(rm + rh)],
            "abs_sd_us_step": base_us * rsd,
        }

    for name, getter in (("ratio-adjusted vs control",
                          lambda r: r["busy"] / r["totals"][control]),
                         ("unadjusted (absolute)", lambda r: r["busy"])):
        vals = contrast(runs, duplexes, getter)
        mean, hw, sd = ci(vals)
        d = base_busy * math.expm1(mean)
        lo = base_busy * math.expm1(mean - hw)
        hi = base_busy * math.expm1(mean + hw)
        print(f"\ntotal steady GPU busy, {name}: {d:+.1f} us/step "
              f"[{lo:+.1f}, {hi:+.1f}]  ({100*math.expm1(mean):+.3f}%)")
        print(f"  score: {d*PCT_PER_US_STEP:+.4f}% "
              f"[{lo*PCT_PER_US_STEP:+.4f}, {hi*PCT_PER_US_STEP:+.4f}]")
        print(f"  per-duplex SD {base_busy*sd:.2f} us/step; "
              f"n={len(vals)} -> +-{base_busy*hw:.2f} us/step")
        if args.scale_to_n > 1:
            h = t95(args.scale_to_n - 1) * sd / math.sqrt(args.scale_to_n)
            print(f"  same SD at n={args.scale_to_n} -> "
                  f"+-{base_busy*h:.2f} us/step")
        key = "busy_adj" if name.startswith("ratio") else "busy_abs"
        out[key] = {"us_step": d, "ci": [lo, hi],
                    "sd_us_step": base_busy * sd, "n": len(vals)}

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
