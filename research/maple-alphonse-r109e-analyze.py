"""Paired analysis for the R109-E full-attention QK ceiling probe.

Reads one or more ABBA TSVs produced by
`research/maple-alphonse-r109e-qk-ceiling-abba.sh` and reports, for every probe
arm against control C, an unpaired Welch delta, a drift-adjusted regression
delta, and a palindromic-block delta.

Pricing is deliberately reported in several units because the campaign's
`%cs per M4 us/step` constant is host-calibrated (Rule 105). See
research/maple-alphonse-r109e-qk-ceiling.md for the discussion.
"""

import math
import os
import random
import sys

# Rule 105 / CURRENT_RESEARCH_STATE.md:2441 -- campaign price is an M5 constant.
M5_PRICE = 0.015228  # %score per M5 us/step
K_ALPHA = 0.4369  # in-kernel busy transfer, CURRENT_RESEARCH_STATE.md:6512
K_ISSUE_UPPER = 0.654  # census bound, tanjiro r107g:762-763
K_BETA = 0.5  # Rule 105.2 fallback upper bound for an ISSUE-bound family
BUSY_TO_WALL = 0.8  # conservative planning transfer; measured 0.93 CI spans 0
# Dispatch-family constant (k_dispatch = 1.0785, r108p:81). Valid only for
# removed chained host encode, NOT for in-kernel busy. Printed for contrast.
BRIEF_PRICE = 0.01642
BLOCK = 8  # palindromic ABBA block length used by the driver script

# Issue slots added per QK reduction site, relative to the shipped kernel.
# One dose repetition is 1 fmul + 5 shuffles + 5 adds; the shipped simd_sum
# ladder that arm P deletes is worth about ten.
SLOTS = {"C": 0.0, "P": -10.0, "D": 11.0, "X": 110.0}
LADDER_SLOTS = 10.0


def load(paths):
    rows = []
    for path in paths:
        with open(path) as handle:
            next(handle)
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5 or parts[2] in ("NA", ""):
                    continue
                rows.append(
                    (parts[1], float(parts[2]) * 1e6, float(parts[3]) * 1e6, parts[4])
                )
    return rows


def stats(values):
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), 0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var), n


def solve(matrix, rhs):
    """Gauss-Jordan with partial pivoting; returns the solution and inv(A)."""
    n = len(matrix)
    aug = [
        row[:] + [1.0 if i == j else 0.0 for j in range(n)] + [rhs[i]]
        for i, row in enumerate(matrix)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pv = aug[col][col]
        aug[col] = [v / pv for v in aug[col]]
        for r in range(n):
            if r != col and aug[r][col]:
                f = aug[r][col]
                aug[r] = [v - f * w for v, w in zip(aug[r], aug[col])]
    return [row[-1] for row in aug], [row[n:2 * n] for row in aug]


def regression(rows, arms, lead=False):
    """decode ~ intercept + linear drift [+ block-lead spike] + arm dummies.

    The lead term is only identifiable once at least one block runs a swapped
    arm order; in a single repeated palindrome it is collinear with the arm
    that owns slot 1 and the fit silently attributes the spike to that arm.
    """
    n = len(rows)
    design = []
    for i, (arm, _, _, _) in enumerate(rows):
        row = [1.0, (i - (n - 1) / 2) / max(n - 1, 1)]
        if lead:
            row.append(1.0 if i % BLOCK == 0 else 0.0)
        row += [1.0 if arm == a else 0.0 for a in arms]
        design.append(row)
    y = [r[1] for r in rows]
    p = len(design[0])
    base = 3 if lead else 2
    xtx = [
        [sum(design[i][a] * design[i][b] for i in range(n)) for b in range(p)]
        for a in range(p)
    ]
    xty = [sum(design[i][a] * y[i] for i in range(n)) for a in range(p)]
    beta, inv = solve(xtx, xty)
    resid = [y[i] - sum(beta[a] * design[i][a] for a in range(p)) for i in range(n)]
    sigma2 = sum(r * r for r in resid) / (n - p)
    out = {
        a: (beta[base + j], math.sqrt(sigma2 * inv[base + j][base + j]))
        for j, a in enumerate(arms)
    }
    if lead:
        out["__lead__"] = (beta[2], math.sqrt(sigma2 * inv[2][2]))
    return out


def block_delta(rows, arm):
    """Palindromic blocks make each block mean drift-free to first order."""
    deltas = []
    for start in range(0, len(rows) - BLOCK + 1, BLOCK):
        chunk = rows[start:start + BLOCK]
        c = [d for a, d, _, _ in chunk if a == "C"]
        p = [d for a, d, _, _ in chunk if a == arm]
        if c and p:
            deltas.append(sum(p) / len(p) - sum(c) / len(c))
    return deltas


def hodges_lehmann(probe, ctrl):
    """Median of all pairwise differences; unaffected by a single outlier."""
    diffs = sorted(p - c for p in probe for c in ctrl)
    k = len(diffs)
    return (diffs[k // 2] if k % 2 else 0.5 * (diffs[k // 2 - 1] + diffs[k // 2]))


def hl_interval(probe, ctrl, draws=4000, seed=17):
    rng = random.Random(seed)
    shifts = []
    for _ in range(draws):
        p = [rng.choice(probe) for _ in probe]
        c = [rng.choice(ctrl) for _ in ctrl]
        shifts.append(hodges_lehmann(p, c))
    shifts.sort()
    return shifts[int(0.025 * draws)], shifts[int(0.975 * draws)]


def report_delta(label, delta, se):
    print(
        f"  {label:28s} {delta:+8.2f} us/step  se {se:6.2f}  "
        f"95% CI [{delta - 1.96 * se:+8.2f}, {delta + 1.96 * se:+8.2f}]"
    )


def price(saving, ctrl_mean, tag):
    host_price = 0.75 * 100.0 * BUSY_TO_WALL / ctrl_mean
    print(f"    {tag}")
    print(f"      vs advisor stop bar 30.0 us/step  ->  {saving / 30.0:.2f}x bar")
    for label, pr in (
        (f"A: in-kernel busy k=a  ({K_ALPHA * M5_PRICE:.6f})", K_ALPHA * M5_PRICE),
        (f"A upper: k=beta        ({K_BETA * M5_PRICE:.6f})", K_BETA * M5_PRICE),
        (f"k_issue hard upper     ({K_ISSUE_UPPER * M5_PRICE:.6f})", K_ISSUE_UPPER * M5_PRICE),
        (f"host-matched this box  ({host_price:.6f})", host_price),
    ):
        print(f"      {label:40s} {saving * pr:+.4f} %score")
    print(
        f"      [not applicable: dispatch-family {BRIEF_PRICE:.5f} would give "
        f"{saving * BRIEF_PRICE:+.4f} %score -- see memo 5.3]"
    )


def main():
    rows = load(sys.argv[1:])
    print(f"order      : {''.join(a for a, _, _, _ in rows)}  (n={len(rows)})")
    arms = sorted({a for a, _, _, _ in rows})
    for arm in arms:
        vals = [d for a, d, _, _ in rows if a == arm]
        passes = {p for a, _, _, p in rows if a == arm}
        m, sd, n = stats(vals)
        print(
            f"  arm {arm} : mean {m:9.2f} us/step  sd {sd:6.2f}  n {n}  "
            f"passed_correctness={'/'.join(sorted(passes))}"
        )

    control = os.environ.get("CTRL", "C")

    # Negative control.  The probed kernel is dispatched only for single-token
    # decode queries, so no arm can reach prefill.  A systematic prefill shift
    # would mean a global thermal / DVFS / host confound is contaminating every
    # decode delta, and the decode numbers below could not be trusted.
    print("\n== prefill negative control (must be arm-independent) ==")
    pref_ctrl = [p for a, _, p, _ in rows if a == control]
    pcm, pcsd, pcn = stats(pref_ctrl)
    for arm in arms:
        pv = [p for a, _, p, _ in rows if a == arm]
        m, sd, n = stats(pv)
        if arm == control:
            print(f"  arm {arm} : mean {m:9.2f} us/token  sd {sd:6.2f}  n {n}")
        else:
            se = math.sqrt(pcsd * pcsd / pcn + sd * sd / n)
            t = (m - pcm) / se if se > 0 else float("nan")
            print(
                f"  arm {arm} : mean {m:9.2f} us/token  sd {sd:6.2f}  n {n}  "
                f"delta {m - pcm:+7.2f}  se {se:5.2f}  t {t:+5.2f}"
            )

    # In a fixed palindromic order every arm occupies one mirrored position
    # pair, so arm is perfectly collinear with position-in-block and no
    # regression can separate them.  Print the position means so the size of
    # the confound is visible, and repeat every contrast with the first run of
    # each block dropped.
    print("\n== position-in-block diagnostic (arm is confounded with slot) ==")
    by_pos = {}
    for i, (a, d, _, _) in enumerate(rows):
        by_pos.setdefault((a, i % BLOCK + 1), []).append(d)
    for (a, pos) in sorted(by_pos):
        m, sd, n = stats(by_pos[(a, pos)])
        print(f"  arm {a} pos {pos} : mean {m:9.2f} us/step  sd {sd:6.2f}  n {n}")
    trimmed = [r for i, r in enumerate(rows) if i % BLOCK != 0]

    ctrl = [d for a, d, _, _ in rows if a == control]
    cm, csd, cn = stats(ctrl)
    probes = [a for a in arms if a != control]
    reg = regression(rows, probes) if len(rows) > len(probes) + 3 else {}

    lead_arms = {a for i, (a, _, _, _) in enumerate(rows) if i % BLOCK == 0}
    reg_lead = {}
    if len(lead_arms) > 1 and len(rows) > len(probes) + 4:
        reg_lead = regression(rows, probes, lead=True)
        spike, sspike = reg_lead["__lead__"]
        print("\n== block-lead spike is identified (slot 1 held by "
              f"{'/'.join(sorted(lead_arms))}) ==")
        print(f"  slot-1 penalty {spike:+8.2f} us/step  se {sspike:6.2f}"
              f"  95% CI [{spike - 1.96 * sspike:+8.2f},"
              f" {spike + 1.96 * sspike:+8.2f}]")

    for arm in probes:
        pv = [d for a, d, _, _ in rows if a == arm]
        pm, psd, pn = stats(pv)
        print(f"\n== arm {arm} minus control {control} ==")
        se = math.sqrt(csd * csd / cn + psd * psd / pn)
        report_delta("unpaired Welch", pm - cm, se)
        if arm in reg:
            report_delta("drift-adjusted OLS", reg[arm][0], reg[arm][1])
        bd = block_delta(rows, arm)
        if len(bd) > 1:
            bm, bsd, bn = stats(bd)
            report_delta(f"palindromic block (n={bn})", bm, bsd / math.sqrt(bn))
        hl = hodges_lehmann(pv, ctrl)
        lo, hi_hl = hl_interval(pv, ctrl)
        print(
            f"  {'Hodges-Lehmann (robust)':28s} {hl:+8.2f} us/step"
            f"          boot 95% CI [{lo:+8.2f}, {hi_hl:+8.2f}]"
        )
        tc = [d for a, d, _, _ in trimmed if a == control]
        tp = [d for a, d, _, _ in trimmed if a == arm]
        if tc and tp:
            tcm, tcsd, tcn = stats(tc)
            tpm, tpsd, tpn = stats(tp)
            tse = math.sqrt(
                (tcsd * tcsd / tcn if tcn > 1 else 0.0)
                + (tpsd * tpsd / tpn if tpn > 1 else 0.0)
            )
            report_delta("no block-lead run (pos>1)", tpm - tcm, tse)
        if arm in reg_lead:
            report_delta("lead-adjusted OLS", *reg_lead[arm])
        best, bse = reg_lead.get(arm, reg.get(arm, (pm - cm, se)))
        price(-best, cm, "point ceiling (saving = -delta):")
        price(-(best - 1.96 * bse), cm, "optimistic 95% upper ceiling:")

    src = reg_lead or reg
    dose = {a: src[a] for a in ("D", "X") if a in src}
    if len(dose) == 2:
        slope = (dose["X"][0] - dose["D"][0]) / (SLOTS["X"] - SLOTS["D"])
        sse = math.sqrt(dose["X"][1] ** 2 + dose["D"][1] ** 2) / (
            SLOTS["X"] - SLOTS["D"]
        )
        print("\n== dose-response (bit-exact arms only) ==")
        print(
            f"  marginal cost {slope * 1000:+8.3f} ns/step per added issue slot"
            f"  (se {sse * 1000:.3f})"
        )
        # Two-parameter fit: a fixed cost F charged once at any dose > 0 plus a
        # marginal slope.  A latency-slack model is convex (per-slot cost rises
        # with dose); F > 0 means the curve is concave, which slack cannot
        # produce, and which disqualifies "issue slots" as a linear ruler.
        step_cost = dose["D"][0] - slope * SLOTS["D"]
        first = dose["D"][0] / SLOTS["D"]
        gap = SLOTS["X"] - SLOTS["D"]
        w_d = 1.0 + SLOTS["D"] / gap
        w_x = SLOTS["D"] / gap
        step_se = math.sqrt((w_d * dose["D"][1]) ** 2 + (w_x * dose["X"][1]) ** 2)
        print(
            f"  first-dose cost {first * 1000:+8.3f} ns/step per slot -> "
            f"fixed step cost {step_cost:+.2f} us/step at any dose > 0 "
            f"(se {step_se:.2f})"
        )
        if abs(step_cost) < 1.96 * step_se:
            print(
                "  curve is LINEAR within noise (fixed step cost not "
                "distinguishable from zero): the slot ruler is usable"
            )
        elif first > slope:
            print(
                "  curve is CONCAVE (first > marginal): a fixed per-step cost "
                "or clock response, not latency slack"
            )
        else:
            print(
                "  curve is CONVEX (first < marginal): consistent with "
                "saturating latency slack"
            )
        ladder = slope * LADDER_SLOTS
        hi = (slope + 1.96 * sse) * LADDER_SLOTS
        print(
            f"  implied ceiling for deleting the whole ladder: "
            f"{ladder:+.2f} us/step (95% upper {hi:+.2f})"
        )
        price(ladder, cm, "dose-response point ceiling:")
        price(hi, cm, "dose-response 95% upper ceiling:")


if __name__ == "__main__":
    main()
