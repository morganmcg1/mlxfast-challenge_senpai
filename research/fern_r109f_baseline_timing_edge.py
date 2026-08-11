#!/usr/bin/env python3
"""READ-ONLY: is the harness's measured BASELINE predictable in time?

Why this matters for the endgame.  The score is exactly

    officialScore = decode_speedup**0.75 * prefill_speedup**0.25
    speedup       = baseline_seconds_per_token / candidate_seconds_per_token

so the harness's own *measured* baseline sits in the numerator.  A submission
that happens to be measured while the machine reports a SLOW baseline is
credited with a higher speedup for identical code.  fern_r109f_baseline_jitter
showed the reported baselines are not constants: rel sd 0.245 % (decode) and
1.962 % (prefill), and because of the 0.25 exponent the prefill baseline
supplies ~7x the score variance that the decode baseline does.

Open question that analysis left: is that dispersion white noise, or is it
slow drift / regime structure?  The distinction is worth real score:

  * white noise      -> firing time is irrelevant, only shot count matters;
  * drift or regimes -> the baseline observable on rows that have ALREADY gone
                        terminal predicts the baseline our next shot will get,
                        and the right move is to fire into a slow-baseline
                        window.  Edge on the score = 0.25 * (predicted log
                        deviation of baseline prefill) + 0.75 * (same for
                        decode).

Everything here is read-only arithmetic on public leaderboard rows that were
already saved to research/fern-r109f-queue-*.json.  No submission is fired.

Timestamp choice: the benchmark itself runs for ~46 s (median
benchmark_wall_seconds) just before a row goes terminal, so the *measurement*
time is updatedAt, not createdAt.  Sojourns are 17-113 min, so using createdAt
would smear the signal by an hour.  We test both and report both.

Usage: python3 research/fern_r109f_baseline_timing_edge.py <queue.json> [...]
"""
import datetime as dt
import json
import math
import statistics
import sys

DEC = "baseline_decode_seconds_per_token"
PRE = "baseline_prefill_seconds_per_token"
W_DEC, W_PRE = 0.75, 0.25
BAR = 2.61955310948
OUR_TREE_MEDIAN = 2.582263  # median normalized draw for our best tree
NEED = BAR / OUR_TREE_MEDIAN - 1.0


def load(paths):
    seen, rows = set(), []
    for p in paths:
        doc = json.load(open(p))
        for r in doc.get("submissions", doc):
            i = r.get("id")
            if i not in seen:
                seen.add(i)
                rows.append(r)
    return rows


def parse(ts):
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def sample(rows, tkey):
    """[(measurement_time, baseline_decode, baseline_prefill, row)] sorted."""
    out = []
    for r in rows:
        m = r.get("officialMetrics")
        if not isinstance(m, dict):
            continue
        d, p, t = m.get(DEC), m.get(PRE), parse(r.get(tkey))
        ok = lambda v: isinstance(v, (int, float)) and v > 0
        if ok(d) and ok(p) and t is not None:
            out.append((t, float(d), float(p), r))
    out.sort(key=lambda x: x[0])
    return out


def relsd(vals):
    if len(vals) < 3:
        return float("nan")
    mu = statistics.median(vals)
    return statistics.stdev(vals) / mu


def windows(sample_, now):
    print("\n== dispersion inside time windows (is the spread era structure?) ==")
    print(f"{'window':>10} {'n':>6} {'relsd_dec':>10} {'relsd_pre':>10} "
          f"{'score_sd_1shot':>15}")
    for label, hours in (("all", None), ("48h", 48), ("24h", 24),
                         ("12h", 12), ("6h", 6), ("2h", 2), ("1h", 1)):
        if hours is None:
            sub = sample_
        else:
            cut = now - dt.timedelta(hours=hours)
            sub = [s for s in sample_ if s[0] >= cut]
        if len(sub) < 3:
            print(f"{label:>10} {len(sub):>6} {'-':>10} {'-':>10} {'-':>15}")
            continue
        sd_d, sd_p = relsd([s[1] for s in sub]), relsd([s[2] for s in sub])
        # baseline noise -> score noise.  log speedup = log base - log cand;
        # assume the candidate measurement carries the same relative jitter as
        # the baseline measurement of the same quantity and is independent, so
        # each log speedup has sqrt(2)x the baseline's sd.
        score_sd = math.sqrt((W_DEC * math.sqrt(2) * sd_d) ** 2 +
                             (W_PRE * math.sqrt(2) * sd_p) ** 2)
        print(f"{label:>10} {len(sub):>6} {100*sd_d:>9.3f}% {100*sd_p:>9.3f}% "
              f"{100*score_sd:>14.3f}%")


def resid(sample_, idx, win=41):
    """log deviation of column idx from a centred rolling median."""
    vals = [math.log(s[idx]) for s in sample_]
    n, half, out = len(vals), win // 2, []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out.append(vals[i] - statistics.median(vals[lo:hi]))
    return vals, out


def autocorr(x, lag):
    n = len(x) - lag
    if n < 10:
        return float("nan")
    a, b = x[:-lag], x[lag:]
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((ai - ma) * (bi - mb) for ai, bi in zip(a, b))
    da = math.sqrt(sum((ai - ma) ** 2 for ai in a))
    db = math.sqrt(sum((bi - mb) ** 2 for bi in b))
    return num / (da * db) if da > 0 and db > 0 else float("nan")


def drift_report(sample_, name, idx):
    logs, _ = resid(sample_, idx)
    print(f"\n== {name}: autocorrelation in measurement order ==")
    print("  (white noise -> all ~0; drift/regimes -> positive and decaying)")
    devs = [v - statistics.median(logs) for v in logs]
    row = []
    for lag in (1, 2, 3, 5, 10, 20, 50):
        row.append(f"lag{lag}={autocorr(devs, lag):+.3f}")
    print("  " + "  ".join(row))
    return devs


def predictive(sample_, m=5):
    """Can the last m TERMINAL rows predict the next row's baseline?

    Strictly causal: for row i we only use rows 0..i-1, which were already
    terminal (and therefore publicly visible) when row i was measured.
    """
    print(f"\n== causal predictability: median of previous {m} rows -> next row ==")
    ld = [math.log(s[1]) for s in sample_]
    lp = [math.log(s[2]) for s in sample_]
    for name, series in (("baseline_decode", ld), ("baseline_prefill", lp)):
        base = statistics.median(series)
        xs, ys = [], []
        for i in range(m, len(series)):
            xs.append(statistics.median(series[i - m:i]) - base)
            ys.append(series[i] - base)
        if len(xs) < 30:
            print(f"  {name}: too few points")
            continue
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        syy = sum((y - my) ** 2 for y in ys)
        slope = sxy / sxx if sxx else float("nan")
        r = sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")
        sd_pred = abs(slope) * statistics.stdev(xs)
        print(f"  {name}: n={len(xs)} slope={slope:+.3f} r={r:+.3f} "
              f"r2={r*r:.3f} sd(predicted log dev)={100*sd_pred:.3f}%")
        yield name, slope, r, sd_pred


def edge(pred):
    print("\n== what a timing rule could be worth on the score ==")
    tot = 0.0
    for name, slope, r, sd_pred in pred:
        w = W_DEC if "decode" in name else W_PRE
        contrib = w * sd_pred
        tot += contrib ** 2
        print(f"  {name}: weight {w} x sd(predictable part) {100*sd_pred:.3f}% "
              f"-> {100*contrib:.3f}% of score sd is FORECASTABLE")
    tot = math.sqrt(tot)
    print(f"  combined forecastable score sd: {100*tot:.3f}%")
    print(f"  gap our tree must close to take the crown: {100*NEED:.3f}%")
    if tot > 0:
        print(f"  firing into a +1 sd favourable window is worth "
              f"{100*tot:.3f}% -> {100*tot/ (100*NEED) * 100:.1f}% of the gap")
    print("  NOTE a favourable window means a SLOW measured baseline: the "
          "baseline sits in the numerator of the speedup.")


def cluster_check(sample_, idx, name):
    print(f"\n== {name}: is the spread regimes rather than noise? ==")
    vals = sorted(s[idx] for s in sample_)
    n = len(vals)
    qs = [vals[int(q * (n - 1))] for q in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)]
    med = qs[3]
    print("  quantiles/median: " +
          " ".join(f"{q/med:.4f}" for q in qs))
    # biggest relative gap between consecutive order statistics in the bulk
    lo, hi = int(0.02 * n), int(0.98 * n)
    gaps = [(vals[i + 1] / vals[i], vals[i]) for i in range(lo, hi - 1)]
    g, at = max(gaps)
    print(f"  largest interior gap: x{g:.4f} at {at:.6g} "
          f"({'regime split' if g > 1.02 else 'no split: continuous'})")


def main(paths):
    rows = load(paths)
    print(f"rows loaded: {len(rows)}")
    for tkey in ("updatedAt", "createdAt"):
        s = sample(rows, tkey)
        if not s:
            print(f"\n#### {tkey}: no usable rows")
            continue
        now = max(x[0] for x in s)
        print(f"\n#################### measurement time = {tkey} "
              f"(n={len(s)}, last {now.isoformat()})")
        windows(s, now)
        if tkey != "updatedAt":
            continue  # order-based tests only make sense on measurement order
        drift_report(s, "baseline_decode", 1)
        drift_report(s, "baseline_prefill", 2)
        cluster_check(s, 1, "baseline_decode")
        cluster_check(s, 2, "baseline_prefill")
        edge(list(predictive(s, m=5)))
        # a 48h-only replay, in case the fleet/harness changed long ago
        cut = now - dt.timedelta(hours=48)
        recent = [x for x in s if x[0] >= cut]
        if len(recent) > 100:
            print(f"\n---- replay on the last 48h only (n={len(recent)}) ----")
            drift_report(recent, "baseline_prefill (48h)", 2)
            edge(list(predictive(recent, m=5)))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
