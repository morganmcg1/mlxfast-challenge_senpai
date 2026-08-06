#!/usr/bin/env python3
"""Paired same-host decode/prefill analysis for the PR #85 dense-repack campaigns.

Every file is a verbatim `score.local-iterate.json`. Filenames are
`<prefix>_<slot>_<arm>.json`; the slot number is the run order within the
session, which the drift estimators need.

Usage:  python3 analyze.py a        # campaign A (within-binary switch)
        python3 analyze.py b        # campaign B (git arms)
"""
import glob
import itertools
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "a"
M4_TO_M5 = 0.399          # M4 us/step saved -> M5 us/step saved
MS_TO_SCORE_PCT = 14.862  # M5 ms saved -> % of normalised score
DECODE, PREFILL = 1, 2


def load():
    """Returns {arm: [(slot, path, decode, prefill, peak_ram_gb), ...]}."""
    arms = {}
    for path in sorted(glob.glob(os.path.join(HERE, f"{PREFIX}_*.json"))):
        stem = os.path.basename(path)[:-len(".json")]
        _, slot, arm = stem.split("_", 2)
        d = json.load(open(path))["metrics"]
        assert d["passed_correctness"], f"{path}: correctness failed"
        assert d["max_abs_diff"] == 0, f"{path}: max_abs_diff={d['max_abs_diff']}"
        assert d["checked_steps"] == 130, f"{path}: checked_steps={d['checked_steps']}"
        arms.setdefault(arm, []).append((
            int(slot), path,
            d["decode_seconds_per_token"], d["prefill_seconds_per_token"],
            d["peak_ram_gb"]))
    return arms


def contrast(base, cand, idx):
    """Reduction (base - cand) / base in percent."""
    mb = st.mean([r[idx] for r in base])
    mc = st.mean([r[idx] for r in cand])
    return (mb - mc) / mb * 100.0


def summarize(name, base, cand, idx):
    b = [r[idx] for r in base]
    c = [r[idx] for r in cand]
    mb, mc = st.mean(b), st.mean(c)
    pct = (mb - mc) / mb * 100.0
    sb = st.stdev(b) if len(b) > 1 else 0.0
    sc = st.stdev(c) if len(c) > 1 else 0.0
    se = math.hypot(sb / math.sqrt(len(b)), sc / math.sqrt(len(c))) / mb * 100.0
    print(f"\n{name}: base n={len(b)} mean={mb:.10f} sd={sb / mb * 100:.3f}%")
    print(f"{name}: cand n={len(c)} mean={mc:.10f} sd={sc / mc * 100:.3f}%")
    print(f"{name}: reduction {pct:+.4f}%  SE {se:.4f}%  95% CI "
          f"[{pct - 1.96 * se:+.4f}%, {pct + 1.96 * se:+.4f}%]")
    return mb, mc, pct


def permutation(name, base, cand, idx):
    b = [r[idx] for r in base]
    c = [r[idx] for r in cand]
    pool = b + c
    obs = st.mean(b) - st.mean(c)
    total = extreme = 0
    for pick in itertools.combinations(range(len(pool)), len(b)):
        rest = [i for i in range(len(pool)) if i not in pick]
        stat = st.mean([pool[i] for i in pick]) - st.mean([pool[i] for i in rest])
        total += 1
        if stat >= obs - 1e-18:
            extreme += 1
    print(f"{name}: exact permutation p(one-sided) = {extreme}/{total} = "
          f"{extreme / total:.4f}")


def null_control(name, rows, idx):
    """Measured same-session A/A: every balanced split of one arm's own
    replicates, using the identical estimator. This is the host's null spread
    on byte-identical work, which section 0.9.32 requires before any
    no-harm or win claim."""
    n = len(rows)
    if n < 4:
        print(f"\n{name}: too few replicates for an A/A control")
        return None
    half = n // 2
    deltas = []
    for pick in itertools.combinations(range(n), half):
        rest = [i for i in range(n) if i not in pick]
        x = [rows[i] for i in pick]
        y = [rows[i] for i in rest]
        deltas.append(contrast(x, y, idx))
    mags = sorted(abs(d) for d in deltas)
    p95 = mags[min(len(mags) - 1, int(math.ceil(0.95 * len(mags))) - 1)]
    print(f"\n{name} A/A null ({len(deltas)} balanced {half}v{half} splits of "
          f"byte-identical work):")
    print(f"    range {min(deltas):+.4f}% .. {max(deltas):+.4f}%   "
          f"sd {st.stdev(deltas):.4f}%   95th pct |delta| {p95:.4f}%")
    return p95


def drift_ols(name, base, cand, idx):
    """Slot-ordered OLS: value ~ intercept + arm + slot, so a monotone thermal
    or clock trend across the session cannot masquerade as an arm effect."""
    rows = [(r[0], 0, r[idx]) for r in base] + [(r[0], 1, r[idx]) for r in cand]
    n = len(rows)
    slots = [r[0] for r in rows]
    arm = [r[1] for r in rows]
    y = [r[2] for r in rows]
    ms, ma = st.mean(slots), st.mean(arm)
    cs = [s - ms for s in slots]
    ca = [a - ma for a in arm]
    saa = sum(a * a for a in ca)
    sss = sum(s * s for s in cs)
    sas = sum(a * s for a, s in zip(ca, cs))
    say = sum(a * (v - st.mean(y)) for a, v in zip(ca, y))
    ssy = sum(s * (v - st.mean(y)) for s, v in zip(cs, y))
    det = saa * sss - sas * sas
    if abs(det) < 1e-30:
        print(f"{name}: OLS singular (arm perfectly confounded with slot)")
        return
    beta_arm = (say * sss - ssy * sas) / det
    beta_slot = (ssy * saa - say * sas) / det
    print(f"{name}: drift-adjusted reduction {-beta_arm / st.mean(y) * 100:+.4f}% "
          f"(slot trend {beta_slot / st.mean(y) * 100:+.4f}%/run, n={n})")


arms = load()
names = sorted(arms)
assert len(names) == 2, f"expected exactly two arms, got {names}"
# The base arm is the one whose label sorts first only by accident, so name it
# explicitly: 'off'/'base' are the reference.
base_name = next((k for k in names if k in ("off", "base", "x")), names[0])
cand_name = next(k for k in names if k != base_name)
base, cand = arms[base_name], arms[cand_name]

print(f"campaign {PREFIX!r}: base arm {base_name!r} n={len(base)}, "
      f"candidate arm {cand_name!r} n={len(cand)}")
for arm in (base_name, cand_name):
    for slot, path, d, pf, ram in sorted(arms[arm]):
        print(f"  slot {slot:2d} {arm:5s} {os.path.basename(path):22s} "
              f"decode={d:.12f} prefill={pf:.12f} peak_ram_gb={ram}")

mb, mc, _ = summarize("decode", base, cand, DECODE)
permutation("decode", base, cand, DECODE)
drift_ols("decode", base, cand, DECODE)
p95_decode = null_control(f"decode {base_name}", base, DECODE)
null_control(f"decode {cand_name}", cand, DECODE)

summarize("prefill(control)", base, cand, PREFILL)
permutation("prefill(control)", base, cand, PREFILL)
drift_ols("prefill(control)", base, cand, PREFILL)
null_control(f"prefill {base_name}", base, PREFILL)

for arm in (base_name, cand_name):
    rams = sorted({r[4] for r in arms[arm]})
    print(f"\npeak_ram_gb {arm}: {rams}")

us_m4 = (mb - mc) * 1e6
us_m5 = us_m4 * M4_TO_M5
print(f"\nM4 us/step saved   = {us_m4:.2f}")
print(f"M5 us/step saved   = {us_m5:.2f}  (x{M4_TO_M5})")
print(f"converted score    = {us_m5 / 1000.0 * MS_TO_SCORE_PCT:+.4f}%  "
      f"(x{MS_TO_SCORE_PCT}/ms)")
if p95_decode is not None:
    print(f"A/A 95th pct |null| on decode = {p95_decode:.4f}%  -- the observed "
          f"effect must clear this to be a measurement rather than noise")
