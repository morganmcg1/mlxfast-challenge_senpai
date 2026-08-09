#!/usr/bin/env python3
"""R102-B P4: candidate-side receipt sigma, re-derived on the fresh corpus.

Method and warning are NOT novel here: research/advisor-r93-m5-receipt-channel-
and-promotion-model.md sec.5 established (a) the adjacent-near-duplicate pair
estimator and (b) that the pinned baseline's PREFILL variance is a cold-start
artifact (baseline runs first, absorbs JIT/page-faults/clock ramp) and must
never be used as a proxy for candidate noise.  This script re-runs that
estimator on the corpus pulled 2026-08-09 to get current numbers, then applies
them to the R102-B composed-restoration receipt.
"""
import json
import math
import statistics as st
import sys
from datetime import datetime

CORPUS = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r102b-receipts.json"
OURS, CONTROL = "e08d759f", "59bd72a3"
CONTROL_CS = 2.575633
RECORD = 2.616504
R1_SOLO, R1_LO, R1_HI = 0.002358, 0.001347, 0.003368
R2_SOLO = 0.00130
WD, WP = 0.75, 0.25
# med|d| of a difference of two iid normals = 0.6745*sigma*sqrt(2)
MED_TO_SIGMA = 1.0 / (0.6745 * math.sqrt(2.0))

rows = [r for r in json.load(open(CORPUS)) if r.get("cs")]
for r in rows:
    r["t"] = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ")
rows.sort(key=lambda r: r["t"])
print(f"[corpus] n={len(rows)}  {rows[0]['ts']} .. {rows[-1]['ts']}")


def pair_sigma(pairs, key):
    d = [abs(100.0 * math.log(a[key] / b[key])) for a, b in pairs]
    d.sort()
    med = st.median(d)
    return med * MED_TO_SIGMA, med, d[len(d) // 4], d[len(d) // 10]


# --- estimator 1: adjacent same-solver submissions < 20 min apart -----------
by_solver = {}
for r in rows:
    by_solver.setdefault(r["solver"], []).append(r)
near_pairs = []
for g in by_solver.values():
    for a, b in zip(g, g[1:]):
        if 0 < (b["t"] - a["t"]).total_seconds() <= 1200:
            near_pairs.append((a, b))
print(f"\n[estimator 1] adjacent same-solver pairs <20 min apart: n={len(near_pairs)}")
print("  (upper bound: the pair still contains whatever real code delta was made)")
sig = {}
for key in ("cand_dec", "cand_pre", "bl_dec", "bl_pre"):
    s, med, p25, p10 = pair_sigma(near_pairs, key)
    sig[key] = s
    print(f"  {key:9s} med|d| {med:.4f} %  p25 {p25:.4f} %  p10 {p10:.4f} %"
          f"   sigma_single <= {s:.4f} %")

# --- estimator 2: all adjacent baseline pairs (fixed binary, pure instrument)
allp = list(zip(rows, rows[1:]))
print(f"\n[estimator 2] all adjacent receipt pairs (baseline is a fixed binary): "
      f"n={len(allp)}")
for key in ("bl_dec", "bl_pre"):
    s, med, p25, p10 = pair_sigma(allp, key)
    print(f"  {key:9s} med|d| {med:.4f} %   sigma_single <= {s:.4f} %")

print("\n[why bl_pre is not usable]  (advisor-r93 sec.5)")
lead = [r for r in rows if r["cand_dec"] < 0.005]
print(f"  leading candidates (cand_dec < 5.00 ms): n={len(lead)}")
for key in ("bl_pre", "cand_pre"):
    v = [math.log(r[key]) for r in lead]
    print(f"    {key:9s} cv {100*st.stdev(v):.4f} %")
print("  the baseline runs first and absorbs cold start; its prefill cv is the "
      "artifact, not the channel")

# --- apply to R102-B --------------------------------------------------------
SD_D = sig["cand_dec"] * WD      # decode leg, in cs-percent units
SD_P = sig["cand_pre"] * WP      # prefill leg, in cs-percent units
SD_CS = math.hypot(SD_D, SD_P)
print(f"\n[candidate-side sigma of cs]  decode leg {SD_D:.4f} %  "
      f"prefill leg {SD_P:.4f} %  total <= {SD_CS:.4f} %")

ours = [r for r in rows if r["id"] == OURS][0]
ctrl = [r for r in rows if r["id"] == CONTROL][0]
meas_d = 100.0 * WD * math.log(ctrl["cand_dec"] / ours["cand_dec"])
meas_p = 100.0 * WP * math.log(ctrl["cand_pre"] / ours["cand_pre"])
pred = 100.0 * (R1_SOLO + R2_SOLO)
sig_r1 = 100.0 * (R1_HI - R1_LO) / (2 * 1.96)
sig_pred = math.hypot(sig_r1, sig_r1)

print(f"\n[R102-B receipt]  control {CONTROL} cs {ctrl['cs']:.6f}   "
      f"ours {OURS} cs {ours['cs']:.6f}")
print(f"  decode leg  {meas_d:+.4f} %   prefill leg {meas_p:+.4f} %   "
      f"total {meas_d+meas_p:+.4f} %")

for tag, meas, sd_leg in (("full cs", meas_d + meas_p, SD_CS),
                          ("decode leg only", meas_d, SD_D)):
    sm = sd_leg * math.sqrt(2.0)
    I = meas - pred
    sI = math.hypot(sm, sig_pred)
    hw = 1.96 * sI
    print(f"\n[additivity | {tag}]")
    print(f"  measured            {meas:+.4f} % +- {sm:.4f}")
    print(f"  additive prediction {pred:+.4f} % +- {sig_pred:.4f}")
    print(f"  interaction I       {I:+.4f} % +- {sI:.4f}   "
          f"95% [{I-hw:+.4f}, {I+hw:+.4f}]")
    print(f"  excludes I = 0 ?                    {'YES' if abs(I) > hw else 'NO'}")
    print(f"  excludes full cancellation I={-pred:+.4f}? "
          f"{'YES' if abs(I+pred) > hw else 'NO'}")
    print(f"  resolution +-{hw:.3f} % vs effect under test {pred:.3f} %  "
          f"-> {hw/pred:.1f}x too coarse")

print("\n[design] paired receipts per arm to resolve the additive effect "
      "(95% conf, 80% power)")
for tag, sd_leg in (("full cs", SD_CS), ("decode leg only", SD_D)):
    n = 2.0 * (2.8 * sd_leg / pred) ** 2
    print(f"  {tag:16s} sigma {sd_leg:.4f} % -> n ~ {math.ceil(n)} per arm "
          f"({2*math.ceil(n)} receipts total)")

gap = 100.0 * (RECORD / ours["cs"] - 1.0)
z = gap / (SD_CS * math.sqrt(2.0))
print(f"\n[record]  record {RECORD:.6f}  ours {ours['cs']:.6f}  gap {gap:+.4f} %")
print(f"  posterior-predictive z {z:.2f}  ->  per-draw P(beat record) "
      f"~ {0.5*math.erfc(z/math.sqrt(2.0)):.2e}")
