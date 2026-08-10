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
import sys

# Rule 105 / CURRENT_RESEARCH_STATE.md:2441 -- campaign price is an M5 constant.
M5_PRICE = 0.015228  # %cs per M5 us/step
K_ISSUE_UPPER = 0.654  # census bound, tanjiro r107g:762-763
K_BETA = 0.5  # Rule 105.2 fallback upper bound for an ISSUE-bound family
BRIEF_PRICE = 0.01642  # constant asserted by the r109-e brief; unsourced
BLOCK = 6  # palindromic ABBA block length used by the driver script


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


def regression(rows, arms):
    """decode ~ intercept + linear drift + one dummy per probe arm."""
    n = len(rows)
    design = []
    for i, (arm, _, _, _) in enumerate(rows):
        row = [1.0, (i - (n - 1) / 2) / max(n - 1, 1)]
        row += [1.0 if arm == a else 0.0 for a in arms]
        design.append(row)
    y = [r[1] for r in rows]
    p = len(design[0])
    xtx = [
        [sum(design[i][a] * design[i][b] for i in range(n)) for b in range(p)]
        for a in range(p)
    ]
    xty = [sum(design[i][a] * y[i] for i in range(n)) for a in range(p)]
    beta, inv = solve(xtx, xty)
    resid = [y[i] - sum(beta[a] * design[i][a] for a in range(p)) for i in range(n)]
    sigma2 = sum(r * r for r in resid) / (n - p)
    return {
        a: (beta[2 + j], math.sqrt(sigma2 * inv[2 + j][2 + j]))
        for j, a in enumerate(arms)
    }


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


def report_delta(label, delta, se):
    print(
        f"  {label:28s} {delta:+8.2f} us/step  se {se:6.2f}  "
        f"95% CI [{delta - 1.96 * se:+8.2f}, {delta + 1.96 * se:+8.2f}]"
    )


def price(saving, ctrl_mean, tag):
    host_price = 0.75 * 100.0 / ctrl_mean
    print(f"    {tag}")
    for label, pr in (
        (f"host-matched    ({host_price:.6f})", host_price),
        (f"Rule 105.2 beta ({K_BETA * M5_PRICE:.6f})", K_BETA * M5_PRICE),
        (f"k_issue upper   ({K_ISSUE_UPPER * M5_PRICE:.6f})", K_ISSUE_UPPER * M5_PRICE),
        (f"brief constant  ({BRIEF_PRICE:.5f})", BRIEF_PRICE),
    ):
        print(f"      {label:36s} {saving * pr:+.4f} %cs")


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

    ctrl = [d for a, d, _, _ in rows if a == "C"]
    cm, csd, cn = stats(ctrl)
    probes = [a for a in arms if a != "C"]
    reg = regression(rows, probes) if len(rows) > len(probes) + 3 else {}

    for arm in probes:
        pv = [d for a, d, _, _ in rows if a == arm]
        pm, psd, pn = stats(pv)
        print(f"\n== arm {arm} minus control C ==")
        se = math.sqrt(csd * csd / cn + psd * psd / pn)
        report_delta("unpaired Welch", pm - cm, se)
        if arm in reg:
            report_delta("drift-adjusted OLS", reg[arm][0], reg[arm][1])
        bd = block_delta(rows, arm)
        if len(bd) > 1:
            bm, bsd, bn = stats(bd)
            report_delta(f"palindromic block (n={bn})", bm, bsd / math.sqrt(bn))
        best, bse = reg.get(arm, (pm - cm, se))
        price(-best, cm, "point ceiling (saving = -delta):")
        price(-(best - 1.96 * bse), cm, "optimistic 95% upper ceiling:")


if __name__ == "__main__":
    main()
