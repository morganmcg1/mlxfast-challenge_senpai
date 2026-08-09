#!/usr/bin/env python3
"""Research-only (PR #456, R85-B rev2): neutrality statistics for the split arm.

`maple_r85_arm_stats.py` already reports the per-kernel and total GPU-busy
duplex contrast. This script covers the three things that arm additionally
needs and that the GPU-busy instrument cannot supply on its own:

  * **cbs-per-step verification.** `--cbs-per-step 406` is a session constant,
    not a program constant. Re-derive it by counting GPUPROF records between
    consecutive `argmax_bfloat16` records rather than inheriting #457's value.

  * **Wall clock from the very same runs.** The split moves *host* code, and a
    kernel-busy instrument is blind to CPU-side dispatch cost by construction.
    The `.steps` dumps already exist, so the wall-clock duplex costs no extra
    GPU time and shares the pairing, the session and the drift structure.

  * **Non-inferiority arithmetic.** "Neutral" is a one-sided claim: what must
    be excluded is a *cost*. Report the one-sided upper confidence bound, the
    margin it clears, and the detectable-effect floor delta_min(n) that the
    observed per-duplex SD implies, so the rig's resolution is stated rather
    than assumed.

Usage:
    python3 research/maple_r85b_split_stats.py --out /tmp/maple-r85b-split \\
        --arms base cand --offset 0 --delta 5.0
"""
import argparse
import glob
import json
import math
import os
import re
import statistics

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z0-9_]+)\.steps$")

# Two-sided 95% and one-sided 95% / 80% Student-t quantiles by df.
T95_2S = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
          7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
          14: 2.145, 15: 2.131, 19: 2.093, 23: 2.069}
T95_1S = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943,
          7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782,
          14: 1.761, 15: 1.753, 19: 1.729, 23: 1.714}
T80_1S = {1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906,
          7: 0.896, 8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876, 12: 0.873,
          14: 0.868, 15: 0.866, 19: 0.861, 23: 0.858}
# Chi-square 2.5% / 97.5% quantiles, for the sampling uncertainty on sd itself.
CHI2_LO = {3: 0.216, 4: 0.484, 5: 0.831, 7: 1.690, 8: 2.180, 11: 3.816,
           15: 6.262, 23: 11.689}
CHI2_HI = {3: 9.348, 4: 11.143, 5: 12.833, 7: 16.013, 8: 17.535, 11: 21.920,
           15: 27.488, 23: 38.076}


def _lookup(table, df):
    if df in table:
        return table[df]
    keys = sorted(table)
    return table[min(keys, key=lambda k: abs(k - df))]


def verify_cbs_per_step(err_paths, marker="argmax_bfloat16"):
    """Count GPUPROF records between consecutive markers -> command buffers/step."""
    counts = []
    for path in err_paths:
        gaps, since, seen = [], 0, False
        with open(path, errors="replace") as fh:
            for line in fh:
                if not line.startswith("GPUPROF"):
                    continue
                since += 1
                if marker in line:
                    if seen:
                        gaps.append(since)
                    seen, since = True, 0
        if gaps:
            counts.append(statistics.mode(gaps))
    return counts


def load_steps(out_dir, drop_first=1):
    runs = []
    for path in sorted(glob.glob(os.path.join(out_dir, "[0-9]*.steps"))):
        m = SLOT_RE.match(os.path.basename(path))
        if not m:
            continue
        vals = [float(x) for x in open(path).read().split()]
        vals = vals[drop_first:]
        if not vals:
            continue
        runs.append(dict(slot=int(m.group(1)), rep=int(m.group(2)),
                         arm=m.group(3), n_steps=len(vals),
                         mean_ms=statistics.mean(vals),
                         median_ms=statistics.median(vals)))
    runs.sort(key=lambda r: r["slot"])
    return runs


def select_duplexes(runs, base_arm, cand_arm, offset):
    """Adjacent pairs at one pairing phase; mirrors maple_r85_arm_stats.py."""
    out, null = [], base_arm == cand_arm
    for i in range(offset, len(runs) - 1, 2):
        a, b = runs[i], runs[i + 1]
        if null:
            if a["arm"] != base_arm or b["arm"] != base_arm:
                continue
            out.append((i, 1.0 if len(out) % 2 == 0 else -1.0))
        else:
            if {a["arm"], b["arm"]} != {base_arm, cand_arm}:
                continue
            out.append((i, 1.0 if b["arm"] == cand_arm else -1.0))
    return out


def analyse(runs, duplexes, base_arm, key="mean_ms"):
    vals = [sign * (math.log(runs[i + 1][key]) - math.log(runs[i][key]))
            for i, sign in duplexes]
    base_us = statistics.mean(
        [r[key] * 1e3 for r in runs if r["arm"] == base_arm])
    n = len(vals)
    mean = statistics.mean(vals)
    sd = statistics.stdev(vals) if n > 1 else float("nan")
    return dict(n=n, log_mean=mean, log_sd=sd, base_us=base_us,
                d_us=base_us * math.expm1(mean),
                sd_us=base_us * sd)


def report(tag, res, delta_us, scale_to=(8, 16, 24)):
    n, sd_us, d_us = res["n"], res["sd_us"], res["d_us"]
    df = n - 1
    print(f"\n=== {tag} ===")
    print(f"  base level              {res['base_us']:.1f} us/step")
    print(f"  n duplexes              {n}")
    if n < 2:
        print("  (too few duplexes for an interval)")
        return {}
    t2, t1, t80 = _lookup(T95_2S, df), _lookup(T95_1S, df), _lookup(T80_1S, df)
    se = sd_us / math.sqrt(n)
    hw2, hw1 = t2 * se, t1 * se
    print(f"  per-duplex SD           {sd_us:.2f} us/step")
    print(f"  point estimate          {d_us:+.2f} us/step "
          f"({100 * math.expm1(res['log_mean']):+.4f}%)")
    print(f"  two-sided 95% CI        [{d_us - hw2:+.2f}, {d_us + hw2:+.2f}]")
    print(f"  one-sided 95% UPPER     {d_us + hw1:+.2f} us/step  "
          f"(the neutrality-relevant bound)")
    verdict = "NON-INFERIOR" if d_us + hw1 < delta_us else "NOT ESTABLISHED"
    print(f"  vs margin delta={delta_us:+.2f}: {verdict}")
    # Detectable-effect floor at 80% power, one-sided alpha=0.05.
    print(f"  delta_min(n={n}) = ({t1:.3f}+{t80:.3f})*{sd_us:.2f}/sqrt({n}) "
          f"= {(t1 + t80) * se:.2f} us/step")
    for m in scale_to:
        tm1, tm80 = _lookup(T95_1S, m - 1), _lookup(T80_1S, m - 1)
        print(f"    same SD at n={m:<3d} -> floor {(tm1 + tm80) * sd_us / math.sqrt(m):6.2f}"
              f"  |  one-sided halfwidth {tm1 * sd_us / math.sqrt(m):6.2f}")
    lo, hi = _lookup(CHI2_LO, df), _lookup(CHI2_HI, df)
    print(f"  95% CI on the SD itself [{sd_us * math.sqrt(df / hi):.2f}, "
          f"{sd_us * math.sqrt(df / lo):.2f}] us/step "
          f"(x[{math.sqrt(df / hi):.2f}, {math.sqrt(df / lo):.2f}])")
    return dict(n=n, d_us=d_us, sd_us=sd_us, ci95=[d_us - hw2, d_us + hw2],
                upper_1s=d_us + hw1, delta_us=delta_us, verdict=verdict,
                floor_us=(t1 + t80) * se, base_us=res["base_us"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--delta", type=float, default=5.0,
                    help="non-inferiority margin in us/step")
    ap.add_argument("--drop-first", type=int, default=1)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    errs = sorted(glob.glob(os.path.join(args.out, "[0-9]*.err")))
    if errs:
        counts = verify_cbs_per_step(errs[:4])
        print(f"cbs-per-step observed in this session: {counts} "
              f"(#457 used 406)")

    runs = load_steps(args.out, args.drop_first)
    print(f"\nloaded {len(runs)} runs, "
          f"{runs[0]['n_steps'] if runs else 0} steady steps each")
    order = " ".join(r["arm"] for r in runs)
    print(f"slot order: {order}")

    results = {}
    plan = [("EFFECT  base vs cand (offset 0)", "base", "cand", 0),
            ("LOTTERY cand vs cand2 (offset 1)", "cand", "cand2", 1),
            ("NULL    cand2 vs cand2 (offset 0)", "cand2", "cand2", 0),
            ("NULL    base vs base (offset 1)", "base", "base", 1)]
    for tag, a, b, off in plan:
        dup = select_duplexes(runs, a, b, off)
        if not dup:
            print(f"\n=== {tag} ===\n  no duplexes matched")
            continue
        results[tag] = report(tag, analyse(runs, dup, a), args.delta)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({"wall_clock": results}, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
