#!/usr/bin/env python3
"""Localize the DispatchTypeConcurrent benefit across command-buffer split
levels and derive the per-command-buffer cost `c` without overlap confounding.

Inputs are two A0 output directories:
  --split  phases h1k1 (1 dispatch/CB) and h1k2 (2 dispatches/CB)
  --base   phase  h1k0 (shipped ~9 dispatches/CB)

Two independent quantities come out.

`c`, the per-command-buffer GPU cost.  In *serial* dispatch mode there is by
construction no intra-buffer overlap at any split level, so the serial arms
differ only by their command-buffer counts:

    c = [busy_serial(k=1) - busy_serial(k=2)] / [cbs(k=1) - cbs(k=2)]

This is the clean measurement.  PR #158 instead used the concurrent arms, where
the difference also contains the whole overlap term, which is why its `c` came
out several times too large.

The localization.  D(k) = busy_serial(k) - busy_concurrent(k) is the overlap
destroyed at split level k.  Uniform seam pipelining (R-A) predicts D(k)
proportional to the number of intra-buffer seams, seams(k) = dispatches -
cbs(k).  Sibling shadowing (R-B) predicts D(2) ~ D(0) because one hazard-free
neighbour is enough to hide a small kernel.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nezuko_a0_analyze import load_run, perm_p  # noqa: E402


def phase_stats(root: Path, phase: str):
    runs = [load_run(p) for p in sorted(root.glob(f"{phase}_*.txt"))
            if not p.name.endswith(".steps.txt")]
    runs = [r for r in runs if "busy_sum_ms" in r]
    conc = [r for r in runs if r["tag"].endswith("_concurrent")]
    ser = [r for r in runs if r["tag"].endswith("_serial")]
    if not conc or not ser:
        return None
    out = {
        "phase": phase,
        "n": (len(conc), len(ser)),
        "divergences_ok": all(r.get("divergences") == 0 for r in runs),
        "cbs": statistics.median([r["cbs"] for r in runs]),
        "dispatches": statistics.median([r["dispatches"] for r in runs]),
        "busy_conc": statistics.median([r["busy_sum_ms"] for r in conc]) * 1e3,
        "busy_ser": statistics.median([r["busy_sum_ms"] for r in ser]) * 1e3,
        "wall_conc": statistics.median([r["wall_median_ms"] for r in conc]) * 1e3,
        "wall_ser": statistics.median([r["wall_median_ms"] for r in ser]) * 1e3,
    }
    out["D_busy"] = out["busy_ser"] - out["busy_conc"]
    out["D_wall"] = out["wall_ser"] - out["wall_conc"]
    out["seams"] = out["dispatches"] - out["cbs"]
    if len(conc) == len(ser) >= 3:
        hits, total = perm_p([r["busy_sum_ms"] for r in conc],
                             [r["busy_sum_ms"] for r in ser])
        out["p_busy"] = hits / total
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="research/nezuko-a0-split")
    ap.add_argument("--base", default="research/nezuko-a0-dispatch-type")
    args = ap.parse_args()

    ph = {}
    for phase in ("h1k1", "h1k2"):
        s = phase_stats(Path(args.split), phase)
        if s:
            ph[phase] = s
    s = phase_stats(Path(args.base), "h1k0")
    if s:
        ph["h1k0"] = s

    print(f"  {'phase':>6} {'n':>7} {'cbs':>7} {'disp':>7} {'seams':>7} "
          f"{'busy_c':>9} {'busy_s':>9} {'D_busy':>8} {'D_wall':>8} "
          f"{'p':>7}  tokens")
    for k in ("h1k1", "h1k2", "h1k0"):
        if k not in ph:
            continue
        s = ph[k]
        print(f"  {k:>6} {s['n'][0]}v{s['n'][1]:<5} {s['cbs']:7.1f} "
              f"{s['dispatches']:7.1f} {s['seams']:7.1f} "
              f"{s['busy_conc']:9.1f} {s['busy_ser']:9.1f} "
              f"{s['D_busy']:+8.1f} {s['D_wall']:+8.1f} "
              f"{s.get('p_busy', float('nan')):7.3f}  "
              f"{'OK' if s['divergences_ok'] else 'DIVERGED'}")

    print()
    if "h1k1" in ph and "h1k0" in ph:
        a, z = ph["h1k1"], ph["h1k0"]
        dcb = a["cbs"] - z["cbs"]
        c = (a["busy_ser"] - z["busy_ser"]) / dcb
        print(f"  c (serial arms, k=1 vs k=0) = "
              f"({a['busy_ser']:.1f} - {z['busy_ser']:.1f}) / {dcb:.1f} "
              f"= {c:.3f} us/CB")
        w = z["busy_ser"] - z["cbs"] * c
        print(f"  zero-overlap work W        = {w:.1f} us/step")
        print(f"  PR #158 published c        = 1.596 us/CB "
              f"({1.596 / c:.1f}x this)")
        print(f"  census de-inflation        = "
              f"{c * dcb / z['dispatches']:.3f} us/dispatch "
              f"(PR #158 used 1.419)")

        # PR #158 computed c from the *concurrent* arms.  Substituting
        # busy_conc(k) = busy_ser(k) - D(k) makes that expression
        # c_true + [D(k=0) - D(k=1)]/dcb exactly: the inflation it saw and the
        # overlap it concluded was absent are the same number.
        c_pub = (a["busy_conc"] - z["busy_conc"]) / dcb
        dd = z["D_busy"] - a["D_busy"]
        print(f"\n  identity check: c from concurrent arms = "
              f"({a['busy_conc']:.1f} - {z['busy_conc']:.1f}) / {dcb:.1f} "
              f"= {c_pub:.3f}")
        print(f"    c_true + [D(k=0)-D(k=1)]/{dcb:.1f} = {c:.3f} + "
              f"{dd:.1f}/{dcb:.1f} = {c + dd / dcb:.3f}  <- same number")

    if "h1k1" in ph and "h1k2" in ph and "h1k0" in ph:
        a, b, z = ph["h1k1"], ph["h1k2"], ph["h1k0"]
        c_lo = (b["busy_ser"] - z["busy_ser"]) / (b["cbs"] - z["cbs"])
        c_hi = (a["busy_ser"] - b["busy_ser"]) / (a["cbs"] - b["cbs"])
        print(f"\n  c is NOT constant (serial arms, no overlap anywhere):")
        print(f"    c({z['cbs']:.0f} -> {b['cbs']:.0f} CB/step) = "
              f"{c_lo:.3f} us/CB")
        print(f"    c({b['cbs']:.0f} -> {a['cbs']:.0f} CB/step) = "
              f"{c_hi:.3f} us/CB")
        print(f"    ratio {c_hi / c_lo if c_lo else float('nan'):.0f}x -- a "
              f"single-slope model fitted at k=1 cannot be extrapolated to "
              f"the shipped split")
    if "h1k0" in ph and "h1k2" in ph:
        d0, d2 = ph["h1k0"]["D_busy"], ph["h1k2"]["D_busy"]
        r_obs = d2 / d0 if d0 else float("nan")
        r_ra = ph["h1k2"]["seams"] / ph["h1k0"]["seams"]
        print(f"\n  D(k=2)/D(k=0) observed     = {r_obs:.3f}")
        print(f"    R-A uniform seams predicts {r_ra:.3f} "
              f"({ph['h1k2']['seams']:.0f}/{ph['h1k0']['seams']:.0f} seams)")
        print(f"    R-B sibling shadow predicts ~0.95")
        verdict = ("R-B sibling shadowing" if r_obs > (r_ra + 0.95) / 2
                   else "R-A uniform seam pipelining")
        print(f"  VERDICT: {verdict}")
    if "h1k1" in ph:
        d1 = ph["h1k1"]["D_busy"]
        print(f"\n  control D(k=1) = {d1:+.1f} us/step "
              f"(must be ~0; >50 us withdraws the A0 conclusion)")
        print(f"    same runs, wall currency: {ph['h1k1']['D_wall']:+.1f} "
              f"us/step (opposite sign)")
        if "h1k0" in ph and "h1k2" in ph:
            print(f"    treating D(k=1) as additive bias: "
                  f"D(k=0)={ph['h1k0']['D_busy'] - d1:+.1f}, "
                  f"D(k=2)={ph['h1k2']['D_busy'] - d1:+.1f}, "
                  f"ratio {(ph['h1k2']['D_busy'] - d1) / (ph['h1k0']['D_busy'] - d1):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
