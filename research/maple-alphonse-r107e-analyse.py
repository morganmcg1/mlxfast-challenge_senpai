#!/usr/bin/env python3
"""R107-E Stage 3: drift-cancelling paired estimator over the in-situ ABBA rows.

Design. Every block is the palindrome `g0 g1 g2 g3 | g3 g2 g1 g0`. Half A runs
the four arms in forward order, half B in reversed order, so each half yields
one observation per arm and the two halves place any given arm at mirrored
positions. Under a linear session drift with slope `s` per position, the
within-half contrast against g0 picks up `+k*s` in half A and `-k*s` in half B;
averaging the mirrored halves cancels it exactly. That is the whole reason the
schedule is a palindrome rather than a repeat.

Estimators reported per contrast:
  * `half_diffs`   - one paired difference per half (8 halves = 8 ABBA pairs,
                     4 forward-order and 4 reverse-order), mean + t_7 CI.
  * `block_means`  - the drift-cancelled average of each block's mirrored pair
                     (n = blocks), mean + t CI. Same point estimate, different
                     variance model.
  * sign test on the half diffs, which assumes nothing about the noise shape.

The 2x2 factorial is orthogonal in the same half-level coordinates:
  factor A = results_per_simdgroup (4 -> 8): A+ = {g1,g2}, A- = {g0,g3}
  factor B = rows_per_threadgroup  (8 -> 16): B+ = {g1,g3}, B- = {g0,g2}
  interaction AB                            : + = {g0,g1}, - = {g2,g3}

The prefill axis is a built-in placebo. The decode oproj call site is gated on
`gatePerHead && B == 1 && L == 1` (LagunaRuntimeModel.swift:6355-6362), so the
512-token prefill cannot reach the kernel under any arm. Whatever the prefill
estimator returns is this session's noise floor for an identical-code null.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics as st
import sys

ART = pathlib.Path(__file__).resolve().parent / "artifacts" / "maple-alphonse-r107e"
INSITU = ART / "insitu"
ARMS = ("g0", "g1", "g2", "g3")
HALF_SIZE = 4
BLOCK_SIZE = 8
# assignment lever bar: 0.4% of the M5 candidate step
BAR_PCT = 0.4

# two-sided 95% t quantiles, indexed by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 19: 2.093, 23: 2.069, 31: 2.040}


def t95(dof: int) -> float:
    if dof < 1:
        return float("nan")
    if dof in T95:
        return T95[dof]
    return min((v for k, v in T95.items() if k >= dof), default=1.96)


def load_rows(sessions: list[str]) -> list[dict]:
    rows = []
    for path in sorted(INSITU.glob("*.row.json")):
        r = json.loads(path.read_text())
        if r["session"] not in sessions:
            continue
        if not r.get("passed"):
            raise SystemExit(f"{path.name}: correctness did not pass; refusing to analyse")
        # global half index: consecutive halves across the concatenated sessions
        r["session_order"] = sessions.index(r["session"])
        rows.append(r)
    rows.sort(key=lambda r: (r["session_order"], r["pos"]))
    return rows


def group_halves(rows: list[dict]) -> list[dict]:
    """Bucket rows into complete halves of four distinct arms."""
    halves: list[dict] = []
    for i in range(0, len(rows) - HALF_SIZE + 1, HALF_SIZE):
        chunk = rows[i:i + HALF_SIZE]
        if {c["arm"] for c in chunk} != set(ARMS):
            raise SystemExit(f"half at index {i} is not a permutation of {ARMS}: "
                             f"{[c['tag'] for c in chunk]}")
        pos = [c["pos"] for c in chunk]
        order = "forward" if chunk[0]["arm"] == "g0" else "reverse"
        halves.append({
            "half": len(halves),
            "session": chunk[0]["session"],
            "block": (chunk[0]["pos"] - 1) // BLOCK_SIZE,
            "order": order,
            "positions": pos,
            "arm_pos": {c["arm"]: c["pos"] for c in chunk},
            "decode": {c["arm"]: c["decode"] for c in chunk},
            "prefill": {c["arm"]: c["prefill"] for c in chunk},
        })
    return halves


CONTRASTS = {
    "g1_vs_g0": ({"g1": 1.0}, {"g0": 1.0}),
    "g2_vs_g0": ({"g2": 1.0}, {"g0": 1.0}),
    "g3_vs_g0": ({"g3": 1.0}, {"g0": 1.0}),
    "A_amortisation": ({"g1": 0.5, "g2": 0.5}, {"g0": 0.5, "g3": 0.5}),
    "B_threadgroup_shape": ({"g1": 0.5, "g3": 0.5}, {"g0": 0.5, "g2": 0.5}),
    "AB_interaction": ({"g0": 0.5, "g1": 0.5}, {"g2": 0.5, "g3": 0.5}),
}


def contrast_value(vals: dict[str, float], plus: dict[str, float],
                   minus: dict[str, float]) -> float:
    return (sum(w * vals[a] for a, w in plus.items())
            - sum(w * vals[a] for a, w in minus.items()))


def summarise(diffs: list[float], base: float) -> dict[str, object]:
    n = len(diffs)
    mean = st.fmean(diffs)
    sd = st.stdev(diffs) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    h = t95(n - 1) * se if n > 1 else float("nan")
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    return {
        "n": n,
        "mean_s": mean,
        "mean_pct": 100.0 * mean / base,
        "sd_s": sd,
        "ci95_half_width_s": h,
        "ci95_pct": [100.0 * (mean - h) / base, 100.0 * (mean + h) / base],
        "excludes_zero": bool(n > 1 and abs(mean) > h),
        # smallest effect this n and this noise could have resolved
        "mde_pct": 100.0 * h / base,
        "resolves_bar": bool(n > 1 and 100.0 * h / base <= BAR_PCT),
        "n_pairs_for_bar": n_for_bar(sd, base),
        "sign_pos": pos,
        "sign_neg": neg,
        # exact two-sided sign test under p=0.5
        "sign_p": sign_p(max(pos, neg), pos + neg),
        "values_s": diffs,
    }


def n_for_bar(sd: float, base: float) -> int | None:
    """Pairs needed for a t-CI half-width of BAR_PCT at the observed noise."""
    if not math.isfinite(sd) or sd <= 0.0:
        return None
    target = BAR_PCT / 100.0 * base
    for n in range(2, 4097):
        if t95(n - 1) * sd / math.sqrt(n) <= target:
            return n
    return None


def sign_p(k: int, n: int) -> float:
    if n == 0:
        return float("nan")
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2.0 * tail)


def analyse(halves: list[dict], axis: str) -> dict[str, object]:
    base = st.fmean([h[axis]["g0"] for h in halves])
    out: dict[str, object] = {
        "axis": axis,
        "g0_mean_s": base,
        "g0_cov_pct": 100.0 * st.stdev([h[axis]["g0"] for h in halves])
        / base if len(halves) > 1 else float("nan"),
        "arm_means_s": {a: st.fmean([h[axis][a] for h in halves]) for a in ARMS},
        "contrasts": {},
    }
    for name, (plus, minus) in CONTRASTS.items():
        half_diffs = [contrast_value(h[axis], plus, minus) for h in halves]
        rec = summarise(half_diffs, base)
        rec["by_order"] = {
            o: st.fmean([d for d, h in zip(half_diffs, halves) if h["order"] == o])
            for o in ("forward", "reverse")
            if any(h["order"] == o for h in halves)
        }
        blocks: dict[tuple, list[float]] = {}
        for d, h in zip(half_diffs, halves):
            blocks.setdefault((h["session"], h["block"]), []).append(d)
        block_means = [st.fmean(v) for v in blocks.values() if len(v) == 2]
        rec["block_means"] = summarise(block_means, base) if len(block_means) > 1 else None
        out["contrasts"][name] = rec  # type: ignore[index]
    return out


def main() -> int:
    sessions = sys.argv[1:] or ["abba1", "abba2"]
    rows = load_rows(sessions)
    halves = group_halves(rows)
    n_fwd = sum(1 for h in halves if h["order"] == "forward")
    ledger = {
        "sessions": sessions,
        "n_runs": len(rows),
        "n_halves": len(halves),
        "n_forward_halves": n_fwd,
        "n_reverse_halves": len(halves) - n_fwd,
        "all_passed_correctness": True,
        "halves": halves,
        "decode": analyse(halves, "decode"),
        "prefill_placebo": analyse(halves, "prefill"),
    }
    out = ART / "insitu-stats.json"
    out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

    for axis in ("decode", "prefill_placebo"):
        a = ledger[axis]
        print(f"=== {axis}: g0={a['g0_mean_s'] * 1e3:.4f} ms "
              f"cov={a['g0_cov_pct']:.3f}% n_halves={len(halves)} ===")
        for name, rec in a["contrasts"].items():
            star = "*" if rec["excludes_zero"] else " "
            print(f" {star}{name:22s} {rec['mean_pct']:+7.3f}% "
                  f"CI[{rec['ci95_pct'][0]:+7.3f},{rec['ci95_pct'][1]:+7.3f}] "
                  f"fwd={100 * rec['by_order'].get('forward', float('nan')) / a['g0_mean_s']:+6.3f} "
                  f"rev={100 * rec['by_order'].get('reverse', float('nan')) / a['g0_mean_s']:+6.3f} "
                  f"sign={rec['sign_pos']}/{rec['sign_pos'] + rec['sign_neg']} "
                  f"p={rec['sign_p']:.3f} "
                  f"mde={rec['mde_pct']:.3f}% n@bar={rec['n_pairs_for_bar']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
