#!/usr/bin/env python3
"""Analyse the R86-A rev2 base-adoption gate: matched ABBA pair of the
pre-adoption base (f64456dd, arm "old") against the adopted base
(7687c2e4/HEAD, arm "new"), plus the correctness invariants that must hold
identically across every arm.

Delta convention matches the pre-registration: delta = old - new, so a
positive delta means the adopted base is faster.
"""

import glob
import json
import os
import statistics as st
import sys

RESULTS = os.path.join(os.path.dirname(__file__), "r86-gate-results")

# Pre-registered 90% intervals (research/tanjiro-r86-base-gate-prereg.md).
PREREG = {
    "decode_us_per_step": (200.0, 30.0, 450.0),
    "prefill_us_per_token": (5.0, -55.0, 65.0),
}
T_CRIT = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447}


def load():
    arms = {"old": [], "new": []}
    for path in sorted(glob.glob(os.path.join(RESULTS, "*.json"))):
        arm = os.path.basename(path).split("-")[0]
        if arm not in arms:
            continue
        m = json.load(open(path))["metrics"]
        arms[arm].append(
            {
                "file": os.path.basename(path),
                "decode_us": m["decode_seconds_per_token"] * 1e6,
                "prefill_us": m["prefill_seconds_per_token"] * 1e6,
                "correct": m["passed_correctness"],
                "steps": m["checked_steps"],
                "golden": m["golden_hash"],
                "harness": m["harness_hash"],
            }
        )
    return arms


def welch(a, b):
    """Two-sample interval on mean(a) - mean(b) with pooled SD."""
    na, nb = len(a), len(b)
    ma, mb = st.mean(a), st.mean(b)
    if na < 2 or nb < 2:
        return ma - mb, None, None, None
    va, vb = st.variance(a), st.variance(b)
    dof = na + nb - 2
    pooled = (((na - 1) * va + (nb - 1) * vb) / dof) ** 0.5
    se = pooled * (1 / na + 1 / nb) ** 0.5
    t = T_CRIT.get(dof, 2.0)
    return ma - mb, pooled, t * se, dof


def report(name, key, arms):
    old = [r[key] for r in arms["old"]]
    new = [r[key] for r in arms["new"]]
    print(f"\n--- {name} (n_old={len(old)} n_new={len(new)}) ---")
    print(f"  old   mean={st.mean(old):10.1f}  " + " ".join(f"{v:.1f}" for v in old))
    print(f"  new   mean={st.mean(new):10.1f}  " + " ".join(f"{v:.1f}" for v in new))
    delta, pooled, half, dof = welch(old, new)
    if half is None:
        print(f"  delta(old-new) = {delta:+.1f}  (n too small for an interval)")
        return
    lo, hi = delta - half, delta + half
    print(f"  pooled SD={pooled:.1f}  dof={dof}  resolution=+/-{half:.1f}")
    print(f"  delta(old-new) = {delta:+.1f}  95% CI [{lo:+.1f}, {hi:+.1f}]")
    print(f"  significant   = {'YES' if lo > 0 or hi < 0 else 'NO (interval spans 0)'}")
    point, plo, phi = PREREG[
        "decode_us_per_step" if key == "decode_us" else "prefill_us_per_token"
    ]
    inside = plo <= delta <= phi
    print(f"  pre-registered: {point:+.1f} 90% [{plo:+.1f}, {phi:+.1f}] -> "
          f"observed point {'INSIDE' if inside else 'OUTSIDE'} prereg interval")


def main():
    arms = load()
    rows = arms["old"] + arms["new"]
    if not rows:
        print("no result JSONs found")
        return 1

    print("=== correctness invariants ===")
    goldens = {r["golden"] for r in rows}
    harness = {r["harness"] for r in rows}
    steps = {r["steps"] for r in rows}
    allcorrect = all(r["correct"] for r in rows)
    for r in rows:
        print(f"  {r['file']:<14} correct={r['correct']} steps={r['steps']} "
              f"golden={r['golden'][:12]} decode_us={r['decode_us']:.1f}")
    print(f"  distinct golden hashes = {len(goldens)} -> "
          f"{'IDENTICAL' if len(goldens) == 1 else 'DIVERGENT'}")
    print(f"  distinct harness hashes = {len(harness)}")
    print(f"  checked_steps set = {steps}")
    print(f"  all arms passed_correctness = {allcorrect}")
    print(f"  MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT = "
          f"{os.environ.get('MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT', '<unset>')}")

    report("decode us/step", "decode_us", arms)
    report("prefill us/token", "prefill_us", arms)

    print()
    ok = allcorrect and len(goldens) == 1
    print(f"GATE_CORRECTNESS={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
