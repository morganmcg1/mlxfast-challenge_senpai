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
# Two palindrome designs share this estimator. `geom4` is the 2x2 factorial of
# the assignment (g0/g1/g2/g3, 4-run halves); `occ2` is the follow-up two-arm
# contrast on the occupancy-increasing direction (g0/g4, 2-run halves).
DESIGNS = {
    "geom4": {
        "arms": ("g0", "g1", "g2", "g3"),
        "half_size": 4,
        "block_size": 8,
        "base_arm": "g0",
        "stats_name": "insitu-stats.json",
        "contrasts": {
            "g1_vs_g0": ({"g1": 1.0}, {"g0": 1.0}),
            "g2_vs_g0": ({"g2": 1.0}, {"g0": 1.0}),
            "g3_vs_g0": ({"g3": 1.0}, {"g0": 1.0}),
            "A_amortisation": ({"g1": 0.5, "g2": 0.5}, {"g0": 0.5, "g3": 0.5}),
            "B_threadgroup_shape": ({"g1": 0.5, "g3": 0.5}, {"g0": 0.5, "g2": 0.5}),
            "AB_interaction": ({"g0": 0.5, "g1": 0.5}, {"g2": 0.5, "g3": 0.5}),
        },
    },
    "occ2": {
        "arms": ("g0", "g4"),
        "half_size": 4,
        "block_size": 8,
        "base_arm": "g0",
        "stats_name": "insitu-stats-occ2.json",
        "contrasts": {
            "g4_vs_g0": ({"g4": 1.0}, {"g0": 1.0}),
        },
    },
}
DESIGN = DESIGNS["geom4"]
# Rule 105 (advisor, #644 comment 5241615076): the campaign price was fitted on
# an official M5 decode, so any bar derived from it is in M5 us/step. This host
# is M4 Pro, so a measured delta must be converted, never compared directly:
#     delta_pct_cs = delta_M4_us_per_step * k * PRICE_PCT_CS_PER_US
# k = alpha in the bytes regime, beta in the latency regime. T3b oproj h64 is
# labelled bytes, provisionally: if tanjiro's #648 census returns ISSUE-bound
# there is no valid k and no conversion is legitimate at all.
PRICE_PCT_CS_PER_US = 0.015228
K = {"alpha_0.4369": 0.4369, "alpha_0.389": 0.389, "beta_0.5": 0.5}
K_PRIMARY = "alpha_0.4369"
BAR_PCT_CS = 0.4       # solo shippability bar
SUMMAND_PCT_CS = 0.2034  # rule 105.10: residual once de-biased L3 supplies 0.1966
HOST = "M4 Pro, 20 GPU cores, applegpu_g16s, nax_available=false"


def bar_us_m4(pct_cs: float, k_name: str = K_PRIMARY) -> float:
    return pct_cs / (K[k_name] * PRICE_PCT_CS_PER_US)


BAR_US_M4 = bar_us_m4(BAR_PCT_CS)              # 60.13
SUMMAND_US_M4 = bar_us_m4(SUMMAND_PCT_CS)      # 30.58

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
    """Bucket rows into halves that carry `half_size / len(arms)` runs per arm.

    Every design's half is position-balanced: each arm's mean position within
    the half is the same, so a linear within-half drift cancels inside the half
    and only the mirrored-block average is needed for curvature. That is what
    buys the ~14 us/step noise floor; an unbalanced adjacent-pair estimator on
    the same rows measures ~130 us/step of session wander instead.
    """
    arms, half_size = DESIGN["arms"], DESIGN["half_size"]
    reps = half_size // len(arms)
    want = {a: reps for a in arms}
    halves: list[dict] = []
    for i in range(0, len(rows) - half_size + 1, half_size):
        chunk = rows[i:i + half_size]
        got: dict[str, int] = {}
        for c in chunk:
            got[c["arm"]] = got.get(c["arm"], 0) + 1
        if got != want:
            raise SystemExit(f"half at index {i} is not {reps} run(s) of each of "
                             f"{arms}: {[c['tag'] for c in chunk]}")
        order = "forward" if chunk[0]["arm"] == DESIGN["base_arm"] else "reverse"
        halves.append({
            "half": len(halves),
            "session": chunk[0]["session"],
            "block": (chunk[0]["pos"] - 1) // DESIGN["block_size"],
            "order": order,
            "positions": [c["pos"] for c in chunk],
            "arm_pos": {a: [c["pos"] for c in chunk if c["arm"] == a] for a in arms},
            "decode": {a: st.fmean([c["decode"] for c in chunk if c["arm"] == a])
                       for a in arms},
            "prefill": {a: st.fmean([c["prefill"] for c in chunk if c["arm"] == a])
                        for a in arms},
        })
    return halves


def contrast_value(vals: dict[str, float], plus: dict[str, float],
                   minus: dict[str, float]) -> float:
    return (sum(w * vals[a] for a, w in plus.items())
            - sum(w * vals[a] for a, w in minus.items()))


def summarise(diffs: list[float], base: float, priced: bool = True) -> dict[str, object]:
    n = len(diffs)
    mean = st.fmean(diffs)
    sd = st.stdev(diffs) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    h = t95(n - 1) * se if n > 1 else float("nan")
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    # Rule 105.6: every quantity carries a host tag and appears in both units.
    mean_us, h_us = mean * 1e6, h * 1e6
    # A negative delta is a speedup, so the largest gain the interval allows is
    # -(mean - h). Rule 105.7 makes this the deliverable, not the point estimate.
    best_case_gain_us = -(mean_us - h_us)
    # The price and both bars were fitted on the *decode* axis, so pricing a
    # prefill delta in % of cs would be the same class of unit error rule 105
    # names. The placebo axis therefore reports measured us only.
    priced_fields: dict[str, object] = {
        "mean_us_per_step_m4": mean_us,
        "ci95_us_per_step_m4": [mean_us - h_us, mean_us + h_us],
        "mde_us_per_step_m4": h_us,
        "best_case_gain_us_per_step_m4": best_case_gain_us,
        "mean_pct_cs": {k: mean_us * v * PRICE_PCT_CS_PER_US for k, v in K.items()},
        "ci95_pct_cs_primary": [(mean_us - h_us) * K[K_PRIMARY] * PRICE_PCT_CS_PER_US,
                                (mean_us + h_us) * K[K_PRIMARY] * PRICE_PCT_CS_PER_US],
        "resolves_bar": bool(n > 1 and h_us <= BAR_US_M4),
        "resolves_summand": bool(n > 1 and h_us <= SUMMAND_US_M4),
        "n_pairs_for_bar": n_for_bar(sd, BAR_US_M4),
        "n_pairs_for_summand": n_for_bar(sd, SUMMAND_US_M4),
        # rule 105.5: a bit-exact, CI-excludes-zero win below the solo bar is
        # still a valid summand for fern if it comes from a different family.
        "banks_as_summand": bool(n > 1 and abs(mean) > h
                                 and mean_us <= -SUMMAND_US_M4),
        # a null is useful when even the interval's best case cannot fund a
        # summand: that lets fern stop budgeting for this family.
        "excludes_summand_sized_gain": bool(n > 1 and best_case_gain_us < SUMMAND_US_M4),
    } if priced else {k: None for k in (
        "mean_us_per_step_m4", "ci95_us_per_step_m4", "mde_us_per_step_m4",
        "best_case_gain_us_per_step_m4",
        "mean_pct_cs", "ci95_pct_cs_primary", "resolves_bar", "resolves_summand",
        "n_pairs_for_bar", "n_pairs_for_summand", "banks_as_summand",
        "excludes_summand_sized_gain")}
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
        "sign_pos": pos,
        "sign_neg": neg,
        # exact two-sided sign test under p=0.5
        "sign_p": sign_p(max(pos, neg), pos + neg),
        "values_s": diffs,

        "host": HOST,
        "mean_us_per_token_m4": mean_us,
        "ci95_us_per_token_m4": [mean_us - h_us, mean_us + h_us],
        "mde_us_per_token_m4": h_us,
        "best_case_gain_us_per_token_m4": best_case_gain_us,
        "priced_in_cs": priced,
        **priced_fields,
    }


def n_for_bar(sd: float, target_us: float) -> int | None:
    """Pairs needed for a t-CI half-width of target_us at the observed noise."""
    if not math.isfinite(sd) or sd <= 0.0:
        return None
    target = target_us * 1e-6
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
    ref = DESIGN["base_arm"]
    base = st.fmean([h[axis][ref] for h in halves])
    out: dict[str, object] = {
        "axis": axis,
        "g0_mean_s": base,
        "g0_cov_pct": 100.0 * st.stdev([h[axis][ref] for h in halves])
        / base if len(halves) > 1 else float("nan"),
        "arm_means_s": {a: st.fmean([h[axis][a] for h in halves])
                        for a in DESIGN["arms"]},
        "contrasts": {},
    }
    for name, (plus, minus) in DESIGN["contrasts"].items():
        half_diffs = [contrast_value(h[axis], plus, minus) for h in halves]
        rec = summarise(half_diffs, base, priced=axis == "decode")
        rec["by_order"] = {
            o: st.fmean([d for d, h in zip(half_diffs, halves) if h["order"] == o])
            for o in ("forward", "reverse")
            if any(h["order"] == o for h in halves)
        }
        blocks: dict[tuple, list[float]] = {}
        for d, h in zip(half_diffs, halves):
            blocks.setdefault((h["session"], h["block"]), []).append(d)
        block_means = [st.fmean(v) for v in blocks.values() if len(v) == 2]
        rec["block_means"] = (summarise(block_means, base, priced=axis == "decode")
                              if len(block_means) > 1 else None)
        out["contrasts"][name] = rec  # type: ignore[index]
    return out


def main() -> int:
    global DESIGN
    argv = sys.argv[1:]
    if "--design" in argv:
        i = argv.index("--design")
        name = argv[i + 1]
        if name not in DESIGNS:
            raise SystemExit(f"unknown design {name!r}; have {sorted(DESIGNS)}")
        DESIGN = DESIGNS[name]
        argv = argv[:i] + argv[i + 2:]
    else:
        name = "geom4"
    sessions = argv or ["abba1", "abba2"]
    rows = load_rows(sessions)
    halves = group_halves(rows)
    n_fwd = sum(1 for h in halves if h["order"] == "forward")
    ledger = {
        "design": name,
        "design_arms": list(DESIGN["arms"]),
        "sessions": sessions,
        "n_runs": len(rows),
        "n_halves": len(halves),
        "n_forward_halves": n_fwd,
        "n_reverse_halves": len(halves) - n_fwd,
        "all_passed_correctness": True,
        "host": HOST,
        "bars": {
            "price_pct_cs_per_m5_us_per_step": PRICE_PCT_CS_PER_US,
            "k_regime_label": "bytes (provisional pending #648 census)",
            "k_primary": K_PRIMARY,
            "solo_bar_pct_cs": BAR_PCT_CS,
            "solo_bar_us_per_step_m4": {k: bar_us_m4(BAR_PCT_CS, k) for k in K},
            "summand_bar_pct_cs": SUMMAND_PCT_CS,
            "summand_bar_us_per_step_m4": {k: bar_us_m4(SUMMAND_PCT_CS, k) for k in K},
            "single_receipt_detection_bar_us_per_step_m4": 80.0,
            "note": "rule 105/105.7/105.10; the solo bar sits below the ~80 us/step "
                    "single-receipt M4 detection bar, which is why paired ABBA is "
                    "the only admissible instrument here",
        },
        "halves": halves,
        "decode": analyse(halves, "decode"),
        "prefill_placebo": analyse(halves, "prefill"),
    }
    out = ART / DESIGN["stats_name"]
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
            unit = "us/step M4" if rec["priced_in_cs"] else "us/token M4"
            line = (f"  {'':22s} {rec['mean_us_per_token_m4']:+8.2f} {unit} "
                    f"CI[{rec['ci95_us_per_token_m4'][0]:+8.2f},"
                    f"{rec['ci95_us_per_token_m4'][1]:+8.2f}]")
            if rec["priced_in_cs"]:
                line += (f" -> {rec['mean_pct_cs'][K_PRIMARY]:+7.4f} %cs "
                         f"(bar {BAR_US_M4:.1f}, summand {SUMMAND_US_M4:.1f} "
                         f"us/step M4)")
            print(line)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
