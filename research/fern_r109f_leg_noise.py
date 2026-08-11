#!/usr/bin/env python3
"""fern R109-F: is the ranked *candidate* leg an instrument or a lottery?

The claim under test
--------------------
Ranking all 1231 full-leg receipts by
    normalized = (REF_D/decode)**0.75 * (REF_P/prefill)**0.25
puts package `5c542169b5` (4890.7 us decode) at rank 2 of 1231 and our own
base-class packages at ~2.5669, 0.64 % behind.  Read naively that says "we own
a package 0.64 % faster than the one we keep submitting".

But `submissionCommitSha` is unique per receipt (1189 receipts, 1189 shas), so
there is no same-sha replicate group to estimate the instrument from.  The
*baseline* legs supply it instead: every receipt re-measures the identical
unmodified model on the same host, so the baseline leg's coefficient of
variation is pure host jitter.  If the candidate leg's CV over a set of
near-identical packages matches the baseline leg's CV, the candidate leg is
carrying no code signal at all and the ranking is a lottery.

Usage:
    python3 research/fern_r109f_leg_noise.py [receipts.json] [since_iso]
"""

from __future__ import annotations

import json
import statistics
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_p4.json"
SINCE = sys.argv[2] if len(sys.argv) > 2 else "2026-08-10T00"

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626

OURS = {"c1c0ba2c": "t1 base", "88584270": "t2 base(same exe)",
        "e4078827": "t3 QHOIST=1"}
TOPS = {"fefaed88": "MyatKaung rank1", "e27f1ce4": "morgan rank2",
        "25e1f18e": "morgan rank3", "1a7a0ea4": "fyrsta7 rank4"}


def norm(dec: float, pf: float) -> float:
    return (REF_D / dec) ** 0.75 * (REF_P / pf) ** 0.25


def cv(xs: list) -> float:
    return 100.0 * statistics.stdev(xs) / statistics.fmean(xs)


def main() -> None:
    rows = json.load(open(PATH))["submissions"]
    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (d and p and bd and bp and m.get("passed_correctness")):
            continue
        recs.append({
            "id": r["id"][:8], "solver": r["solverUsername"],
            "created": (r.get("createdAt") or "")[:19],
            "d": d * 1e6, "p": p * 1e6, "bd": bd * 1e6, "bp": bp * 1e6,
            "n": norm(d, p),
        })
    recs.sort(key=lambda x: x["created"])
    win = [x for x in recs if x["created"] >= SINCE]

    print("=" * 100)
    print("fern R109-F: candidate-leg noise vs baseline-leg noise")
    print("  source=%s  all full-leg=%d  window >= %s -> n=%d"
          % (PATH, len(recs), SINCE, len(win)))
    print("=" * 100)

    for label, sel in (("window", win), ("all", recs)):
        print("\n[%s]  n=%d" % (label, len(sel)))
        for key, name, unit in (("bd", "baseline decode", "us"),
                                ("d", "candidate decode", "us"),
                                ("bp", "baseline prefill", "us"),
                                ("p", "candidate prefill", "us"),
                                ("n", "normalized", "")):
            xs = [x[key] for x in sel]
            print("  %-18s mean %10.4f %-2s  sd %8.4f  cv %6.3f%%  "
                  "min %10.4f  max %10.4f"
                  % (name, statistics.fmean(xs), unit, statistics.stdev(xs),
                     cv(xs), min(xs), max(xs)))

    mu_d = statistics.fmean([x["d"] for x in win])
    sd_d = statistics.stdev([x["d"] for x in win])
    mu_p = statistics.fmean([x["p"] for x in win])
    sd_p = statistics.stdev([x["p"] for x in win])
    mu_n = statistics.fmean([x["n"] for x in win])
    sd_n = statistics.stdev([x["n"] for x in win])

    print("\nz-scores against the %s window (n=%d)" % (SINCE, len(win)))
    print("-" * 100)
    print("%-9s %-22s %10s %7s %10s %7s %12s %7s"
          % ("receipt", "what", "dec_us", "z_dec", "pf_us", "z_pf",
             "normalized", "z_norm"))
    for x in recs:
        tag = OURS.get(x["id"]) or TOPS.get(x["id"])
        if not tag:
            continue
        print("%-9s %-22s %10.1f %7.2f %10.2f %7.2f %12.6f %7.2f"
              % (x["id"], tag, x["d"], (x["d"] - mu_d) / sd_d,
                 x["p"], (x["p"] - mu_p) / sd_p, x["n"], (x["n"] - mu_n) / sd_n))

    print("\nresolving power of the normalized instrument")
    print("-" * 100)
    print("  per-receipt sd of normalized      : %.4f %% of mean"
          % (100.0 * sd_n / mu_n))
    print("  candidate-decode sd              : %.2f us (%.3f %%)"
          % (sd_d, 100.0 * sd_d / mu_d))
    print("  candidate-prefill sd             : %.2f us (%.3f %%)"
          % (sd_p, 100.0 * sd_p / mu_p))
    rel = 100.0 * sd_n / mu_n
    for effect in (0.10, 0.20, 0.30, 0.60, 1.00):
        # receipts per arm for a two-sample z-test at 95 % power, alpha 0.05
        need = 2 * ((1.96 + 1.645) * rel / effect) ** 2
        print("  to resolve a %.2f %% normalized effect: n >= %6.1f receipts "
              "PER ARM (2-sample, alpha .05, power .95)" % (effect, need))

    print("\nspread of the top of the ranked table, in instrument sigmas")
    print("-" * 100)
    ranked = sorted(recs, key=lambda x: -x["n"])
    top = ranked[:14]
    print("  rank1 normalized %.6f  rank14 normalized %.6f  gap %.4f %% = %.2f sd"
          % (top[0]["n"], top[-1]["n"],
             100.0 * (top[0]["n"] - top[-1]["n"]) / top[0]["n"],
             (top[0]["n"] - top[-1]["n"]) / sd_n))
    ours = [x for x in recs if x["id"] in ("c1c0ba2c", "88584270")]
    if ours:
        base_mu = statistics.fmean([x["n"] for x in ours])
        print("  our base class (n=%d) normalized %.6f -> %.4f %% behind rank1"
              " = %.2f sd of a single receipt, %.2f sd of its own mean"
              % (len(ours), base_mu,
                 100.0 * (top[0]["n"] - base_mu) / top[0]["n"],
                 (top[0]["n"] - base_mu) / sd_n,
                 (top[0]["n"] - base_mu) / (sd_n / len(ours) ** 0.5)))
        print("  our base class vs the WINDOW MEAN %.6f: %+.4f %% = %+.2f sd"
              " of its own mean"
              % (mu_n, 100.0 * (base_mu - mu_n) / mu_n,
                 (base_mu - mu_n) / (sd_n / len(ours) ** 0.5)))


if __name__ == "__main__":
    main()
