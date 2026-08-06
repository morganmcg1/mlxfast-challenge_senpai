#!/usr/bin/env python3
"""Research-only: PR #101 arm A round-3 ABBA ABBA analysis.

Eight 400-step runs alternate stock (R4NS2) and candidate (R1NS2) in
A B B A A B B A order. With four replicates per condition the honest noise
scale is the spread *within* a condition across separate worker processes, so
the contrast is reported against that spread and against a permutation test
over run-level medians. A step-level bootstrap is deliberately not used: steps
inside one worker share that worker's clock, cache and thermal state.

The isolated-dispatch microbenchmark predicts -0.87 % for this geometry; the
test is powered to see that if it is real.
"""
import glob
import itertools
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "pr101-gatesp-abba")
WARMUP = 8
PREDICTED_PCT = -0.87  # research/pr101-gatesp-dispatch-bench.txt, serial arm


def load(tag):
    log = os.path.join(OUT, tag + ".txt")
    with open(log) as fh:
        text = fh.read()
    if "0 divergences (all match)" not in text:
        sys.exit("%s: no clean-divergence line; refusing to score" % tag)
    steps = [float(x) for x in open(os.path.join(OUT, tag + ".steps.txt"))
             if x.strip()][WARMUP:]
    if not steps:
        sys.exit("%s: no steps" % tag)
    return steps


def summary(xs):
    o = sorted(xs)
    return dict(n=len(o), mean=statistics.mean(o), median=statistics.median(o),
                p10=o[len(o) // 10], min=o[0], sd=statistics.stdev(o))


tags = sorted(os.path.basename(p)[:-10]
              for p in glob.glob(os.path.join(OUT, "g*_*.steps.txt")))
if len(tags) != 8:
    print("warning: expected 8 runs, found %d" % len(tags))

runs = [(t, load(t)) for t in tags]
print("run                 n     mean   median      p10      min       sd")
for t, xs in runs:
    s = summary(xs)
    print("%-18s %4d %8.3f %8.3f %8.3f %8.3f %8.3f"
          % (t, s["n"], s["mean"], s["median"], s["p10"], s["min"], s["sd"]))

stock = [(t, xs) for t, xs in runs if "stock" in t]
cand = [(t, xs) for t, xs in runs if "cand" in t]
print("\nreplicates: %d stock, %d candidate" % (len(stock), len(cand)))

print("\nstat        stock     cand    effect        within-stock  within-cand"
      "   verdict")
for key in ("mean", "median", "p10", "min"):
    sv = [summary(xs)[key] for _, xs in stock]
    cv = [summary(xs)[key] for _, xs in cand]
    s, c = statistics.mean(sv), statistics.mean(cv)
    # Widest run-to-run spread inside each condition: the effect must clear it.
    ws, wc = max(sv) - min(sv), max(cv) - min(cv)
    delta = s - c
    verdict = "resolved" if abs(delta) > max(ws, wc) else "BELOW noise"
    print("%-8s %8.3f %8.3f  %+7.3f ms (%+5.2f%%) %8.3f %12.3f   %s"
          % (key, s, c, delta, -delta / s * 100.0, ws, wc, verdict))

# Exact two-sided permutation test over the eight run-level medians.
meds = [(("cand" in t), summary(xs)["median"]) for t, xs in runs]
vals = [m for _, m in meds]
obs = (statistics.mean([m for k, m in meds if not k])
       - statistics.mean([m for k, m in meds if k]))
count = 0
total = 0
for pick in itertools.combinations(range(len(vals)), len(cand)):
    other = [i for i in range(len(vals)) if i not in pick]
    d = statistics.mean([vals[i] for i in other]) - statistics.mean([vals[i] for i in pick])
    total += 1
    if abs(d) >= abs(obs) - 1e-12:
        count += 1
print("\npermutation over run medians: observed %+0.3f ms, p = %d/%d = %.3f"
      % (obs, count, total, count / total))

base = statistics.mean([summary(xs)["median"] for _, xs in stock])
print("microbench prediction: %+0.2f%% (%+0.3f ms); measured: %+0.2f%% (%+0.3f ms)"
      % (PREDICTED_PCT, PREDICTED_PCT / 100.0 * base, -obs / base * 100.0, -obs))


def welch(a, b):
    """Two-sample Welch interval on run-level medians (t=2.45, df~6)."""
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    se = (va + vb) ** 0.5
    return ma - mb, 2.447 * se


def sweep_median(path):
    m = re.search(r"median=([0-9.]+) ms", open(path).read())
    return float(m.group(1))


# Pooled across all three rounds. Rounds 1-2 report the median over all 160
# steps including warm-up; the median is robust to the single high first step,
# so the definitions are close enough to pool, and the pooling is reported as a
# secondary analysis rather than the headline.
prev = []
for d in ("pr101-sweep", "pr101-sweep-r2"):
    for geom, cond in (("gatesp_r4n2", "stock"), ("gatesp_r1n2", "cand")):
        p = os.path.join(ROOT, "research", d, geom + ".txt")
        if os.path.exists(p):
            prev.append((cond, sweep_median(p)))

pool_s = [m for c, m in prev if c == "stock"] + [summary(xs)["median"] for _, xs in stock]
pool_c = [m for c, m in prev if c == "cand"] + [summary(xs)["median"] for _, xs in cand]
d, h = welch(pool_s, pool_c)
pb = statistics.mean(pool_s)
print("\npooled over all rounds: %d stock, %d cand run medians" % (len(pool_s), len(pool_c)))
print("  stock %.3f  cand %.3f  effect %+0.3f ms  95%% CI [%+0.3f, %+0.3f] ms"
      % (pb, statistics.mean(pool_c), d, d - h, d + h))
print("  as speedup: %+0.2f%%  95%% CI [%+0.2f%%, %+0.2f%%]"
      % (d / pb * 100.0, (d - h) / pb * 100.0, (d + h) / pb * 100.0))
print("  microbench prediction %+0.2f%% is %s by this interval"
      % (PREDICTED_PCT, "EXCLUDED" if -PREDICTED_PCT > (d + h) / pb * 100.0 else "NOT excluded"))
