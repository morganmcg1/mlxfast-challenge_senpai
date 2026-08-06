#!/usr/bin/env python3
"""Research-only: combine the PR #101 round-1 and round-2 decode probes.

Round 1 recorded only summary lines; round 2 also dumped per-step times, so the
Arm B ABBA is analysed from the raw steps and Arm A from the per-point medians
of both rounds.

The two contrasts are reported differently on purpose:

  * Arm B ran OFF/ON/ON/OFF, so the drift-cancelling estimator is
    mean(ON_b, ON_c) - mean(OFF_a, OFF_d); linear host drift cancels exactly.
    With two runs per condition the honest noise scale is the *within*-condition
    run-to-run gap (|ON_b - ON_c|, |OFF_a - OFF_d|), and the ON-OFF contrast has
    to clear it to mean anything. A bootstrap over steps would understate this,
    because steps inside one worker are not independent of that worker.

  * Arm A ran forward in round 1 and backward in round 2, so averaging the two
    rounds per geometry cancels monotone drift across the sweep.
"""
import glob
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WARMUP = 8  # first steps include one-off pipeline warm-up; always an outlier

SUMMARY = re.compile(
    r"decode steps=(\d+) mean=([\d.]+) ms median=([\d.]+) ms p10=([\d.]+) ms "
    r"p90=([\d.]+) ms min=([\d.]+) ms max=([\d.]+) ms")


def read_summary(path):
    with open(path) as fh:
        text = fh.read()
    if "0 divergences (all match)" not in text:
        return None, "DIVERGENCE"
    m = SUMMARY.search(text)
    if not m:
        return None, "no summary"
    n, mean, med, p10, p90, lo, hi = m.groups()
    return dict(n=int(n), mean=float(mean), median=float(med), p10=float(p10),
                p90=float(p90), min=float(lo), max=float(hi)), None


def read_steps(path):
    with open(path) as fh:
        return [float(x) for x in fh if x.strip()][WARMUP:]


def stats(xs):
    o = sorted(xs)
    return dict(n=len(o), mean=statistics.mean(o), median=statistics.median(o),
                p10=o[len(o) // 10], p90=o[9 * len(o) // 10], min=o[0], max=o[-1],
                sd=statistics.stdev(o))


def pct(new, old):
    return (new - old) / old * 100.0


# ------------------------------------------------------------------- Arm B ABBA
print("=" * 78)
print("ARM B  o_proj lane-major scale-base hoist  (round 2, 400-step ABBA)")
print("=" * 78)
r2 = os.path.join(ROOT, "research", "pr101-sweep-r2")
order = ["armb_off_a", "armb_on_b", "armb_on_c", "armb_off_d"]
armb = {}
for tag in order:
    summ, err = read_summary(os.path.join(r2, tag + ".txt"))
    if err:
        print(f"  {tag}: {err} -- Arm B analysis aborted")
        armb = {}
        break
    armb[tag] = stats(read_steps(os.path.join(r2, tag + ".steps.txt")))

if armb:
    print(f"  correctness: all four runs 0 divergences (teacher-forced greedy)")
    print(f"  warm-up steps dropped: {WARMUP}")
    print()
    hdr = f"  {'run':<12}{'n':>5}{'mean':>9}{'median':>9}{'p10':>9}{'min':>9}{'sd':>8}"
    print(hdr)
    for tag in order:
        s = armb[tag]
        print(f"  {tag:<12}{s['n']:>5}{s['mean']:>9.3f}{s['median']:>9.3f}"
              f"{s['p10']:>9.3f}{s['min']:>9.3f}{s['sd']:>8.3f}")
    print()
    for stat in ("mean", "median", "p10", "min"):
        on = (armb["armb_on_b"][stat] + armb["armb_on_c"][stat]) / 2
        off = (armb["armb_off_a"][stat] + armb["armb_off_d"][stat]) / 2
        noise_on = abs(armb["armb_on_b"][stat] - armb["armb_on_c"][stat])
        noise_off = abs(armb["armb_off_a"][stat] - armb["armb_off_d"][stat])
        noise = max(noise_on, noise_off)
        effect = off - on
        verdict = "clears" if abs(effect) > noise else "BELOW"
        print(f"  {stat:<7} ON={on:8.3f}  OFF={off:8.3f}  "
              f"effect={effect:+.3f} ms ({pct(on, off):+.2f}%)   "
              f"within-condition gap: ON-ON={noise_on:.3f} OFF-OFF={noise_off:.3f}"
              f"  -> {verdict} noise")

# --------------------------------------------------------------- Arm A geometry
print()
print("=" * 78)
print("ARM A  gate_sp geometry  (round 1 forward + round 2 backward)")
print("=" * 78)
r1 = os.path.join(ROOT, "research", "pr101-sweep")
geoms = [(r, n) for r in (4, 2, 1) for n in (2, 4, 1)]
rows = []
for r, n in geoms:
    tag = f"gatesp_r{r}n{n}"
    a, ea = read_summary(os.path.join(r1, tag + ".txt"))
    b, eb = read_summary(os.path.join(r2, tag + ".txt"))
    if ea or eb:
        print(f"  {tag}: r1={ea or 'ok'} r2={eb or 'ok'}")
        continue
    rows.append((tag, a, b))

if rows:
    base = next((x for x in rows if x[0] == "gatesp_r4n2"), None)
    print(f"  correctness: all points 0 divergences (teacher-forced greedy)")
    print()
    print(f"  {'geometry':<14}{'r1 med':>9}{'r2 med':>9}{'avg med':>10}"
          f"{'vs stock':>10}{'r1-r2 gap':>11}")
    bavg = (base[1]["median"] + base[2]["median"]) / 2
    for tag, a, b in rows:
        avg = (a["median"] + b["median"]) / 2
        mark = "  <- stock" if tag == "gatesp_r4n2" else ""
        print(f"  {tag:<14}{a['median']:>9.3f}{b['median']:>9.3f}{avg:>10.3f}"
              f"{pct(avg, bavg):>9.2f}%{abs(a['median']-b['median']):>11.3f}{mark}")
    spread = [(a["median"] + b["median"]) / 2 for _, a, b in rows]
    print()
    print(f"  family spread: {min(spread):.3f} .. {max(spread):.3f} ms "
          f"({pct(max(spread), min(spread)):.2f}% total)")
    gaps = [abs(a["median"] - b["median"]) for _, a, b in rows]
    print(f"  round-to-round reproducibility (same geometry): "
          f"median gap {statistics.median(gaps):.3f} ms, max {max(gaps):.3f} ms")
    print(f"  -> any geometry effect smaller than the round-to-round gap is "
          f"not resolvable here.")

# ------------------------------------------------------------ round-1 Arm B ref
print()
print("=" * 78)
print("ARM B  round-1 single pair (unbalanced, retained for the record)")
print("=" * 78)
for tag in ("oproj_hoist_off", "oproj_hoist_on"):
    s, e = read_summary(os.path.join(r1, tag + ".txt"))
    if e:
        print(f"  {tag}: {e}")
        continue
    print(f"  {tag:<18}n={s['n']} mean={s['mean']:.3f} median={s['median']:.3f} "
          f"p10={s['p10']:.3f} min={s['min']:.3f} max={s['max']:.3f}")
