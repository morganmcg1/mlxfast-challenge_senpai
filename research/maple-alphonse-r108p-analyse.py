#!/usr/bin/env python3
"""R108-P: fit the removal price and the addition price of one decode dispatch.

Ladder D turns shipped fusions off (a real merge measured in reverse) and
ladder E injects near-empty dispatches. Both ladders run the same binary in one
session on one host, so the headline removal/addition ratio is dimensionless and
independent of the M4->score pricing multiplier.

Usage: python3 research/maple-alphonse-r108p-analyse.py [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

LADDER = Path("research/artifacts/maple-alphonse-r108p/ladder")

# Additional GPU kernel dispatches per single-token decode step, relative to the
# unmodified base. Ladder E is exact by construction (one MLXFast.metalKernel
# call per injected unit). Ladder D is the audited source census in
# research/maple-alphonse-r108p-dispatch-removal-symmetry.md; DN_D_UNCERTAINTY
# carries the census uncertainty into the ratio.
DN = {
    "d0": 0,
    "e0": 0,
    "e78": 78,
    "e156": 156,
    "e198": 198,
    "e276": 276,
    "d1": None,
    "d2": None,
    "d3": None,
    "d4": None,
}
LADDER_OF = {"d": "D", "e": "E"}
RNG = np.random.default_rng(20260810)
BOOT = 20000


def load_dn_census() -> None:
    """Overlay the audited ladder-D dispatch census when it is available."""
    census = LADDER.parent / "dn-census.json"
    if census.exists():
        for arm, n in json.loads(census.read_text())["dn"].items():
            DN[arm] = int(n)


def load_rows() -> list[dict]:
    rows = []
    for path in sorted(LADDER.glob("*.row.json")):
        row = json.loads(path.read_text())
        if row.get("decode") is None:
            continue
        row["us_per_step"] = row["decode"] * 1e6
        row["ladder"] = LADDER_OF[row["arm"][0]]
        row["dn"] = DN.get(row["arm"])
        rows.append(row)
    rows.sort(key=lambda r: (r["session"], r["pos"]))
    for i, row in enumerate(rows):
        row["order"] = i  # global run order, the thermal-drift covariate
    return rows


def fit_slope(rows: list[dict], drift: bool) -> tuple[np.ndarray, np.ndarray]:
    """Design matrix and response for t = a + c_R * dn (+ d * order)."""
    cols = [np.ones(len(rows)), np.array([r["dn"] for r in rows], dtype=float)]
    if drift:
        cols.append(np.array([r["order"] for r in rows], dtype=float))
    return np.vstack(cols).T, np.array([r["us_per_step"] for r in rows])


def ols(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(x, y, rcond=None)[0]


def slope_ci(rows: list[dict], drift: bool) -> dict:
    x, y = fit_slope(rows, drift)
    if len(rows) <= x.shape[1]:
        return {"n": len(rows), "slope": None, "ci": None}
    beta = ols(x, y)
    resid = y - x @ beta
    dof = len(rows) - x.shape[1]
    sigma2 = float(resid @ resid) / dof
    cov = sigma2 * np.linalg.inv(x.T @ x)
    se = math.sqrt(cov[1, 1])
    # Student-t two sided 95 percent; table for the small dof we actually hit.
    tcrit = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}.get(dof, 2.13)
    return {
        "n": len(rows),
        "slope": float(beta[1]),
        "se": se,
        "dof": dof,
        "ci": [float(beta[1] - tcrit * se), float(beta[1] + tcrit * se)],
        "intercept": float(beta[0]),
        "drift_us_per_run": float(beta[2]) if drift else None,
        "resid_sd": math.sqrt(sigma2),
    }


def boot_ratio(rows: list[dict], drift: bool) -> dict:
    """Bootstrap the removal/addition slope ratio, resampling runs within arm."""
    by_arm: dict[str, list[dict]] = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)
    ratios, sd_, sa_ = [], [], []
    for _ in range(BOOT):
        sample = []
        for arm, group in by_arm.items():
            pick = RNG.integers(0, len(group), len(group))
            sample.extend(group[i] for i in pick)
        d = [r for r in sample if r["ladder"] == "D"]
        e = [r for r in sample if r["ladder"] == "E"]
        fd, fe = slope_ci(d, drift), slope_ci(e, drift)
        if fd["slope"] is None or fe["slope"] is None or abs(fe["slope"]) < 1e-9:
            continue
        sd_.append(fd["slope"])
        sa_.append(fe["slope"])
        ratios.append(fd["slope"] / fe["slope"])
    if not ratios:
        return {"ratio": None}
    ratios = np.array(ratios)
    return {
        "ratio_median": float(np.median(ratios)),
        "ratio_ci": [float(np.percentile(ratios, 2.5)),
                     float(np.percentile(ratios, 97.5))],
        "removal_slope_ci": [float(np.percentile(sd_, 2.5)),
                             float(np.percentile(sd_, 97.5))],
        "addition_slope_ci": [float(np.percentile(sa_, 2.5)),
                              float(np.percentile(sa_, 97.5))],
        "boot_n": len(ratios),
    }


def matched_pair(rows: list[dict], hi_d: str, hi_e: str) -> dict:
    """Direct ratio at one matched dispatch delta, no linearity assumption."""
    def arm(name):
        return np.array([r["us_per_step"] for r in rows if r["arm"] == name])

    base = np.concatenate([arm("d0"), arm("e0")])
    d, e = arm(hi_d), arm(hi_e)
    if not len(base) or not len(d) or not len(e):
        return {"available": False}
    if DN.get(hi_d) in (None, 0):
        return {"available": False, "reason": "ladder D dispatch census missing"}
    ratios = []
    for _ in range(BOOT):
        b = base[RNG.integers(0, len(base), len(base))].mean()
        dd = d[RNG.integers(0, len(d), len(d))].mean() - b
        ee = e[RNG.integers(0, len(e), len(e))].mean() - b
        if abs(ee) < 1e-9:
            continue
        ratios.append((dd / DN[hi_d]) / (ee / DN[hi_e]))
    ratios = np.array(ratios)
    return {
        "available": True,
        "baseline_us_per_step": float(base.mean()),
        "baseline_n": len(base),
        "removal_delta_us_per_step": float(d.mean() - base.mean()),
        "removal_price_us_per_dispatch": float((d.mean() - base.mean()) / DN[hi_d]),
        "addition_delta_us_per_step": float(e.mean() - base.mean()),
        "addition_price_us_per_dispatch": float((e.mean() - base.mean()) / DN[hi_e]),
        "ratio_median": float(np.median(ratios)),
        "ratio_ci": [float(np.percentile(ratios, 2.5)),
                     float(np.percentile(ratios, 97.5))],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="research/artifacts/maple-alphonse-r108p/fit.json")
    ap.add_argument("--drift", action="store_true",
                    help="include a linear global-run-order drift covariate")
    args = ap.parse_args()

    load_dn_census()
    rows = load_rows()
    known = [r for r in rows if r["dn"] is not None]

    per_arm = {}
    for r in rows:
        per_arm.setdefault(r["arm"], []).append(r["us_per_step"])
    arms = {
        a: {
            "n": len(v),
            "mean_us_per_step": float(np.mean(v)),
            "sd_us_per_step": float(np.std(v, ddof=1)) if len(v) > 1 else None,
            "dn": DN.get(a),
            "values": [round(x, 2) for x in v],
        }
        for a, v in sorted(per_arm.items())
    }

    d_rows = [r for r in known if r["ladder"] == "D"]
    e_rows = [r for r in known if r["ladder"] == "E"]
    out = {
        "runs": len(rows),
        "runs_with_known_dn": len(known),
        "all_passed_correctness": all(bool(r["passed"]) for r in rows),
        "failed_tags": [r["tag"] for r in rows if not r["passed"]],
        "arms": arms,
        "removal_fit": slope_ci(d_rows, args.drift),
        "addition_fit": slope_ci(e_rows, args.drift),
        "ratio_bootstrap": boot_ratio(known, args.drift),
        "matched_pair_d4_e276": matched_pair(rows, "d4", "e276"),
        "drift_covariate": args.drift,
    }
    Path(args.json).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
