#!/usr/bin/env python3
"""Paired local-submit timing ledger for the R109-F integration arm.

Reads the `score.local-submit.<family><n>.json` snapshots that
`./benchmark.sh --local-submit` leaves in `score.json` (one copy per
replicate, because the harness overwrites `score.json` every run) and reports
per-family dispersion plus the paired candidate-vs-baseline ratios that the
official weighted score uses:

    score = decode_speedup^0.75 * prefill_speedup^0.25

Everything here is a *ratio between two families measured on this host*.  The
absolute `score` field a local run prints is not comparable to an official M5
receipt: this box is an M4 Pro, whose prefill is far slower relative to the
pinned M5 prefill constant, so `prefill_speedup` and therefore the local score
are structurally depressed.  Only same-host candidate/baseline ratios carry
information.

Usage:
    python3 research/fern_r109_timing_ledger.py                # all families
    python3 research/fern_r109_timing_ledger.py base cand      # pair two
"""

import argparse
import json
import math
import pathlib
import re
import statistics
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^score\.local-submit\.([A-Za-z0-9_\-]+?)(\d+)\.json$")
PAIRED_DIR = pathlib.Path("research/artifacts/fern-r109f/paired")
PAIRED_PATTERN = re.compile(
    r"^([A-Za-z0-9_\-]+?)-(\d{8}T\d{6}Z)-(\d+)-([A-Za-z0-9]+)\.json$"
)

DECODE_W = 0.75
PREFILL_W = 0.25

# Official-M5 pinned baseline seconds/token, used by the campaign `ns` proxy.
NS_DECODE_REF = 0.013890
NS_PREFILL_REF = 0.0003845

# Score axes.  One scored window is a 512-token prefill plus 128 one-token
# decode steps, so the prefill cost enters the decode budget as S/128.
PREFILL_TOKENS = 512
DECODE_STEPS = 128

# Official-M5 frontier operating point (research/maple-fern-terminal-report.md
# section 4).  The elasticities are an identity of the score formula at a given
# operating point, not a regression fit.
M5_ELAST_S = 0.362
M5_ELAST_T = 0.638

# Bar to clear: the successor must beat official receipt e27f1ce (2.60664969
# at commit 5c542169) by this weighted factor.
BAR_WEIGHTED_RATIO = 1.003780272


def axes(decode_s, prefill_s):
    """Split a (decode, prefill) seconds/token pair into the two score axes.

    `S` is whole-prefill milliseconds, `D` is per-decode-step milliseconds and
    `T = D - S/128` is the steady per-step cost that carries no prefill share.
    `sigma` is the prefill fraction of one decode step; both elasticities are
    fixed by it.
    """
    S = PREFILL_TOKENS * 1000.0 * prefill_s
    D = 1000.0 * decode_s
    T = D - S / DECODE_STEPS
    sigma = (S / DECODE_STEPS) / D
    return {
        "S_ms": S,
        "D_ms": D,
        "T_ms": T,
        "sigma": sigma,
        "elast_S": 0.25 + 0.75 * sigma,
        "elast_T": 0.75 * (1.0 - sigma),
    }


def m5_projection(base, cand, tau=1.0):
    """Re-price a local paired result with the official-M5 elasticities.

    A local harness reports its own `ns` ratio at its own operating point, so
    the same physical saving scores differently on `--local-iterate`
    (sigma~34%, elast_T 0.498) than on `--local-submit` (sigma~6%, elast_T
    0.706) than on the ranked M5 (sigma~15%, elast_T 0.638).  Projecting the
    measured fractional moves along S and T through the M5 elasticities
    removes that 1.42x harness swing; `tau` is the mechanism-class transfer
    factor (~1.0 dispatch-overhead, ~1.06 DRAM-traffic, unknown for
    threadgroup-geometry changes, which can flip sign).
    """
    b = axes(base["decode_median"], base["prefill_median"])
    c = axes(cand["decode_median"], cand["prefill_median"])
    dln_S = math.log(c["S_ms"] / b["S_ms"])
    dln_T = math.log(c["T_ms"] / b["T_ms"])
    ln_ratio = -tau * (M5_ELAST_S * dln_S + M5_ELAST_T * dln_T)
    projected = math.exp(ln_ratio)
    return {
        "tau": tau,
        "base_sigma": b["sigma"],
        "base_elast_T": b["elast_T"],
        "base_T_ms": b["T_ms"],
        "cand_T_ms": c["T_ms"],
        "delta_T_us": (b["T_ms"] - c["T_ms"]) * 1000.0,
        "delta_S_ms": b["S_ms"] - c["S_ms"],
        "harness_normalization": M5_ELAST_T / b["elast_T"],
        "projected_m5_ratio": projected,
        "beats_bar": projected > BAR_WEIGHTED_RATIO,
    }


def load_families(root=ROOT, drop_first=False):
    """`drop_first` discards each family's lowest-numbered replicate.

    Stage-0 measured a reproducible cold-start penalty on the first
    `--local-submit` of a session (+0.75% decode, +1.07% prefill against the
    steady-state median of the next four), so a blocked design that compares a
    fresh baseline family against a later candidate family is biased in the
    candidate's favour by more than the whole ranked bar.
    """
    fams = defaultdict(list)
    for path in sorted(root.glob("score.local-submit.*.json")):
        m = PATTERN.match(path.name)
        if not m:
            continue
        d = json.loads(path.read_text())
        met = d["metrics"]
        fams[m.group(1)].append(
            {
                "replicate": int(m.group(2)),
                "path": path.name,
                "decode": met["decode_seconds_per_token"],
                "prefill": met["prefill_seconds_per_token"],
                "score": d["score"],
                "passed": d["passed"],
                "correct": met["passed_correctness"],
                "max_abs_diff": met["max_abs_diff"],
                "golden_hash": met["golden_hash"],
                "commit": met["commit"],
                "timestamp": met["timestamp"],
                "peak_ram_gb": met["peak_ram_gb"],
                "base_decode": met["baseline_decode_seconds_per_token"],
                "base_prefill": met["baseline_prefill_seconds_per_token"],
            }
        )
    for name, reps in fams.items():
        reps.sort(key=lambda r: r["replicate"])
        if drop_first and len(reps) > 1:
            fams[name] = reps[1:]
    return fams


def load_paired(root=ROOT, tag=None, session=None):
    """Load the interleaved paired driver's per-slot snapshots, keyed by arm.

    `fern_r109f_paired_submit.sh` runs several arms inside one session from
    pre-staged worker binaries, so its slot index -- not a per-family counter --
    is the replicate identity, and the session's warmup arm is simply an arm the
    caller does not name.
    """
    fams = defaultdict(list)
    for path in sorted((root / PAIRED_DIR).glob("*.json")):
        m = PAIRED_PATTERN.match(path.name)
        if not m:
            continue
        if tag and m.group(1) != tag:
            continue
        if session and m.group(2) != session:
            continue
        d = json.loads(path.read_text())
        met = d["metrics"]
        fams[m.group(4)].append(
            {
                "replicate": int(m.group(3)),
                "path": path.name,
                "decode": met["decode_seconds_per_token"],
                "prefill": met["prefill_seconds_per_token"],
                "score": d["score"],
                "passed": d["passed"],
                "correct": met["passed_correctness"],
                "max_abs_diff": met["max_abs_diff"],
                "golden_hash": met["golden_hash"],
                "commit": met["commit"],
                "timestamp": met["timestamp"],
                "peak_ram_gb": met["peak_ram_gb"],
                "base_decode": met["baseline_decode_seconds_per_token"],
                "base_prefill": met["baseline_prefill_seconds_per_token"],
            }
        )
    for reps in fams.values():
        reps.sort(key=lambda r: r["replicate"])
    return fams


def stats(vals):
    med = statistics.median(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return med, sd, sd / med if med else 0.0


def spread(vals):
    lo, hi = min(vals), max(vals)
    return (hi - lo) / statistics.median(vals)


def detection_floor(cv, n, sigmas=2.0):
    """Smallest relative difference two same-n families can resolve.

    Both arms carry the same sampling error, so the standard error of their
    ratio is cv/sqrt(n) * sqrt(2).
    """
    if n < 2:
        return float("inf")
    return sigmas * cv / (n**0.5) * (2**0.5)


def replicates_needed(target, cv, sigmas=2.0):
    """Per-family replicate count needed to resolve `target` at `sigmas`."""
    return math.ceil(2.0 * (sigmas * cv / target) ** 2)


def normalized_score(decode, prefill):
    """The campaign `ns` proxy: official-M5 baseline seconds/token over ours."""
    return (NS_DECODE_REF / decode) ** DECODE_W * (NS_PREFILL_REF / prefill) ** PREFILL_W


def summarize(name, reps):
    dec = [r["decode"] for r in reps]
    pre = [r["prefill"] for r in reps]
    nsv = [normalized_score(r["decode"], r["prefill"]) for r in reps]
    _, _, dcv = stats(dec)
    _, _, pcv = stats(pre)
    _, _, ncv = stats(nsv)
    return {
        "family": name,
        "n": len(reps),
        "ns_median": statistics.median(nsv),
        "ns_min": min(nsv),
        "ns_max": max(nsv),
        "ns_cv": ncv,
        "decode_median": statistics.median(dec),
        "decode_min": min(dec),
        "decode_max": max(dec),
        "decode_spread": spread(dec),
        "decode_cv": dcv,
        "prefill_median": statistics.median(pre),
        "prefill_min": min(pre),
        "prefill_max": max(pre),
        "prefill_spread": spread(pre),
        "prefill_cv": pcv,
        "all_correct": all(r["correct"] for r in reps),
        "max_abs_diff": max(r["max_abs_diff"] for r in reps),
        "golden_hashes": sorted({r["golden_hash"] for r in reps}),
        "commits": sorted({r["commit"] for r in reps}),
    }


def paired(base, cand):
    """Candidate-vs-baseline weighted ratio from medians (lower s/token wins)."""
    d = base["decode_median"] / cand["decode_median"]
    p = base["prefill_median"] / cand["prefill_median"]
    return {
        "decode_ratio": d,
        "prefill_ratio": p,
        "weighted_ratio": d**DECODE_W * p**PREFILL_W,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("families", nargs="*", help="baseline family first")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--drop-first",
        action="store_true",
        help="discard each family's first replicate (cold-start outlier)",
    )
    ap.add_argument(
        "--paired",
        action="store_true",
        help=f"read interleaved per-slot snapshots from {PAIRED_DIR} instead",
    )
    ap.add_argument("--tag", help="restrict --paired to one campaign tag")
    ap.add_argument("--session", help="restrict --paired to one session stamp")
    ap.add_argument(
        "--tau",
        type=float,
        default=1.0,
        help="M4->M5 mechanism-class transfer factor: 1.0 dispatch overhead, "
        "1.06 DRAM traffic, unknown (can flip sign) for threadgroup geometry",
    )
    args = ap.parse_args()

    if args.paired:
        fams = load_paired(tag=args.tag, session=args.session)
        if args.drop_first:
            for name, reps in fams.items():
                if len(reps) > 1:
                    fams[name] = reps[1:]
        if not fams:
            print(f"no paired snapshots under {PAIRED_DIR}", file=sys.stderr)
            return 1
    else:
        fams = load_families(drop_first=args.drop_first)
        if not fams:
            print(
                "no score.local-submit.<family><n>.json snapshots found",
                file=sys.stderr,
            )
            return 1

    names = args.families or sorted(fams)
    missing = [n for n in names if n not in fams]
    if missing:
        print(f"unknown families: {missing}; have {sorted(fams)}", file=sys.stderr)
        return 1

    summaries = {n: summarize(n, fams[n]) for n in names}

    if args.json:
        out = {"families": summaries}
        if len(names) >= 2:
            base = summaries[names[0]]
            out["pairs"] = {
                n: {
                    **paired(base, summaries[n]),
                    "m5": m5_projection(base, summaries[n], tau=args.tau),
                }
                for n in names[1:]
            }
        print(json.dumps(out, indent=2))
        return 0

    for n in names:
        s = summaries[n]
        print(f"=== {n}  (n={s['n']}) ===")
        for r in fams[n]:
            print(
                f"  rep{r['replicate']}  decode={r['decode']:.9f}  "
                f"prefill={r['prefill']:.9f}  "
                f"ns={normalized_score(r['decode'], r['prefill']):.6f}  "
                f"correct={r['correct']}  diff={r['max_abs_diff']}  "
                f"commit={r['commit']}  {r['timestamp']}"
            )
        print(
            f"  ns      median={s['ns_median']:.6f} "
            f"min={s['ns_min']:.6f} max={s['ns_max']:.6f} "
            f"cv={s['ns_cv'] * 100:.3f}% "
            f"2sigma-paired-floor={detection_floor(s['ns_cv'], s['n']) * 100:.3f}%"
        )
        print(
            f"  decode  median={s['decode_median']:.9f} "
            f"min={s['decode_min']:.9f} max={s['decode_max']:.9f} "
            f"spread={s['decode_spread'] * 100:.3f}% cv={s['decode_cv'] * 100:.3f}%"
        )
        print(
            f"  prefill median={s['prefill_median']:.9f} "
            f"min={s['prefill_min']:.9f} max={s['prefill_max']:.9f} "
            f"spread={s['prefill_spread'] * 100:.3f}% cv={s['prefill_cv'] * 100:.3f}%"
        )
        print(
            "  2-sigma detection floor for a same-n paired comparison: "
            f"decode {detection_floor(s['decode_cv'], s['n']) * 100:.3f}% "
            f"prefill {detection_floor(s['prefill_cv'], s['n']) * 100:.3f}%"
        )
        print(
            f"  correctness: all_correct={s['all_correct']} "
            f"max_abs_diff={s['max_abs_diff']} "
            f"golden_hashes={s['golden_hashes']}"
        )
        print()

    if len(names) >= 2:
        base = summaries[names[0]]
        bx = axes(base["decode_median"], base["prefill_median"])
        print(f"=== paired ratios vs {names[0]} (>1 means candidate faster) ===")
        print(
            f"  baseline operating point: S={bx['S_ms']:.1f}ms "
            f"T={bx['T_ms']:.4f}ms sigma={bx['sigma'] * 100:.1f}% "
            f"elast_S={bx['elast_S']:.3f} elast_T={bx['elast_T']:.3f}"
        )
        print(
            f"  harness normalization vs M5 (pure steady-step win): "
            f"x{M5_ELAST_T / bx['elast_T']:.3f}"
        )
        for n in names[1:]:
            pr = paired(base, summaries[n])
            m5 = m5_projection(base, summaries[n], tau=args.tau)
            print(
                f"  {n}: decode x{pr['decode_ratio']:.6f}  "
                f"prefill x{pr['prefill_ratio']:.6f}  "
                f"weighted x{pr['weighted_ratio']:.6f}"
            )
            print(
                f"      dT={m5['delta_T_us']:+.1f}us dS={m5['delta_S_ms']:+.3f}ms "
                f"-> M5 projected x{m5['projected_m5_ratio']:.6f} "
                f"(tau={m5['tau']:.2f}) "
                f"bar x{BAR_WEIGHTED_RATIO:.6f} "
                f"{'CLEARS' if m5['beats_bar'] else 'below'}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
