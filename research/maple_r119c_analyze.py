#!/usr/bin/env python3
"""Research-only (PR #714, R119-C): reduce the SPLIT=1 atlas logs to per-arm
per-kernel us/step, then fit the load-balance conversion coefficient phi.

  python3 research/maple_r119c_analyze.py research/r119c-runs/atlas
"""
import glob
import os
import re
import statistics
import sys

ARM_ROW = "swiglu_qmv_rows1_halved"
# Predicted static imbalance vs the ideal 25.6 rows on this 20-core host:
#   worst core rows = ceil(512 / rows_per_tg / 20) * rows_per_tg
PREDICTED = {64: 0.0, 128: 28 / 26 - 1, 256: 32 / 26 - 1}

ROW_RE = re.compile(
    r"^\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)\s+([0-9.]+)\s+(.+?)\s*$")


def parse_log(path):
    """Return (us_per_step_by_kernel, wall_ms, busy_ms, calls_by_kernel)."""
    rows, wall, busy, calls = {}, None, None, {}
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("per steady step:"):
                wall = float(re.search(r"wall=([0-9.]+) ms", line).group(1))
                busy = float(
                    re.search(r"gpu_busy_sum=([0-9.]+) ms", line).group(1))
                continue
            m = ROW_RE.match(line)
            if not m or line.lstrip().startswith("us/step"):
                continue
            name = m.group(5)
            if name.startswith("...") or " " in name.split("]")[-1].strip():
                continue
            rows[name] = rows.get(name, 0.0) + float(m.group(1))
            calls[name] = calls.get(name, 0.0) + float(m.group(3))
    return rows, wall, busy, calls


def summarize(values):
    n = len(values)
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    return mean, sd, (sd / n**0.5 if n > 1 else 0.0), n


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "research/r119c-runs/atlas"
    per_arm = {}
    for path in sorted(glob.glob(os.path.join(out, "p*-tg*.log"))):
        tg = int(re.search(r"-tg(\d+)\.log$", path).group(1))
        rows, wall, busy, calls = parse_log(path)
        if wall is None:
            print(f"skip (no profile block): {path}")
            continue
        per_arm.setdefault(tg, []).append(
            (os.path.basename(path), rows, wall, busy, calls))

    if not per_arm:
        print("no logs parsed")
        return 1

    arms = sorted(per_arm)
    print(f"{'arm':>6} {'n':>3} {'qmv us/step':>22} {'calls':>7} "
          f"{'wall ms':>16} {'busy ms':>16}")
    arm_qmv = {}
    for tg in arms:
        qmv, walls, busies, ncalls = [], [], [], []
        for _, rows, wall, busy, calls in per_arm[tg]:
            hit = [v for k, v in rows.items() if ARM_ROW in k]
            cal = [v for k, v in calls.items() if ARM_ROW in k]
            qmv.append(sum(hit))
            ncalls.append(sum(cal))
            walls.append(wall)
            busies.append(busy)
        m, sd, sem, n = summarize(qmv)
        wm, wsd, _, _ = summarize(walls)
        bm, bsd, _, _ = summarize(busies)
        arm_qmv[tg] = (m, sd, sem, n, qmv)
        print(f"{tg:>6} {n:>3} {m:>10.2f} +- {sd:5.2f} (sem {sem:4.2f}) "
              f"{statistics.mean(ncalls):>7.1f} "
              f"{wm:>9.3f} +- {wsd:4.3f} {bm:>9.3f} +- {bsd:4.3f}")

    base = arm_qmv[64][0]
    print("\nper-arm delta vs TG=64 (raw SPLIT=1 us/step):")
    for tg in arms:
        if tg == 64:
            continue
        m, sd, sem, n, _ = arm_qmv[tg]
        d = m - base
        dsem = (sem**2 + arm_qmv[64][2] ** 2) ** 0.5
        pred = PREDICTED[tg] * base
        phi = d / pred if pred else float("nan")
        phi_lo = (d - 1.96 * dsem) / pred if pred else float("nan")
        phi_hi = (d + 1.96 * dsem) / pred if pred else float("nan")
        print(f"  TG={tg:<4} delta={d:+8.2f} +- {dsem:.2f} us/step "
              f"({d / base * 100:+6.2f}%)  predicted_if_phi1={pred:+7.2f} "
              f"phi={phi:+.3f} [{phi_lo:+.3f}, {phi_hi:+.3f}]")

    # Granularity predicts delta(C)/delta(B) = 23.08/7.69 = 3.0 exactly; a
    # threadgroup-size step instead predicts a ratio near 1.
    if 128 in arm_qmv and 256 in arm_qmv:
        db = arm_qmv[128][0] - base
        dc = arm_qmv[256][0] - base
        sb, sc = arm_qmv[128][2], arm_qmv[256][2]
        s0 = arm_qmv[64][2]
        ratio = dc / db if db else float("nan")
        rsem = (abs(ratio) * ((sc**2 + s0**2) / dc**2
                              + (sb**2 + s0**2) / db**2) ** 0.5
                if db and dc else float("nan"))
        print(f"\ndelta(C)/delta(B) = {ratio:+.2f} +- {rsem:.2f}   "
              f"(3.00 => granularity, ~1.00 => threadgroup-size step)")

    # Negative control: every kernel present in all arms and not the arm row.
    common = None
    for tg in arms:
        names = set()
        for _, rows, _, _, _ in per_arm[tg]:
            names |= {k for k in rows if ARM_ROW not in k}
        common = names if common is None else (common & names)
    print("\nuntouched-neighbour control (max |delta| vs TG=64, us/step; "
          "atlas resolution +-0.655):")
    worst = []
    for name in sorted(common):
        vals = {}
        ok = True
        for tg in arms:
            v = [rows.get(name) for _, rows, _, _, _ in per_arm[tg]]
            if any(x is None for x in v):
                ok = False
                break
            vals[tg] = statistics.mean(v)
        if not ok:
            continue
        drift = max(abs(vals[tg] - vals[64]) for tg in arms)
        worst.append((drift, name, vals))
    worst.sort(reverse=True)
    for drift, name, vals in worst[:12]:
        cells = " ".join(f"tg{tg}={vals[tg]:8.2f}" for tg in arms)
        flag = "  DRIFT" if drift > 0.655 else ""
        print(f"  {drift:6.2f}  {cells}  {name}{flag}")
    n_drift = sum(1 for d, _, _ in worst if d > 0.655)
    print(f"  {n_drift} of {len(worst)} common kernels drift beyond +-0.655")

    # phi from the slope through all three arms, forced through the origin.
    xs, ys = [], []
    for tg in arms:
        for v in arm_qmv[tg][4]:
            xs.append(PREDICTED[tg] * base)
            ys.append(v - base)
    slope = sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs)
    resid = [y - slope * x for x, y in zip(xs, ys)]
    se = (sum(r * r for r in resid) / (len(xs) - 1) / sum(x * x for x in xs)) ** 0.5
    print(f"\nphi (through-origin slope over all {len(xs)} runs) = "
          f"{slope:+.3f} +- {se:.3f} (95% CI "
          f"[{slope - 1.96 * se:+.3f}, {slope + 1.96 * se:+.3f}])")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
