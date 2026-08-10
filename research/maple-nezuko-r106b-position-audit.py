#!/usr/bin/env python3
"""R106-B Stage B: position-confound audit for the control-anchored paired design.

The preregistered design (Amendment 2 section 3) fixes the control at position 1
of every block of four and permutes K/H/P over positions 2, 3 and 4.  That buys
each candidate a contemporaneous control, but it buys it at a price: the control
is *never* measured at positions 2-4, so any systematic within-block drift -- the
host warming through a block, a page cache filling, anything monotone in run
order -- lands entirely on the candidates and inflates every paired difference in
the same direction.

The design does, however, make the confound measurable, because arm and position
are orthogonal *within* the candidate positions: each of K, H and P is run
exactly twice at each of positions 2, 3 and 4.  So

  * the position effect can be estimated from the 18 candidate runs alone,
    with no help from the control and no contamination by arm; and
  * an arm contrast adjusted for block and for a linear position trend can be
    fitted over all 24 runs and compared against the preregistered one.

Nothing here replaces the preregistered primary analysis.  The paired dof-5
contrast is the result of record; this script exists so the report can state
whether that result is position-inflated, and by how much.

usage: research/maple-nezuko-r106b-position-audit.py <evidence.tsv>
"""

import csv
import math
import sys

import numpy as np

US = 1e6

# Student's t, 97.5 % quantile.  scipy is not installed on this host.
T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
}


def load(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["decode_s_per_token"] in ("", "NA", None):
                continue
            rows.append({
                "idx": int(r["idx"]),
                "block": int(r["block"]),
                "arm": r["arm"],
                "kernel": r.get("kernel", ""),
                "us": float(r["decode_s_per_token"]) * US,
            })
    rows.sort(key=lambda r: r["idx"])
    # Position within the block, 1-based, from run order.
    seen = {}
    for r in rows:
        seen[r["block"]] = seen.get(r["block"], 0) + 1
        r["pos"] = seen[r["block"]]
    return rows


def paired(rows, arm):
    """Preregistered primary: candidate minus the control of its own block."""
    ctrl = {r["block"]: r["us"] for r in rows if r["arm"] == "C"}
    d = [r["us"] - ctrl[r["block"]] for r in rows
         if r["arm"] == arm and r["block"] in ctrl]
    n = len(d)
    if n < 2:
        return None
    m = float(np.mean(d))
    sd = float(np.std(d, ddof=1))
    se = sd / math.sqrt(n)
    t = T975[n - 1]
    return {"n": n, "dof": n - 1, "mean": m, "sd": sd, "se": se,
            "lo": m - t * se, "hi": m + t * se, "d": d}


def main():
    rows = load(sys.argv[1])
    arms = sorted({r["arm"] for r in rows if r["arm"] != "C"})
    ctrls = [r["us"] for r in rows if r["arm"] == "C"]

    print("=== rows: %d  (C=%d, %s)" % (
        len(rows), len(ctrls),
        ", ".join("%s=%d" % (a, sum(1 for r in rows if r["arm"] == a)) for a in arms)))

    # --- 1. control replicate scatter: the C.3 prediction test ----------------
    if len(ctrls) >= 2:
        print("\n--- control replicates (tests the C.3 fixed-term noise model) ---")
        print("C values us/step: " + " ".join("%.1f" % v for v in ctrls))
        print("C mean %.2f  sd %.2f us/step  (range %.1f)  n=%d"
              % (float(np.mean(ctrls)), float(np.std(ctrls, ddof=1)),
                 max(ctrls) - min(ctrls), len(ctrls)))
        print("C.3 predicted sd ~7.5 us/step; triage sd at N=128 was 60.0 us/step")

    # --- 2. preregistered paired contrasts -----------------------------------
    print("\n--- preregistered primary: paired vs same-block control ---")
    print("arm  n dof     delta_us      sd      95%% CI            %% of cs")
    prereg = {}
    for a in arms:
        st = paired(rows, a)
        if not st:
            continue
        prereg[a] = st
        print("%-3s %2d %3d  %+9.3f  %7.3f  [%+8.3f, %+8.3f]  %+.4f"
              % (a, st["n"], st["dof"], st["mean"], st["sd"], st["lo"], st["hi"],
                 st["mean"] * 0.015228))
        print("     per-block deltas: " + " ".join("%+.1f" % x for x in st["d"]))

    # --- 3. position effect from candidate runs only -------------------------
    print("\n--- within-block position effect, estimated from candidate runs only ---")
    print("(arm and position are orthogonal here: each arm appears twice at each"
          " of positions 2, 3, 4)")
    cand = [r for r in rows if r["arm"] != "C"]
    for p in (2, 3, 4):
        vals = [r["us"] for r in cand if r["pos"] == p]
        if vals:
            print("position %d: n=%d mean %.2f us/step  arms %s"
                  % (p, len(vals), float(np.mean(vals)),
                     "".join(sorted(r["arm"] for r in cand if r["pos"] == p))))
    # Arm-adjusted linear trend in position over the candidate rows: regress
    # us on arm dummies + (pos - 3).
    if len(cand) >= 6:
        alist = sorted({r["arm"] for r in cand})
        X = []
        y = []
        for r in cand:
            row = [1.0 if r["arm"] == a else 0.0 for a in alist]
            row.append(float(r["pos"] - 3))
            X.append(row)
            y.append(r["us"])
        X = np.array(X)
        y = np.array(y)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        dof = len(y) - np.linalg.matrix_rank(X)
        if dof > 0:
            s2 = float(resid @ resid) / dof
            cov = s2 * np.linalg.pinv(X.T @ X)
            se = math.sqrt(float(cov[-1, -1]))
            t = T975.get(dof, 1.96)
            slope = float(beta[-1])
            print("linear position slope %+.3f us/step per position"
                  " 95%% CI [%+.3f, %+.3f]  (dof %d)"
                  % (slope, slope - t * se, slope + t * se, dof))
            print("if that slope is real, a control measured at position 1 sits"
                  " %+.2f us/step below the mean candidate position (3),"
                  " i.e. every paired delta above is inflated by about that much"
                  % (-2.0 * slope))

    # --- 4. block + linear-position + arm model over all 24 runs -------------
    print("\n--- secondary, NOT preregistered: block + linear position + arm ---")
    blocks = sorted({r["block"] for r in rows})
    arml = arms  # control is the reference level
    X = []
    y = []
    for r in rows:
        row = [1.0 if r["block"] == b else 0.0 for b in blocks]
        row.append(float(r["pos"] - 1))
        row += [1.0 if r["arm"] == a else 0.0 for a in arml]
        X.append(row)
        y.append(r["us"])
    X = np.array(X)
    y = np.array(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - np.linalg.matrix_rank(X)
    if dof <= 0:
        print("skipped: %d runs cannot identify %d parameters"
              % (len(y), int(np.linalg.matrix_rank(X))))
        return
    print("residual sd %.3f us/step on %d dof" % (math.sqrt(float(resid @ resid) / dof), dof))
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(X.T @ X)
    t = T975.get(dof, 1.96)
    names = ["block%d" % b for b in blocks] + ["pos_slope"] + ["arm_" + a for a in arml]
    for i, nm in enumerate(names):
        if not (nm.startswith("arm_") or nm == "pos_slope"):
            continue
        se = math.sqrt(max(cov[i, i], 0.0))
        print("%-10s %+9.3f  95%% CI [%+8.3f, %+8.3f]"
              % (nm, beta[i], beta[i] - t * se, beta[i] + t * se))

    # --- 5. resolution actually achieved ------------------------------------
    print("\n--- achieved resolution of the preregistered design ---")
    for a, st in prereg.items():
        half = (st["hi"] - st["lo"]) / 2.0
        print("arm %s: 95%% CI half-width %.2f us/step = %.4f %% of cs;"
              " smallest effect this campaign could have called nonzero"
              % (a, half, half * 0.015228))
        need = (T975[5] * st["sd"] / 19.405) ** 2
        print("      to resolve the 19.405 us/step Stage 0 residual at this"
              " arm's own scatter would need n ~ %.1f pairs" % need)


if __name__ == "__main__":
    main()
