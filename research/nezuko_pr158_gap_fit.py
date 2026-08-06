"""Fit the decode host gap against command-buffer count, dispatch count and GPU busy time.

Inputs are the per-steady-step profile rows from
research/nezuko-pr158-split-sweep.log and research/nezuko-pr158-unfuse-sweep.log.
The SPLIT=1 arm is excluded: at 406 command buffers per step the host is the
critical path and the per-buffer cost is unamortized, so it is a different regime.
"""

# label, cbs, dispatches, gpu_busy_sum (ms), gap (ms)
ROWS = [
    ("split0", 45, 406, 8.013, 0.265),
    ("split0'", 45, 406, 8.041, 0.263),
    ("split8", 53, 406, 7.934, 0.230),
    ("split4", 103, 406, 7.937, 0.269),
    ("split2", 204, 406, 8.058, 0.287),
    ("base", 45, 406, 8.001, 0.273),
    ("base2", 45, 406, 8.004, 0.273),
    ("rrr", 45, 445, 8.262, 0.275),
    ("rsdr", 46, 445, 8.074, 0.222),
    ("ssq", 46, 601, 8.374, 0.265),
    ("rsq", 45, 601, 8.474, 0.281),
]

NAMES = ["cbs", "disp", "busy"]


def ols(x_rows, y):
    n, p = len(y), len(x_rows[0])
    a = [[sum(x_rows[i][r] * x_rows[i][c] for i in range(n)) for c in range(p)] for r in range(p)]
    b = [sum(x_rows[i][r] * y[i] for i in range(n)) for r in range(p)]
    m = [a[i][:] + [b[i]] for i in range(p)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(p):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, p + 1):
                    m[r][k] -= f * m[c][k]
    coef = [m[i][p] / m[i][i] for i in range(p)]
    pred = [sum(coef[c] * x_rows[i][c] for c in range(p)) for i in range(n)]
    ybar = sum(y) / n
    ss_res = sum((y[i] - pred[i]) ** 2 for i in range(n))
    ss_tot = sum((v - ybar) ** 2 for v in y)
    return coef, 1 - ss_res / ss_tot, (ss_res / (n - p)) ** 0.5


def main():
    y = [r[4] for r in ROWS]
    print(f"n={len(ROWS)}  gap mean={sum(y)/len(y)*1000:.1f} us  "
          f"busy range={min(r[3] for r in ROWS):.3f}-{max(r[3] for r in ROWS):.3f} ms")
    for cols in ([0], [1], [2], [0, 1], [0, 2], [0, 1, 2]):
        x_rows = [[1.0] + [r[1 + c] for c in cols] for r in ROWS]
        coef, r2, rmse = ols(x_rows, y)
        label = "1+" + "+".join(NAMES[c] for c in cols)
        terms = "  ".join(
            f"{n}={v:+.6f}" for n, v in zip(["int"] + [NAMES[c] for c in cols], coef)
        )
        print(f"{label:20s} R2={r2:6.3f} rmse={rmse*1000:5.1f}us  {terms}")


if __name__ == "__main__":
    main()
