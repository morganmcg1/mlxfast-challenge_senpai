#!/usr/bin/env python3
"""Per-step GPU-busy interval from GPUPROF command-buffer records.

The profile hook prints one `GPUPROF <start> <end> <ndispatch> <names>` line per
command buffer. Decode steps end with the lm-head winner kernel, so that marker
chunks the stream into steps without needing phase markers.
"""
from __future__ import annotations

import argparse
import math
import sys

MARKER = "lmhead_exact_winner_bf16_midpoint_threshold_v1"


def per_step(path: str) -> tuple[list[float], list[int]]:
    busy: list[float] = []
    disp: list[int] = []
    acc_busy = 0.0
    acc_disp = 0
    acc_cbs = 0
    for line in open(path, errors="replace"):
        if not line.startswith("GPUPROF "):
            continue
        parts = line.split(None, 4)
        start, end, n = float(parts[1]), float(parts[2]), int(parts[3])
        names = parts[4] if len(parts) > 4 else ""
        acc_busy += (end - start) * 1e6
        acc_disp += n
        acc_cbs += 1
        if MARKER in names:
            busy.append(acc_busy)
            disp.append(acc_disp)
            acc_busy = 0.0
            acc_disp = 0
            acc_cbs = 0
    return busy, disp


def steady(values: list[float], drop_lo: int, drop_hi: int) -> list[float]:
    return values[drop_lo:len(values) - drop_hi] if drop_hi else values[drop_lo:]


def mean_sd(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var)


def betacf(a: float, b: float, x: float) -> float:
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: float) -> float:
    return 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))


def t_crit(df: float, conf: float) -> float:
    target = (1.0 - conf) / 2.0
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_sf(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def welch(a: list[float], b: list[float], conf: float) -> dict[str, float]:
    ma, sa = mean_sd(a)
    mb, sb = mean_sd(b)
    na, nb = len(a), len(b)
    va, vb = sa * sa / na, sb * sb / nb
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va * va / (na - 1) + vb * vb / (nb - 1))
    t = t_crit(df, conf)
    delta = mb - ma
    return {
        "baseline_mean": ma, "baseline_sd": sa, "n_baseline": na,
        "candidate_mean": mb, "candidate_sd": sb, "n_candidate": nb,
        "delta": delta, "se": se, "df": df,
        "lo": delta - t * se, "hi": delta + t * se,
        "p": 2.0 * t_sf(abs(delta) / se, df) if se > 0 else 1.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--drop-lo", type=int, default=0)
    ap.add_argument("--conf", type=float, default=0.95)
    ap.add_argument("--label", default="gpu_busy_us_per_step")
    args = ap.parse_args()

    base_busy, base_disp = per_step(args.baseline)
    cand_busy, cand_disp = per_step(args.candidate)
    # The decode phase is preceded by prefill/seed command buffers that also
    # end with the winner kernel; keep only the trailing run of 45-CB steps.
    def tail(busy, disp, want):
        keep_b, keep_d = [], []
        for b, d in zip(busy, disp):
            if abs(d - want) <= 1:
                keep_b.append(b)
                keep_d.append(d)
            else:
                keep_b, keep_d = [], []
        return keep_b, keep_d

    bmode = max(set(base_disp), key=base_disp.count)
    cmode = max(set(cand_disp), key=cand_disp.count)
    base_busy, base_disp = tail(base_busy, base_disp, bmode)
    cand_busy, cand_disp = tail(cand_busy, cand_disp, cmode)
    base_busy = steady(base_busy, args.drop_lo, 0)
    cand_busy = steady(cand_busy, args.drop_lo, 0)
    if not base_busy or not cand_busy:
        print("no steady steps recovered", file=sys.stderr)
        raise SystemExit(2)

    print(f"dispatches/step baseline={bmode} candidate={cmode} "
          f"delta={cmode - bmode}")
    r = welch(base_busy, cand_busy, args.conf)
    for k in ("n_baseline", "baseline_mean", "baseline_sd", "n_candidate",
              "candidate_mean", "candidate_sd", "delta", "se", "df", "lo",
              "hi", "p"):
        print(f"{args.label}\t{k}\t{r[k]:.4f}")
    excl = (r["lo"] > 0.0) or (r["hi"] < 0.0)
    print(f"{args.label}\texcludes_zero\t{excl}")
    per_dispatch = r["delta"] / (cmode - bmode) if cmode != bmode else float("nan")
    print(f"{args.label}\tus_per_removed_dispatch\t{per_dispatch:.4f}")


if __name__ == "__main__":
    main()
