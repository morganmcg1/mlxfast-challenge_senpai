"""Paired analysis for the R109-E full-attention QK ceiling probe.

Reads one or more ABBA TSVs produced by
`research/maple-alphonse-r109e-qk-ceiling-abba.sh` and reports the arm means,
the unpaired Welch delta, and the adjacent-pair delta with a normal-approx CI.

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


def load(paths):
    rows = []
    for path in paths:
        with open(path) as handle:
            next(handle)
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5 or parts[2] in ("NA", ""):
                    continue
                rows.append((parts[1], float(parts[2]) * 1e6, float(parts[3]) * 1e6))
    return rows


def stats(values):
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0, n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var), n


def main():
    rows = load(sys.argv[1:])
    ctrl = [d for arm, d, _ in rows if arm == "C"]
    probe = [d for arm, d, _ in rows if arm == "P"]
    cm, cs_, cn = stats(ctrl)
    pm, ps, pn = stats(probe)
    print(f"order      : {''.join(arm for arm, _, _ in rows)}")
    print(f"control  C : mean {cm:9.2f} us/step  sd {cs_:6.2f}  n {cn}")
    print(f"probe    P : mean {pm:9.2f} us/step  sd {ps:6.2f}  n {pn}")

    delta = pm - cm
    se = math.sqrt(cs_ * cs_ / cn + ps * ps / pn) if cn > 1 and pn > 1 else float("nan")
    print(f"\nunpaired delta (P - C): {delta:+.2f} us/step  se {se:.2f}")
    print(f"  95% CI [{delta - 1.96 * se:+.2f}, {delta + 1.96 * se:+.2f}]")

    pairs = []
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if a[0] != b[0]:
            pairs.append(b[1] - a[1] if b[0] == "P" else a[1] - b[1])
    if pairs:
        dm, ds, dn = stats(pairs)
        dse = ds / math.sqrt(dn) if dn > 1 else float("nan")
        print(f"\nadjacent-pair delta (P - C): {dm:+.2f} us/step  sd {ds:.2f}  n {dn}")
        print(f"  95% CI [{dm - 1.96 * dse:+.2f}, {dm + 1.96 * dse:+.2f}]")

    print("\n-- ceiling pricing (saving = -delta, positive means probe is faster) --")
    saving = -delta
    hi = -(delta - 1.96 * se) if se == se else float("nan")
    host_price = 0.75 * 100.0 / cm  # %cs per local us/step under 1:1 relative transfer
    for label, price in (
        (f"host-matched  ({host_price:.6f} %cs/us)", host_price),
        (f"Rule 105.2 beta ({K_BETA * M5_PRICE:.6f} %cs/us)", K_BETA * M5_PRICE),
        (f"k_issue upper ({K_ISSUE_UPPER * M5_PRICE:.6f} %cs/us)", K_ISSUE_UPPER * M5_PRICE),
        (f"brief constant ({BRIEF_PRICE:.5f} %cs/us)", BRIEF_PRICE),
    ):
        print(f"  {label:38s} point {saving * price:+.4f} %cs   upper {hi * price:+.4f} %cs")


if __name__ == "__main__":
    main()
