#!/usr/bin/env python3
"""Research-only analysis for the six-arm QKV-GEMV threadgroup-packing curve.

  python3 research/tanjiro_packing_stats.py /tmp/tanjiro/abba [--trim 0.05]

Every estimator here is `research/nezuko_pr48_stats.py`'s, imported and reused
unchanged: the upper-trimmed per-run estimator, the within-run interference
report, the block-paired CI, and the two-way fixed-effects OLS. Only the arm
*labels* and the contrast set are relabelled for the packing axis, plus a
monotonicity / argmax verdict that a two-point sweep could not produce.
"""
import argparse
import importlib.util
import math
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "nezuko_pr48_stats", os.path.join(_HERE, "nezuko_pr48_stats.py"))
nz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nz)

# label -> simdgroups per threadgroup. "0" is the reference arm in nz's OLS.
S_OF = {"0": 2, "RV": 1, "V": 4, "G": 8, "R": 16, "N": 32}
ORDER = ["RV", "0", "V", "G", "R", "N"]  # ascending S
PIVOT = "R"  # S=16, the PR #298 winner: fixed before any data was collected

nz.ARM_DESC = {
    lab: f"S={S_OF[lab]:<2d} simdgroups/threadgroup"
         + ("   (shipped default, reference)" if lab == "0" else "")
    for lab in S_OF
}
nz.CONTRASTS = [
    (f"{lab}-0", lab, "0", f"S={S_OF[lab]} vs shipped default S=2")
    for lab in ORDER if lab != "0"
] + [
    ("N-R", "N", "R", "S=32 vs S=16: does the curve keep improving past 16?"),
    ("R-G", "R", "G", "S=16 vs S=8: local slope at the PR #298 winner"),
    ("V-RV", "V", "RV", "S=4 vs S=1: local slope at the small end"),
]


def curve_verdict(runs, blocks):
    """Monotonicity / argmax verdict on the fixed-effects arm means."""
    try:
        effect, se_diff, df, rsd = nz.ols(runs, blocks)
    except ValueError as exc:
        print(f"\ncurve verdict skipped: {exc}")
        return
    present = [lab for lab in ORDER if any(r[2] == lab for r in runs)]
    ref = statistics.mean([r[3] for r in runs if r[2] == "0"])
    print("\npacking curve (fixed-effects, us/step, relative to shipped S=2)")
    print(f"{'S':>4} {'arm':>4} {'effect':>9} {'se':>7} {'t':>7} {'95% CI':>20}")
    pts = []
    for lab in present:
        e = effect(lab)
        se, _ = se_diff(lab, "0")
        h = nz.t95(df) * se
        t = e / se if se else float("nan")
        pts.append((S_OF[lab], lab, e, se))
        print(f"{S_OF[lab]:>4} {lab:>4} {e:9.1f} {se:7.1f} {t:7.2f}"
              f"  [{e - h:7.1f},{e + h:7.1f}]")
    print(f"reference arm S=2 absolute mean {ref:.1f} us/step; "
          f"residual sd {rsd:.1f} us over {df} df")

    # Monotonicity is only meaningful against the noise floor: a step is called
    # a rise/fall only when it clears its own 95% half-width.
    ups = downs = flats = 0
    steps = []
    for (s0, l0, e0, _), (s1, l1, e1, _) in zip(pts, pts[1:]):
        se, _ = se_diff(l1, l0)
        h = nz.t95(df) * se
        d = e1 - e0
        tag = "flat" if abs(d) <= h else ("faster" if d < 0 else "slower")
        steps.append((s0, s1, d, h, tag))
        if tag == "faster":
            downs += 1
        elif tag == "slower":
            ups += 1
        else:
            flats += 1
    print("\nadjacent steps (negative = larger S is faster)")
    for s0, s1, d, h, tag in steps:
        print(f"  S={s0:<2d} -> S={s1:<2d} {d:+8.1f} +/- {h:5.1f}   {tag}")

    best = min(pts, key=lambda p: p[2])
    tied = []
    for s, lab, e, _ in pts:
        se, _ = se_diff(lab, best[1])
        if lab == best[1] or abs(e - best[2]) <= nz.t95(df) * se:
            tied.append(s)

    # An adjacent-step scan alone cannot see a shallow wide-bottomed U: every
    # individual step can sit inside the noise floor while the cumulative
    # descent and the far-end rise both clear theirs.  So the interior-optimum
    # question is asked directly, against both sweep endpoints.
    def endpoints(lab):
        out = []
        for other in (pts[0][1], pts[-1][1]):
            if other == lab:
                out.append(None)
                continue
            se, _ = se_diff(lab, other)
            d = effect(lab) - effect(other)
            out.append((S_OF[other], d, nz.t95(df) * se))
        return out

    def interior(lab):
        lo, hi = endpoints(lab)
        return (lo and lo[1] < -lo[2]) and (hi and hi[1] < -hi[2])

    if downs and not ups:
        verdict = "MONOTONE-DECREASING (larger S never significantly worse)"
    elif ups and not downs:
        verdict = "MONOTONE-INCREASING (smaller S never significantly worse)"
    elif downs and ups:
        verdict = "NON-MONOTONE (U-shaped / interior optimum)"
    else:
        verdict = "FLAT (no adjacent step clears its own 95% half-width)"
    print(f"\nadjacent-step monotonicity verdict: {verdict}")
    print(f"  {downs} faster step(s), {ups} slower step(s), {flats} flat step(s)")

    print("\ninterior-optimum test (arm vs BOTH sweep endpoints)")
    rows = [(PIVOT, "pre-registered pivot")]
    if best[1] == PIVOT:
        rows = [(PIVOT, "pre-registered pivot == observed argmax")]
    else:
        rows.append((best[1], "observed argmax, selection-biased"))
    for lab, tag in rows:
        if not any(p[1] == lab for p in pts):
            continue
        cells = []
        for pair in endpoints(lab):
            cells.append("(self)" if pair is None else
                         f"vs S={pair[0]}: {pair[1]:+.1f} +/- {pair[2]:.1f}")
        flag = "INTERIOR OPTIMUM" if interior(lab) else "not established"
        print(f"  S={S_OF[lab]:<2d} ({tag:<34s}) "
              f"{cells[0]:<26s} {cells[1]:<26s} -> {flag}")

    print(f"\nargmax S={best[0]} at {best[2]:+.1f} us/step vs default; "
          f"statistically tied set = {sorted(tied)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--trim", type=float, default=0.0)
    args = ap.parse_args()

    sys.argv = ["nz", args.outdir, "--warmup", str(args.warmup),
                "--trim", str(args.trim)]
    rc = nz.main()
    if rc:
        return rc
    runs = [r for r in nz.load(args.outdir, args.warmup, args.trim) if r[1] > 0]
    curve_verdict(runs, sorted({r[1] for r in runs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
