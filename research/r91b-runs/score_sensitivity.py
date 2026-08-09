#!/usr/bin/env python3
"""Estimate how much of a ranked score is decided by the pinned baseline draw.

The baseline is frozen code, so its per-session timing spread is pure
measurement noise. Holding a candidate's raw timings fixed and re-scoring it
against every observed baseline draw isolates the baseline-induced component of
receipt-to-receipt sigma. That is a LOWER BOUND on total sigma, because the
candidate's own timing noise is not included.

usage: score_sensitivity.py <baseline-drift.json>
"""

import json
import statistics
import sys

BEST_ID = "cc6ddc12"
BEST_SCORE = 2.61650354381456
ARM_R_ID = "7ce1262d"

rows = json.load(open(sys.argv[1]))
score = lambda bd, bp, cd, cp: (bd / cd) ** 0.75 * (bp / cp) ** 0.25

bl_dec = [r["bl_dec"] for r in rows]
bl_pre = [r["bl_pre"] for r in rows]
n = len(rows)
print(f"scored submissions with a baseline: n={n}")
print(f"window: {rows[0]['ts']} .. {rows[-1]['ts']}")

for name, vals in (("baseline_decode", bl_dec), ("baseline_prefill", bl_pre)):
    mean = statistics.mean(vals)
    sd = statistics.stdev(vals)
    print(f"\n{name}: mean={mean:.12f} sd={sd:.12f} cv={sd / mean * 100:.3f} %")
    print(f"  min={min(vals):.12f}  max={max(vals):.12f}  spread={(max(vals) / min(vals) - 1) * 100:.3f} %")

arm_r = next(r for r in rows if r["id"] == ARM_R_ID)
best = next(r for r in rows if r["id"] == BEST_ID)

print("\n=== where the two receipts of interest sit in the baseline distribution ===")
for label, r in (("leaderboard best", best), ("Arm R", arm_r)):
    dec_rank = sum(1 for v in bl_dec if v <= r["bl_dec"])
    pre_rank = sum(1 for v in bl_pre if v <= r["bl_pre"])
    print(f"{label:<17} score={r['score']:.10f} "
          f"bl_dec pctile={dec_rank / n * 100:5.1f}  bl_pre pctile={pre_rank / n * 100:5.1f}")

print("\n=== Arm R's OWN candidate timings re-scored against every observed baseline draw ===")
sims = [score(r["bl_dec"], r["bl_pre"], arm_r["cand_dec"], arm_r["cand_pre"]) for r in rows]
mean, sd = statistics.mean(sims), statistics.stdev(sims)
print(f"n={len(sims)} mean={mean:.10f} sd={sd:.10f} ({sd / mean * 100:.3f} %)")
print(f"min={min(sims):.10f} max={max(sims):.10f}")
print(f"actual Arm R score      = {arm_r['score']:.10f}")
print(f"leaderboard best        = {BEST_SCORE:.10f}")
beat = sum(1 for s in sims if s >= BEST_SCORE)
print(f"draws where Arm R's UNCHANGED candidate would have scored >= the best: "
      f"{beat}/{len(sims)} = {beat / len(sims) * 100:.1f} %")
print(f"Arm R scored against the BEST receipt's baseline draw = "
      f"{score(best['bl_dec'], best['bl_pre'], arm_r['cand_dec'], arm_r['cand_pre']):.10f}")
print(f"BEST candidate scored against Arm R's baseline draw   = "
      f"{score(arm_r['bl_dec'], arm_r['bl_pre'], best['cand_dec'], best['cand_pre']):.10f}")

print("\n=== leaderboard re-ranked at a common (mean) baseline ===")
ref_d, ref_p = statistics.mean(bl_dec), statistics.mean(bl_pre)
norm = sorted(
    ((score(ref_d, ref_p, r["cand_dec"], r["cand_pre"]), r) for r in rows),
    key=lambda t: -t[0],
)
print(f"{'rank':<6}{'id':<10}{'as-published':<20}{'at common baseline':<21}{'solver'}")
for i, (s, r) in enumerate(norm[:12], 1):
    mark = "  <== ARM R" if r["id"] == ARM_R_ID else ("  <== BEST" if r["id"] == BEST_ID else "")
    print(f"{i:<6}{r['id']:<10}{r['score']:<20.10f}{s:<21.10f}{r['solver']}{mark}")
rank_r = next(i for i, (_, r) in enumerate(norm, 1) if r["id"] == ARM_R_ID)
rank_b = next(i for i, (_, r) in enumerate(norm, 1) if r["id"] == BEST_ID)
print(f"\nArm R common-baseline rank = {rank_r}/{n}; published-best common-baseline rank = {rank_b}/{n}")

print("\n=== robustness 1: is the published score actually driven by the baseline draw? ===")
corr = lambda xs, ys: statistics.correlation(xs, ys)
scores = [r["score"] for r in rows]
print(f"corr(published score, baseline_decode)  = {corr(scores, bl_dec):+.4f}")
print(f"corr(published score, baseline_prefill) = {corr(scores, bl_pre):+.4f}")
print(f"corr(baseline_decode, baseline_prefill) = {corr(bl_dec, bl_pre):+.4f}")
print("corr(baseline_decode, candidate_decode) = "
      f"{corr(bl_dec, [r['cand_dec'] for r in rows]):+.4f}   "
      "(a strong positive value would mean session slowness is common-mode and "
      "partly cancels in the ratio)")
print(f"corr(baseline_prefill, candidate_prefill) = "
      f"{corr(bl_pre, [r['cand_pre'] for r in rows]):+.4f}")

print("\n=== robustness 2: is the pinned baseline stationary over the window? ===")
by_day = {}
for r in rows:
    by_day.setdefault((r["ts"] or "")[:10], []).append(r)
print(f"{'day':<12}{'n':<6}{'mean bl_dec':<18}{'mean bl_pre':<18}{'sd score-equiv %'}")
for day in sorted(by_day):
    rs = by_day[day]
    if len(rs) < 5:
        continue
    d = [x["bl_dec"] for x in rs]
    p = [x["bl_pre"] for x in rs]
    sim = [score(x["bl_dec"], x["bl_pre"], arm_r["cand_dec"], arm_r["cand_pre"]) for x in rs]
    sd_pct = statistics.stdev(sim) / statistics.mean(sim) * 100 if len(sim) > 1 else float("nan")
    print(f"{day:<12}{len(rs):<6}{statistics.mean(d):<18.12f}{statistics.mean(p):<18.12f}{sd_pct:.3f}")

print("\n=== robustness 3: restrict to the most recent 3 days ===")
recent = [r for r in rows if (r["ts"] or "") >= "2026-08-06"]
sims_r = [score(r["bl_dec"], r["bl_pre"], arm_r["cand_dec"], arm_r["cand_pre"]) for r in recent]
mr, sr = statistics.mean(sims_r), statistics.stdev(sims_r)
beat_r = sum(1 for s in sims_r if s >= BEST_SCORE)
print(f"n={len(recent)} mean={mr:.10f} sd={sr:.10f} ({sr / mr * 100:.3f} %) "
      f"draws >= best: {beat_r}/{len(recent)} = {beat_r / len(recent) * 100:.1f} %")
print(f"gap to best in units of this sd: {(BEST_SCORE - arm_r['score']) / sr:.2f} sigma")
