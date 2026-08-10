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


KNEE_K = 480          # R93 knee-results.md: M4 free region ends between 480 and 800
RULE57 = 1.2382       # M4 saturated hazard-free addition price, µs/dispatch
RULE57_CI = (1.2237, 1.2518)
RULE65 = 2.3403       # M5 hazard-free addition price, µs/dispatch
RULE65_CI = (2.2766, 2.4040)
K_DISPATCH = 1.890    # RULE65 / RULE57
K_RESIDUE = 1.4998    # tanjiro r107-G memory-residue host multiplier
# R93 knee-results.md tail segments, i.e. the M4 addition price measured where
# the free region is exhausted: 1200->1600 = 1.98, 1600->2400 = 2.36 µs/dispatch.
# RULE57's 1.2382 is close to that curve's 0->2400 chord (1.300), not its tail.
M4_SATURATED_ADDITION = 2.17
M4_SATURATED_ADDITION_RANGE = (1.98, 2.36)
R93_CHORD_0_2400 = 1.300


def derive(out: dict) -> dict:
    """Turn the two measured prices into the ratios rule 65 is quoted against."""
    mp = out["matched_pair_d4_e276"]
    fit = out["removal_fit"]
    if not mp.get("available"):
        return {"available": False}
    # Prefer the multi-rung slope; the d4/d0 matched pair is the fallback when
    # only two rungs of the removal ladder exist.
    removal = fit.get("slope") or mp["removal_price_us_per_dispatch"]
    addition_op = mp["addition_price_us_per_dispatch"]
    d = {
        "removal_price_used": removal,
        "removal_price_source": "slope" if fit.get("slope") else "matched_pair",
        "removal_price_us_per_dispatch_matched": mp["removal_price_us_per_dispatch"],
        "removal_price_us_per_dispatch_slope": fit.get("slope"),
        "removal_price_ci_slope": fit.get("ci"),
        "addition_price_operating_point": addition_op,
        "ratio_removal_over_addition_operating_point":
            removal / addition_op if abs(addition_op) > 1e-9 else None,
        "ratio_removal_over_rule57_saturated_M4": removal / RULE57,
        # The regime-matched comparison: both sides are same-host prices measured
        # where the machine has no idle slack left to absorb a dispatch.
        "ratio_removal_over_M4_saturated_addition": removal / M4_SATURATED_ADDITION,
        "ratio_removal_over_M4_saturated_addition_range":
            [removal / M4_SATURATED_ADDITION_RANGE[1],
             removal / M4_SATURATED_ADDITION_RANGE[0]],
        "ratio_removal_over_rule65_M5_addition": removal / RULE65,
        "k_dispatch_regime_matched": RULE65 / M4_SATURATED_ADDITION,
        "k_dispatch_regime_matched_range":
            [RULE65 / M4_SATURATED_ADDITION_RANGE[1],
             RULE65 / M4_SATURATED_ADDITION_RANGE[0]],
        "M5_removal_projected_at_k_dispatch": removal * K_DISPATCH,
        "M5_removal_projected_at_k_residue": removal * K_RESIDUE,
        "ratio_M5_projection_over_rule65_at_k_dispatch":
            removal * K_DISPATCH / RULE65,
        "ratio_M5_projection_over_rule65_at_k_residue":
            removal * K_RESIDUE / RULE65,
        # If the M5 is encode-limited (no free region at K=100, per R93) then a
        # removal there recovers the full encode price and rule 65 IS the M5
        # removal price, which turns the ratio into a host multiplier.
        "k_removal_if_M5_symmetric": RULE65 / removal,
        "k_removal_if_M5_symmetric_ci": None,
    }
    ci = fit.get("ci")
    if ci and ci[0] > 0:
        d["k_removal_if_M5_symmetric_ci"] = [RULE65 / ci[1], RULE65 / ci[0]]
        d["ratio_removal_over_rule57_ci"] = [ci[0] / RULE57_CI[1],
                                             ci[1] / RULE57_CI[0]]
    return d


def _ci(x) -> str:
    return "n/a" if not x else "[%.4f, %.4f]" % (x[0], x[1])


def render_md(out: dict) -> str:
    """Emit the §5 block so the report never carries a hand-copied number."""
    L = []
    A = out["arms"]
    L.append("### 5.1 Arm means (µs/step, decode)\n")
    L.append("| arm | Δn | n | mean | sd | rows |")
    L.append("|---|---|---|---|---|---|")
    for a, v in A.items():
        L.append("| `%s` | %s | %d | %.2f | %s | %s |" % (
            a, "?" if v["dn"] is None else v["dn"], v["n"], v["mean_us_per_step"],
            "—" if v["sd_us_per_step"] is None else "%.1f" % v["sd_us_per_step"],
            ", ".join("%.0f" % x for x in v["values"])))
    L.append("\nCorrectness: %s (%d runs, %d with a censused Δn).%s\n" % (
        "every run passed" if out["all_passed_correctness"] else "FAILURES PRESENT",
        out["runs"], out["runs_with_known_dn"],
        "" if out["all_passed_correctness"] else " Failed: " + ", ".join(out["failed_tags"])))

    L.append("### 5.2 Slopes (µs/step per dispatch)\n")
    L.append("| ladder | rungs | slope | 95 % CI | resid sd |")
    L.append("|---|---|---|---|---|")
    for key, label in (("removal_fit", "D — removal (de-fusion)"),
                       ("addition_fit_free_region", "E — addition, K ≤ %d (free region)" % KNEE_K),
                       ("addition_fit_past_knee", "E — addition, secant from K=%d upward (past knee)" % KNEE_K),
                       ("addition_fit_all_K", "E — addition, all K (secant, do not quote)")):
        f = out[key]
        if f.get("slope") is None:
            L.append("| %s | — | unavailable | — | — |" % label)
            continue
        L.append("| %s | %d | %.4f | %s | %s |" % (
            label, f.get("n", 0), f["slope"], _ci(f.get("ci")),
            "—" if f.get("resid_sd") is None else "%.1f" % f["resid_sd"]))

    d = out.get("derived") or {}
    if d.get("available") is False:
        L.append("\n(no matched pair yet)\n")
        return "\n".join(L) + "\n"
    L.append("\n### 5.3 Headline ratios\n")
    L.append("| quantity | value | 95 % CI |")
    L.append("|---|---|---|")
    rows = [
        ("removal price, µs/dispatch (slope)", d.get("removal_price_us_per_dispatch_slope"),
         d.get("removal_price_ci_slope")),
        ("removal price, µs/dispatch (d4/d0 matched pair)", d.get("removal_price_us_per_dispatch_matched"), None),
        ("addition price at operating point, µs/dispatch", d.get("addition_price_operating_point"), None),
        ("**ratio removal / addition(operating point)**",
         d.get("ratio_removal_over_addition_operating_point"),
         (out.get("matched_pair_d4_e276") or {}).get("ratio_ci")),
        ("**ratio removal / M4 saturated addition (%.2f, regime-matched)**" % M4_SATURATED_ADDITION,
         d.get("ratio_removal_over_M4_saturated_addition"),
         d.get("ratio_removal_over_M4_saturated_addition_range")),
        ("ratio removal / rule 65 M5 addition (%.4f)" % RULE65,
         d.get("ratio_removal_over_rule65_M5_addition"), None),
        ("ratio removal / rule 57 quoted M4 (%.4f, chord — void)" % RULE57,
         d.get("ratio_removal_over_rule57_saturated_M4"),
         d.get("ratio_removal_over_rule57_ci")),
        ("k_dispatch regime-matched = rule65 / M4 saturated addition",
         d.get("k_dispatch_regime_matched"), d.get("k_dispatch_regime_matched_range")),
        ("M5 removal projected at k_dispatch=%.3f" % K_DISPATCH,
         d.get("M5_removal_projected_at_k_dispatch"), None),
        ("M5 removal projected at k_residue=%.4f" % K_RESIDUE,
         d.get("M5_removal_projected_at_k_residue"), None),
        ("**k_removal = rule65 / M4 removal**", d.get("k_removal_if_M5_symmetric"),
         d.get("k_removal_if_M5_symmetric_ci")),
    ]
    for name, val, ci in rows:
        L.append("| %s | %s | %s |" % (
            name, "n/a" if val is None else "%.4f" % val, _ci(ci)))
    return "\n".join(L) + "\n"


REPORT = "research/maple-alphonse-r108p-dispatch-removal-symmetry.md"


def splice_report(path: Path, md: str) -> None:
    """Keep §5 of the report generated, so no number is hand-copied."""
    text = path.read_text()
    start = text.index("## 5 Results")
    end = text.index("## 6 ", start)
    head = "## 5 Results\n\nGenerated by `research/maple-alphonse-r108p-analyse.py`; do not edit by hand.\n\n"
    path.write_text(text[:start] + head + md + "\n" + text[end:])


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

    # `d0` and `e0` are the same physical arm: no toggle flipped, nothing
    # injected. Both ladders therefore share it as their zero rung.
    zero_rows = [r for r in known if r["dn"] == 0]
    d_rows = [r for r in known if r["ladder"] == "D" and r["dn"] > 0] + zero_rows
    e_rows = [r for r in known if r["ladder"] == "E" and r["dn"] > 0] + zero_rows
    # R93's knee-results.md places the M4 free region below K ~= 480-800, so a
    # single slope across it and the saturated region would only be a secant.
    e_free = [r for r in e_rows if r["dn"] <= KNEE_K]
    # Past-knee rungs are anchored on the highest free-region rung rather than on
    # zero, so the slope is a secant from the knee and not across it.
    anchor = max((r["dn"] for r in e_free), default=0)
    e_sat = [r for r in e_rows if r["dn"] > KNEE_K or r["dn"] == anchor]
    out = {
        "runs": len(rows),
        "runs_with_known_dn": len(known),
        "all_passed_correctness": all(bool(r["passed"]) for r in rows),
        "failed_tags": [r["tag"] for r in rows if not r["passed"]],
        "arms": arms,
        "removal_fit": slope_ci(d_rows, args.drift),
        "addition_fit_all_K": slope_ci(e_rows, args.drift),
        "addition_fit_free_region": slope_ci(e_free, args.drift),
        "addition_fit_past_knee": slope_ci(e_sat, args.drift),
        "ratio_bootstrap": boot_ratio(known, args.drift),
        "matched_pair_d4_e276": matched_pair(rows, "d4", "e276"),
        "matched_pair_d4_e1600": matched_pair(rows, "d4", "e1600"),
        "drift_covariate": args.drift,
    }
    out["derived"] = derive(out)
    Path(args.json).write_text(json.dumps(out, indent=2) + "\n")
    md = render_md(out)
    Path(args.json).with_name("results.md").write_text(md)
    splice_report(Path(REPORT), md)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
