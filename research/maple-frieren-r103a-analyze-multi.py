#!/usr/bin/env python3
"""Paired analysis of an N-arm palindromic within-session timing run (PR #571).

Written for the advisor amendment r103-a-fb2, which replaces the two-arm
OLD/NEW contrast with three arms:

    A = 30f752df  Arm R receipt tree      (7ce1262d, cs 2.589321)
    B = e17bdeb1  frontier receipt tree   (e08d759f, cs 2.582286)
    C = 0f6862d0  assignment base = B + R3 (#558), never measured officially

and demotes the +20.15 us/step "missing microseconds" figure from a target to a
falsification candidate. The deliverable is therefore no longer a verdict about
a known effect; it is an *exclusion bound*: "this experiment excludes effects
larger than X us/step", with X attached, for every pair of arms.

Design assumption: each repetition runs the arms in a palindrome, e.g.

    pos    1  2  3  4  5  6
    arm    A  B  C  C  B  A

so every arm's per-rep estimate is the mean of two slots placed symmetrically
about the rep midpoint. Linear session drift therefore cancels to first order
in *every* pairwise contrast, not just one privileged pair. The within-arm
difference (later slot - earlier slot) is a rule-79 identical-code null at a
known position separation, and the set of separations {1, 3, 5} measures the
drift-versus-separation curve directly - which is the calibration the two-arm
design could not supply.

This analyzer is design-agnostic: it reads index.tsv, groups by repetition,
and emits a contrast for every arm pair and a null for every arm that appears
more than once per repetition. It therefore also runs on the original 4-slot
`oldA old new oldB` layout as a cross-check.

    python3 research/maple-frieren-r103a-analyze-multi.py OUTDIR [WARMUP_REPS]
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "r103a_analyze", _HERE / "maple-frieren-r103a-analyze.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)  # type: ignore[union-attr]
slot_stats, paired, t95 = _base.slot_stats, _base.paired, _base.t95

# M5->M4 magnitude transfer, R1 (see doc section 1.5d "bar sensitivity"): a
# delta of d us/step on M5 is expected to appear as d/0.622 on M4. Valid only
# within one mechanism class; reported alongside the three alternative
# assumptions so the reader can see how much the conversion carries.
TRANSFER = {
    "fixed-overhead (x1.000)": 1.000,
    "R1 empirical (x0.622)": 0.622,
    "proportional (x0.505)": 4141.540 / 8200.0,
    "bandwidth-ratio (x0.436)": 266.3 / 610.0,
}
R1 = 0.622
# The two reference magnitudes this arm was sent to test, in M5 us/step of T.
REF_M5 = {"A->B  'missing microseconds'": 20.149, "B->C  R3 (#558)": 0.0}
STATS = ("median", "trimmed", "mean")


def load(out: Path, warmup: int):
    """reps[rep][arm] = [(position, stats), ...], warm-up reps dropped."""
    reps: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for line in (out / "index.tsv").read_text().splitlines()[1:]:
        rep_s, pos_s, arm, tag = line.split("\t")
        rep = int(rep_s)
        if rep < warmup:
            continue
        p = out / f"{tag}.steps"
        if not p.exists() or not p.read_text().strip():
            print(f"  WARNING: missing or empty {p.name}; rep {rep} dropped")
            reps.pop(rep, None)
            continue
        reps[rep][arm].append((int(pos_s), slot_stats(p)))
    return reps


def arm_estimates(reps, stat: str):
    """rep -> arm -> mean of that arm's slot statistics in that repetition."""
    est: dict[int, dict[str, float]] = {}
    for rep, byarm in sorted(reps.items()):
        est[rep] = {a: statistics.mean(s[stat] for _, s in occ)
                    for a, occ in byarm.items()}
    return est


def nulls(reps, stat: str):
    """arm -> (separation, [later - earlier per repetition])."""
    out: dict[str, tuple[int, list[float]]] = {}
    seps: dict[str, list[int]] = defaultdict(list)
    vals: dict[str, list[float]] = defaultdict(list)
    for _, byarm in sorted(reps.items()):
        for arm, occ in byarm.items():
            if len(occ) < 2:
                continue
            occ = sorted(occ)
            vals[arm].append(occ[-1][1][stat] - occ[0][1][stat])
            seps[arm].append(occ[-1][0] - occ[0][0])
    for arm in vals:
        out[arm] = (max(set(seps[arm]), key=seps[arm].count), vals[arm])
    return out


def band(p: dict[str, float]) -> float:
    """Largest true effect this contrast is consistent with, in magnitude."""
    return max(abs(p["lo"]), abs(p["hi"]))


def main() -> None:
    out = Path(sys.argv[1])
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    reps = load(out, warmup)
    if not reps:
        sys.exit("no usable repetitions")
    arms = sorted({a for byarm in reps.values() for a in byarm})
    layout = sorted({(p, a) for byarm in reps.values()
                     for a, occ in byarm.items() for p, _ in occ})
    print(f"# rung 1B multi-arm paired analysis  ({out})")
    print(f"warm-up repetitions discarded: {warmup}")
    print(f"repetitions analysed: {len(reps)}   arms: {' '.join(arms)}")
    print("slot layout (position -> arm): "
          + "  ".join(f"{p}:{a}" for p, a in layout))

    report: dict = {"outdir": str(out), "warmup": warmup,
                    "reps": len(reps), "arms": arms,
                    "layout": [[p, a] for p, a in layout], "stats": {}}

    for stat in STATS:
        est = arm_estimates(reps, stat)
        print(f"\n########## statistic: {stat} (us/step) ##########")
        print("\nper-arm level, mean over repetitions:")
        for a in arms:
            xs = [e[a] for e in est.values() if a in e]
            print(f"  {a:>5}  {statistics.mean(xs):10.1f}"
                  f"   sd(rep) {statistics.stdev(xs) if len(xs) > 1 else float('nan'):7.2f}")

        print("\nrule-79 identical-code nulls (same arm, two slots, one rep):")
        print(f"  {'arm':>5} {'sep':>4} {'K':>3} {'mean':>9} {'95% hw':>9}"
              f" {'lo':>9} {'hi':>9}  sign +/-")
        null_out = {}
        for arm, (sep, diffs) in sorted(nulls(reps, stat).items()):
            p = paired(diffs)
            null_out[arm] = dict(p, separation=sep)
            print(f"  {arm:>5} {sep:>4} {p['k']:>3} {p['mean']:9.2f}"
                  f" {p['half_width']:9.2f} {p['lo']:9.2f} {p['hi']:9.2f}"
                  f"   {p['pos']}/{p['neg']}")
        print("  (drift scales with separation; the palindrome cancels drift in")
        print("   the contrasts below, so these are a conservative upper bound.)")

        print("\npaired contrasts, drift-cancelled (later arm - earlier arm):")
        print(f"  {'contrast':>10} {'K':>3} {'mean':>9} {'95% hw':>9}"
              f" {'lo':>9} {'hi':>9} {'excl>':>9}  sign +/-")
        con_out = {}
        for x, y in itertools.combinations(arms, 2):
            diffs = [e[y] - e[x] for e in est.values() if x in e and y in e]
            p = paired(diffs)
            b = band(p)
            con_out[f"{x}->{y}"] = dict(p, excludes_above_m4=b,
                                        excludes_above_m5_r1=b * R1)
            print(f"  {x:>4}->{y:<4} {p['k']:>3} {p['mean']:9.2f}"
                  f" {p['half_width']:9.2f} {p['lo']:9.2f} {p['hi']:9.2f}"
                  f" {b:9.2f}   {p['pos']}/{p['neg']}")
        report["stats"][stat] = {"nulls": null_out, "contrasts": con_out,
                                 "levels": {a: statistics.mean(
                                     [e[a] for e in est.values() if a in e])
                                     for a in arms}}

    # Everything below reads the primary statistic only (section 1.5a).
    est = arm_estimates(reps, "median")
    prim = report["stats"]["median"]["contrasts"]

    print("\n########## exclusion bounds (primary statistic: median) ##########")
    print("Reporting discipline (advisor fb2): never 'neutral' without an X.")
    for name, p in prim.items():
        b = p["excludes_above_m4"]
        print(f"  {name}: 95% CI [{p['lo']:.2f}, {p['hi']:.2f}] us/step M4."
              f"  Excludes |true effect| > {b:.1f} us/step M4"
              f"  = {b * R1:.1f} us/step M5-equivalent at the R1 factor.")
    print("\n  M5-equivalent of the achieved half-width under four transfer")
    print("  assumptions (a scalar factor is only valid within one mechanism")
    print("  class; this is the sensitivity, not four estimates):")
    for name, p in prim.items():
        hw = p["half_width"]
        row = "  ".join(f"{lbl.split()[0]} {hw * f:5.1f}"
                        for lbl, f in TRANSFER.items())
        print(f"    {name:<28} hw {hw:6.2f} M4  ->  {row}")

    print("\n########## precision check ##########")
    worst = max(p["half_width"] for p in prim.values())
    print(f"  worst contrast half-width {worst:.2f} us/step M4"
          f"  (target < 8.00, advisor fb2 'the number that decides the round')")
    print("  PASS" if worst < 8.0 else "  MISS: underpowered against the target")
    report["precision"] = {"worst_half_width_m4": worst, "target": 8.0,
                           "pass": bool(worst < 8.0)}

    print("\n########## N-2: is the null quiet? ##########")
    nl = report["stats"]["median"]["nulls"]
    for arm, p in sorted(nl.items()):
        flag = "" if p["lo"] <= 0 <= p["hi"] else "  <-- EXCLUDES ZERO"
        print(f"  {arm} (sep {p['separation']}): [{p['lo']:.2f},"
              f" {p['hi']:.2f}]{flag}")
    n2 = any(not (p["lo"] <= 0 <= p["hi"]) for p in nl.values())
    print("  N-2 fires (drift comparable to a contrast): "
          + ("YES - downgrade every contrast to inconclusive" if n2 else "no"))
    report["n2_fires"] = bool(n2)

    print("\n########## N-5: are all arms mutually indistinguishable? ##########")
    n5 = all(p["lo"] <= 0 <= p["hi"] for p in prim.values())
    print("  " + ("YES: every pairwise CI contains zero. Report the achieved"
                  " half-widths above and stop (advisor fb2)."
                  if n5 else
                  "no: at least one contrast excludes zero; see the table."))
    report["n5_fires"] = bool(n5)

    print("\n########## reference magnitudes ##########")
    for label, m5 in REF_M5.items():
        if m5:
            print(f"  {label}: {m5:.2f} us/step M5 = {m5 / R1:.1f} M4-equivalent")
        else:
            print(f"  {label}: no official same-base receipt exists; there is"
                  " no prior magnitude to test against.")

    print("\n########## diagnostics (not decision variables) ##########")
    for key in ("step0", "mean_first128", "tail_excess", "spike_count",
                "spike_mass"):
        e = arm_estimates(reps, key)
        row = "  ".join(
            f"{a} {statistics.mean([x[a] for x in e.values() if a in x]):9.2f}"
            for a in arms)
        print(f"  {key:>14}: {row}")

    (out / "analysis-multi.json").write_text(json.dumps(report, indent=2))
    print(f"\nwrote {out / 'analysis-multi.json'}")


if __name__ == "__main__":
    main()
