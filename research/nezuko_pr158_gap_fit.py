"""Fit the decode host gap against command-buffer count, dispatch count and GPU busy time.

Inputs are the per-steady-step profile rows from
research/nezuko-pr158-split-sweep.log, research/nezuko-pr158-unfuse-sweep.log and
research/nezuko-pr158-busy-range-sweep.log.
The SPLIT=1 arm is excluded: at 406 command buffers per step the host is the
critical path and the per-buffer cost is unamortized, so it is a different regime.

The last block decides §1.1: under an ABSOLUTE model d(gap)/d(busy) = 0; under a
PROPORTIONAL model d(gap)/d(busy) = gap/busy ~= 0.033. The fitted slope and its
standard error are compared against both.
"""

import math

# label, cbs, dispatches, gpu_busy_sum (ms), gap (ms)
SPLIT = [
    ("split0", 45, 406, 8.013, 0.265),
    ("split0'", 45, 406, 8.041, 0.263),
    ("split8", 53, 406, 7.934, 0.230),
    ("split4", 103, 406, 7.937, 0.269),
    ("split2", 204, 406, 8.058, 0.287),
]
UNFUSE = [
    ("base", 45, 406, 8.001, 0.273),
    ("base2", 45, 406, 8.004, 0.273),
    ("rrr", 45, 445, 8.262, 0.275),
    ("rsdr", 46, 445, 8.074, 0.222),
    ("ssq", 46, 601, 8.374, 0.265),
    ("rsq", 45, 601, 8.474, 0.281),
]
# 2x2 busy-range sweep, ABBA order a1 b1 c1 d1 d2 c2 b2 a2.
# a = seed512 fused, b = seed32 fused, c = seed512 unfused x4, d = seed32 unfused x4.
BUSY_RANGE = [
    ("a1", 45, 406, 7.945, 0.266),
    ("b1", 45, 496, 7.920, 0.246),
    ("c1", 51, 835, 8.603, 0.257),
    ("d1", 51, 925, 8.641, 0.277),
    ("d2", 51, 925, 8.645, 0.340),
    ("c2", 51, 835, 8.606, 0.291),
    ("b2", 45, 496, 7.939, 0.226),
    ("a2", 45, 406, 7.917, 0.227),
]
ROWS = SPLIT + UNFUSE + BUSY_RANGE

NAMES = ["cbs", "disp", "busy"]


def ols(x_rows, y):
    """Return (coef, R2, rmse, stderr) for a design already carrying its intercept."""
    n, p = len(y), len(x_rows[0])
    a = [[sum(x_rows[i][r] * x_rows[i][c] for i in range(n)) for c in range(p)] for r in range(p)]
    b = [sum(x_rows[i][r] * y[i] for i in range(n)) for r in range(p)]
    m = [a[i][:] + [b[i]] + [1.0 if j == i else 0.0 for j in range(p)] for i in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        d = m[c][c]
        for k in range(2 * p + 1):
            m[c][k] /= d
        for r in range(p):
            if r != c:
                f = m[r][c]
                for k in range(2 * p + 1):
                    m[r][k] -= f * m[c][k]
    coef = [m[i][p] for i in range(p)]
    inv = [[m[i][p + 1 + j] for j in range(p)] for i in range(p)]
    pred = [sum(coef[c] * x_rows[i][c] for c in range(p)) for i in range(n)]
    ybar = sum(y) / n
    ss_res = sum((y[i] - pred[i]) ** 2 for i in range(n))
    ss_tot = sum((v - ybar) ** 2 for v in y)
    sigma2 = ss_res / (n - p)
    stderr = [math.sqrt(sigma2 * inv[i][i]) for i in range(p)]
    return coef, 1 - ss_res / ss_tot, math.sqrt(sigma2), stderr


def replicate_noise():
    """Half-range of gap between the two replicates of each ABBA configuration."""
    by = {r[0]: r for r in BUSY_RANGE}
    return [(n, abs(by[n + "1"][4] - by[n + "2"][4]) / 2 * 1000) for n in "abcd"]


def main():
    y = [r[4] for r in ROWS]
    print(f"n={len(ROWS)}  gap mean={sum(y)/len(y)*1000:.1f} us  "
          f"busy range={min(r[3] for r in ROWS):.3f}-{max(r[3] for r in ROWS):.3f} ms "
          f"({(max(r[3] for r in ROWS)/min(r[3] for r in ROWS)-1)*100:.1f}%)  "
          f"disp range={min(r[2] for r in ROWS)}-{max(r[2] for r in ROWS)}  "
          f"cbs range={min(r[1] for r in ROWS)}-{max(r[1] for r in ROWS)}")

    print("\n-- replicate noise (half-range of the two ABBA replicates) --")
    noise = replicate_noise()
    for name, h in noise:
        print(f"  config {name}: +/-{h:5.1f} us")
    print(f"  mean half-range: +/-{sum(h for _, h in noise)/len(noise):.1f} us")

    print("\n-- 2x2 contrasts (means of the two replicates) --")
    by = {r[0]: r for r in BUSY_RANGE}
    cell = {}
    for name in "abcd":
        r1, r2 = by[name + "1"], by[name + "2"]
        cell[name] = ((r1[1] + r2[1]) / 2, (r1[2] + r2[2]) / 2,
                      (r1[3] + r2[3]) / 2, (r1[4] + r2[4]) / 2)
    for name in "abcd":
        c = cell[name]
        print(f"  {name}: cbs={c[0]:5.1f} disp={c[1]:6.1f} busy={c[2]:.3f} ms gap={c[3]*1000:6.1f} us")
    for label, hi, lo in (("seed512->32 fused   (dispatch-only lever)", "b", "a"),
                          ("seed512->32 unfused (dispatch-only lever)", "d", "c"),
                          ("fused->unfused x4   (busy lever)         ", "c", "a")):
        h, l = cell[hi], cell[lo]
        print(f"  {label}: d_busy={(h[2]-l[2])*1000:+7.1f} us  "
              f"d_disp={h[1]-l[1]:+6.0f}  d_cbs={h[0]-l[0]:+4.0f}  "
              f"d_gap={(h[3]-l[3])*1000:+6.1f} us")

    print("\n-- OLS on all rows --")
    for cols in ([0], [1], [2], [0, 1], [0, 2], [0, 1, 2]):
        x_rows = [[1.0] + [r[1 + c] for c in cols] for r in ROWS]
        coef, r2, rmse, se = ols(x_rows, y)
        label = "1+" + "+".join(NAMES[c] for c in cols)
        terms = "  ".join(
            f"{n}={v:+.6f}+/-{s:.6f}"
            for n, v, s in zip(["int"] + [NAMES[c] for c in cols], coef, se)
        )
        print(f"{label:22s} R2={r2:6.3f} rmse={rmse*1000:5.1f}us  {terms}")

    print("\n-- absolute vs proportional --")
    prop_slope = sum(y) / sum(r[3] for r in ROWS)
    for cols, tag in (([2], "gap ~ 1 + busy             "),
                      ([0, 1, 2], "gap ~ 1 + cbs + disp + busy")):
        x_rows = [[1.0] + [r[1 + c] for c in cols] for r in ROWS]
        coef, _, _, se = ols(x_rows, y)
        slope, sd = coef[-1], se[-1]
        print(f"  {tag}: d(gap)/d(busy) = {slope:+.4f} +/- {sd:.4f}")
        print(f"    ABSOLUTE     predicts 0.0000 -> {abs(slope) / sd:.2f} sigma away")
        print(f"    PROPORTIONAL predicts {prop_slope:.4f} -> {abs(slope - prop_slope) / sd:.2f} sigma away")
        lo, hi = slope - 1.96 * sd, slope + 1.96 * sd
        print(f"    95% CI [{lo:+.4f}, {hi:+.4f}]  "
              f"(absolute {'inside' if lo <= 0 <= hi else 'EXCLUDED'}, "
              f"proportional {'inside' if lo <= prop_slope <= hi else 'EXCLUDED'})")

    print("\n-- what the two models imply for a 10% cut in gpu_busy --")
    base_busy, base_gap = 7.93, 0.2465
    wall = base_busy + base_gap
    abs_wall = base_busy * 0.9 + base_gap
    prop_wall = wall * 0.9
    print(f"  base wall {wall*1000:.0f} us -> absolute {abs_wall*1000:.0f} us "
          f"({(wall/abs_wall-1)*100:.2f}% speedup), proportional {prop_wall*1000:.0f} us "
          f"({(wall/prop_wall-1)*100:.2f}% speedup)")
    print(f"  the two models differ by {(abs_wall/prop_wall-1)*100:.2f}% of wall; "
          f"the entire question is bounded by gap/wall = {base_gap/wall*100:.2f}%")


if __name__ == "__main__":
    main()
