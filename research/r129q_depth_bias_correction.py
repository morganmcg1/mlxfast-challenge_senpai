#!/usr/bin/env python3
"""fern R129-Q: how wrong is my own adjudication-odds curve?

In `r129q_adjudication_odds.py` I bucketed sojourns by GLOBAL IN-FLIGHT DEPTH AT
ROW CREATION and then printed a caveat I never measured:

    "depth is measured at row creation and a fire made now also queues behind
     later arrivals; depth has climbed ~0.12 rows/min today, so the KM column is
     mildly optimistic."

A caveat with no number attached is not a result -- it is an excuse filed in
advance.  This script turns it into a measurement, and it can come out either
way: if the ambient depth a row *actually experiences* predicts its sojourn much
better than the depth at its admission, my published curve mis-sorts rows and
the deadline moves.  If it does not, the caveat is dead and I should stop
repeating it.

Three covariates per completed row, deliberately ordered from least to most
contaminated:

  d_create  in-flight depth immediately BEFORE the row was admitted (self
            excluded).  Strictly predetermined -- knowable at fire time.  This
            is what my published KM used.
  d_win     mean in-flight depth over the FIXED window [created, created+W]
            (self's own contribution removed).  Window length does not depend on
            how long the row lived, so long rows are not mechanically given more
            exposure.  Partly postdates admission, so it is usable ex ante only
            through a forecast of the depth process -- which is exactly what the
            campaign has to do anyway.
  d_life    mean in-flight depth over the row's whole life.  ENDOGENOUS BY
            CONSTRUCTION: a slow row is alive longer and therefore averages over
            more of the arrival process, and a globally slow patch produces both
            long sojourns and deep queues.  Reported only as the upper bound on
            "how much could depth possibly explain", never as a predictor.

Then the part that actually decides something: within a fixed d_create bucket,
split rows by the SLOPE of the queue over their first W minutes (rising / flat /
falling).  If rising-queue rows are slower at equal admission depth, my caveat
is real and its size is that gap.  Today's slope is the input the campaign has:
the watcher has read global in-flight = 12 at eight consecutive polls, i.e. a
slope of ZERO, so this is the test of whether my own caveat currently bites.

Read-only: consumes a snapshot already on disk, issues no API call, fires
nothing, builds nothing.

usage: r129q_depth_bias_correction.py <snapshot.json> [--window 15]
                                       [--close 17:00] [--bucket 8]
"""
import argparse
import bisect
import datetime as dt
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r129q_adjudication_odds import TERMINAL, load, ts  # noqa: E402


def timeline(rows, asof):
    """Step function of global in-flight count, plus its running integral.

    Returns (times, level, integral) where level[i] is the in-flight count on
    [times[i], times[i+1]) and integral[i] is the integral of the level from
    times[0] to times[i], in minutes*rows.
    """
    ev = []
    for r in rows:
        a = ts(r["createdAt"])
        term = r.get("status") in TERMINAL
        b = ts(r["updatedAt"]) if term else asof
        if b < a:
            b = a
        ev.append((a, +1))
        ev.append((b, -1))
    ev.sort()
    times, level = [], []
    cur = 0
    i = 0
    while i < len(ev):
        t = ev[i][0]
        while i < len(ev) and ev[i][0] == t:
            cur += ev[i][1]
            i += 1
        times.append(t)
        level.append(cur)
    integral = [0.0]
    for k in range(1, len(times)):
        dtm = (times[k] - times[k - 1]).total_seconds() / 60.0
        integral.append(integral[-1] + level[k - 1] * dtm)
    return times, level, integral


class Depth:
    def __init__(self, rows, asof):
        self.t, self.lv, self.I = timeline(rows, asof)
        self.asof = asof

    def at(self, when):
        """Level in force at `when` (right-continuous step function)."""
        k = bisect.bisect_right(self.t, when) - 1
        return self.lv[k] if k >= 0 else 0

    def _integral_to(self, when):
        k = bisect.bisect_right(self.t, when) - 1
        if k < 0:
            return 0.0
        return self.I[k] + self.lv[k] * (when - self.t[k]).total_seconds() / 60.0

    def mean(self, a, b):
        span = (b - a).total_seconds() / 60.0
        if span <= 0:
            return float(self.at(a))
        return (self._integral_to(b) - self._integral_to(a)) / span

    def before(self, when):
        """Level immediately before `when` -- excludes rows admitted at `when`."""
        k = bisect.bisect_left(self.t, when) - 1
        return self.lv[k] if k >= 0 else 0


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def km(sample):
    """Kaplan-Meier survival from [(duration_min, completed_bool), ...]."""
    pts = sorted(sample)
    n = len(pts)
    surv, out = 1.0, [(0.0, 1.0)]
    i = 0
    while i < n:
        t = pts[i][0]
        d = sum(1 for k in range(i, n) if pts[k][0] == t and pts[k][1])
        cnt = sum(1 for k in range(i, n) if pts[k][0] == t)
        at_risk = n - i
        if d:
            surv *= (1 - d / at_risk)
            out.append((t, surv))
        i += cnt
    return out


def s_at(curve, t):
    s = 1.0
    for tt, ss in curve:
        if tt <= t:
            s = ss
        else:
            break
    return s


def q(curve, p):
    """Smallest t with S(t) <= 1-p; None if the curve never gets there."""
    for tt, ss in curve:
        if ss <= 1 - p:
            return tt
    return None


def perm_p(a, b, trials=4000, seed=17):
    """Two-sided permutation p-value on the difference of medians."""
    import random
    rng = random.Random(seed)
    obs = abs(statistics.median(a) - statistics.median(b))
    pool = list(a) + list(b)
    na = len(a)
    hits = 0
    for _ in range(trials):
        rng.shuffle(pool)
        if abs(statistics.median(pool[:na]) - statistics.median(pool[na:])) >= obs:
            hits += 1
    return (hits + 1) / (trials + 1)


def boot_p_at(sample, budget, trials=600, seed=23):
    """Bootstrap interval for P(sojourn <= budget) via KM on resamples."""
    import random
    rng = random.Random(seed)
    n = len(sample)
    if n == 0:
        return (float("nan"), float("nan"))
    vals = []
    for _ in range(trials):
        rs = [sample[rng.randrange(n)] for _ in range(n)]
        vals.append(1 - s_at(km(rs), budget))
    vals.sort()
    return (vals[int(0.05 * trials)], vals[int(0.95 * trials)])


def build(rows, asof, W):
    """Per-row depth covariates.  Single source of truth: the W&B publisher
    imports this rather than re-deriving (or worse, pasting) any of it."""
    D = Depth(rows, asof)
    recs, dropped_edge = [], 0
    for r in rows:
        c = ts(r["createdAt"])
        term = r.get("status") in TERMINAL
        u = ts(r["updatedAt"]) if term else asof
        soj = (u - c).total_seconds() / 60.0
        if soj < 0:
            continue
        wend = c + dt.timedelta(minutes=W)
        if wend > asof:
            dropped_edge += 1
            continue                      # ambient window not fully observed
        self_share = min(soj, W) / W      # self counted while alive inside window
        recs.append(dict(id=r["id"][:8], c=c, soj=soj, done=term,
                         d_create=D.before(c),
                         d_win=D.mean(c, wend) - self_share,
                         d_life=(D.mean(c, u) - 1.0) if soj > 0 else float(D.before(c)),
                         slope=D.at(wend) - D.at(c)))
    return D, recs, dropped_edge


def today_sample(rows, asof):
    """[(sojourn_min, completed)] for rows created on the snapshot's own date."""
    out = []
    for r in rows:
        c = ts(r["createdAt"])
        if c.date() != asof.date():
            continue
        term = r.get("status") in TERMINAL
        u = ts(r["updatedAt"]) if term else asof
        soj = (u - c).total_seconds() / 60.0
        if soj >= 0:
            out.append((soj, term))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--window", type=float, default=15.0,
                    help="minutes of ambient depth a fresh row is judged by")
    ap.add_argument("--close", default="17:00")
    ap.add_argument("--bucket", type=int, default=8,
                    help="d_create floor for the slope experiment")
    a = ap.parse_args()

    rows, asof = load(a.snapshot)
    hh, mm = (int(x) for x in a.close.split(":"))
    close = asof.replace(hour=hh, minute=mm, second=0, microsecond=0)
    W = a.window

    print("=" * 78)
    print("R129-Q  DEPTH-BIAS CORRECTION -- measuring the caveat I published")
    print("=" * 78)
    print(f"snapshot           : {a.snapshot}")
    print(f"snapshot as-of     : {asof.isoformat()}   rows {len(rows)}")
    print(f"close              : {close.isoformat()}")
    print(f"ambient window W   : {W:.0f} min")

    # ---- per-row covariates -------------------------------------------------
    D, recs, dropped_edge = build(rows, asof, W)
    done = [x for x in recs if x["done"] and x["soj"] > 0]
    print(f"usable rows        : {len(recs)} ({len(done)} completed), "
          f"{dropped_edge} dropped because [created, created+W] runs past the snapshot")

    # ---- which covariate tracks sojourn? -----------------------------------
    ls = [x["soj"] for x in done]
    print()
    print("-- rank correlation with sojourn (completed rows only) --------------")
    for key, label, note in [
            ("d_create", "d_create", "predetermined; what my published KM used"),
            ("d_win", f"d_win(W={W:.0f})", "fixed window; needs a depth forecast"),
            ("d_life", "d_life", "ENDOGENOUS upper bound, not a predictor")]:
        rho = spearman([x[key] for x in done], ls)
        print(f"  {label:<14} rho = {rho:+.3f}   {note}")

    # ---- the experiment that decides the caveat ----------------------------
    B = [x for x in done if x["d_create"] >= a.bucket]
    print()
    print(f"-- within d_create >= {a.bucket} (n={len(B)}), split by queue SLOPE over "
          f"first {W:.0f} min --")
    groups = {
        "rising  (slope >= +2)": [x for x in B if x["slope"] >= 2],
        "flat    (|slope| <= 1)": [x for x in B if abs(x["slope"]) <= 1],
        "falling (slope <= -2)": [x for x in B if x["slope"] <= -2],
    }
    med = {}
    for name, g in groups.items():
        if not g:
            print(f"  {name:<22} n=0")
            continue
        s = sorted(x["soj"] for x in g)
        med[name] = statistics.median(s)
        p90 = s[min(len(s) - 1, int(0.9 * len(s)))]
        print(f"  {name:<22} n={len(g):<4} median {med[name]:6.1f} min   "
              f"p90 {p90:6.1f}   mean d_create {statistics.fmean([x['d_create'] for x in g]):4.1f}")
    rise = groups["rising  (slope >= +2)"]
    flat = groups["flat    (|slope| <= 1)"]
    if rise and flat:
        gap = med["rising  (slope >= +2)"] - med["flat    (|slope| <= 1)"]
        p = perm_p([x["soj"] for x in rise], [x["soj"] for x in flat])
        print(f"  => rising-minus-flat median sojourn gap: {gap:+.1f} min "
              f"at equal admission depth (permutation p = {p:.2f}, n_rising={len(rise)})")
        print("     THIS IS THE SIZE OF MY CAVEAT: a few minutes of median sojourn,")
        print("     not a regime change -- and with n_rising this small it is not even")
        print("     distinguishable from zero.  A rising queue is worth ~1-2 points of")
        print("     adjudication probability, so the caveat should stop being quoted as")
        print("     if it moved the deadline.")

    # ---- adjudication odds under both bucketings ---------------------------
    print()
    print("-- P(a fire at T is adjudicated before close): published vs corrected --")
    # NOTE: every still-resident row is given an artificial end at `asof`, so the
    # step function drops to 0 exactly at asof.  The live depth is the level
    # immediately BEFORE asof -- getting this wrong printed "in-flight 0" in my
    # first run, against a watcher that was reading 12.
    print(f"  global in-flight just before snapshot: {D.before(asof)} "
          f"(level AT asof is 0 by construction -- resident rows are censored there)")
    pub = [(x["soj"], x["done"]) for x in recs if x["d_create"] >= 10]
    cor = [(x["soj"], x["done"]) for x in recs if x["d_win"] >= 10]
    tod = [(x["soj"], x["done"]) for x in recs
           if x["d_create"] >= a.bucket and abs(x["slope"]) <= 1]
    kp, kc, kt = km(pub), km(cor), km(tod)
    print(f"  A published  d_create >= 10          : n={len(pub):<4} "
          f"KM median {q(kp, 0.5):6.1f} min")
    print(f"  B d_win      >= 10 (ambient-matched) : n={len(cor):<4} "
          f"KM median {q(kc, 0.5):6.1f} min")
    print(f"  C d_create >= {a.bucket} AND flat queue      : n={len(tod):<4} "
          f"KM median {q(kt, 0.5):6.1f} min   <-- matches today")
    print(f"  {'fire T':>8}  {'budget':>7}  {'A pub':>7}  {'B dwin':>7}  {'C today':>8}")
    base = asof.replace(second=0, microsecond=0)
    for k in range(0, 13):
        T = base + dt.timedelta(minutes=5 * k)
        if T > close:
            break
        budget = (close - T).total_seconds() / 60.0
        print(f"  {T.strftime('%H:%MZ'):>8}  {budget:7.0f}  "
              f"{100*(1-s_at(kp,budget)):6.1f}%  {100*(1-s_at(kc,budget)):6.1f}%  "
              f"{100*(1-s_at(kt,budget)):7.1f}%")
    for thr in (0.9, 0.8, 0.5):
        out = []
        for name, curve in (("A", kp), ("B", kc), ("C", kt)):
            last = None
            for k in range(0, 24 * 12):
                T = base + dt.timedelta(minutes=5 * k)
                if T > close:
                    break
                if 1 - s_at(curve, (close - T).total_seconds() / 60.0) >= thr:
                    last = T
            out.append(f"{name} {last.strftime('%H:%MZ') if last else 'past'}")
        print(f"  latest fire holding >= {100*thr:.0f}%:  " + "   ".join(out))

    # is the A-vs-B gap real, or is it one row in a 50-row bucket?
    probe = base + dt.timedelta(minutes=35)
    bud = (close - probe).total_seconds() / 60.0
    print()
    print(f"  POWER CHECK at a {probe.strftime('%H:%MZ')} fire (budget {bud:.0f} min), "
          f"90% bootstrap intervals:")
    ci = {}
    for name, s in (("A published d_create>=10", pub), ("B d_win>=10", cor),
                    ("C flat-queue, today", tod)):
        lo, hi = boot_p_at(s, bud)
        ci[name] = (lo, hi)
        print(f"    {name:<26} n={len(s):<4} P = {100*(1-s_at(km(s),bud)):5.1f}%  "
              f"[{100*lo:.1f}, {100*hi:.1f}]")
    (alo, ahi), (blo, bhi) = ci["A published d_create>=10"], ci["B d_win>=10"]
    overlap = not (ahi < blo or bhi < alo)
    if overlap:
        print("    A and B intervals OVERLAP => B is not a distinguishable correction")
        print("    to A; I do not adopt it, and I keep quoting A as the deadline curve.")
    else:
        print("    A and B intervals are DISJOINT => the ambient-depth bucketing is a")
        print("    real correction and my published curve A should be replaced by B.")

    # A "correction" that is really an era effect is the exact mistake that
    # wrecked my r109f noise identification (rho = -12.6, an impossibility).
    # Before adopting B over A, check WHICH DAYS each bucket is made of.
    print()
    print("-- is the A-vs-B gap depth, or is it an ERA CONFOUND? ---------------")
    setA = {x["id"] for x in recs if x["d_create"] >= 10}
    setB = {x["id"] for x in recs if x["d_win"] >= 10}
    print(f"  |A| = {len(setA)}   |B| = {len(setB)}   |A and B| = {len(setA & setB)}   "
          f"|B only| = {len(setB - setA)}")
    by_day = {}
    for x in recs:
        day = x["c"].strftime("%m-%d")
        inA = x["d_create"] >= 10
        inB = x["d_win"] >= 10
        if not (inA or inB):
            continue
        d = by_day.setdefault(day, {"A": [], "B": []})
        if inA:
            d["A"].append(x)
        if inB:
            d["B"].append(x)
    print(f"  {'day':>6}  {'nA':>4} {'medA':>6}  {'nB':>4} {'medB':>6}")
    for day in sorted(by_day):
        g = by_day[day]
        mA = statistics.median([x["soj"] for x in g["A"]]) if g["A"] else float("nan")
        mB = statistics.median([x["soj"] for x in g["B"]]) if g["B"] else float("nan")
        print(f"  {day:>6}  {len(g['A']):>4} {mA:6.1f}  {len(g['B']):>4} {mB:6.1f}")
    both = [d for d in by_day if by_day[d]["A"] and by_day[d]["B"]]
    if both:
        diffs = [statistics.median([x["soj"] for x in by_day[d]["B"]])
                 - statistics.median([x["soj"] for x in by_day[d]["A"]]) for d in both]
        print(f"  WITHIN-DAY B-minus-A median sojourn, over {len(both)} shared days: "
              f"mean {statistics.fmean(diffs):+.1f} min, "
              f"median {statistics.median(diffs):+.1f} min")
        print("  If the pooled gap survives day-by-day it is depth; if it collapses")
        print("  here, B is just a different slice of the calendar and A stands.")

    # The era table is not just a hygiene check: it says TODAY is slower than the
    # pooled history at equal depth.  My published curve A pools an 18-day
    # history in which one fast day (07-29) supplies most of the deep-queue rows,
    # so A is optimistic FOR TODAY -- and that is a bigger correction than the
    # rising-queue caveat I actually published, in the opposite direction.
    print()
    print("-- TODAY-ONLY curve: the population the next fire actually joins ------")
    today = today_sample(rows, asof)
    ncen = sum(1 for _, t in today if not t)
    kd = km(today)
    print(f"  rows created {asof.date()}: n={len(today)} ({ncen} still resident, "
          f"censored at their current age)")
    mt = q(kd, 0.5)
    print(f"  KM median sojourn today: {mt:.1f} min   "
          f"vs {q(kp,0.5):.1f} min for my published bucket A")
    print(f"  {'fire T':>8}  {'budget':>7}  {'A pub':>7}  {'D today-only':>13}  {'shift':>7}")
    for k in range(0, 13):
        T = base + dt.timedelta(minutes=5 * k)
        if T > close:
            break
        bg = (close - T).total_seconds() / 60.0
        pa, pd = 1 - s_at(kp, bg), 1 - s_at(kd, bg)
        print(f"  {T.strftime('%H:%MZ'):>8}  {bg:7.0f}  {100*pa:6.1f}%  "
              f"{100*pd:12.1f}%  {100*(pd-pa):+6.1f}")
    for thr in (0.9, 0.8, 0.5):
        out = []
        for name, curve in (("A", kp), ("D", kd)):
            last = None
            for k in range(0, 24 * 12):
                T = base + dt.timedelta(minutes=5 * k)
                if T > close:
                    break
                if 1 - s_at(curve, (close - T).total_seconds() / 60.0) >= thr:
                    last = T
            out.append(f"{name} {last.strftime('%H:%MZ') if last else 'past'}")
        print(f"  latest fire holding >= {100*thr:.0f}%:  " + "   ".join(out))
    lo, hi = boot_p_at(today, bud)
    pa = 1 - s_at(kp, bud)
    pd = 1 - s_at(kd, bud)
    print(f"  at a {probe.strftime('%H:%MZ')} fire: today-only P = {100*pd:.1f}% "
          f"[{100*lo:.1f}, {100*hi:.1f}] vs published A {100*pa:.1f}%")
    if hi < pa:
        print("  => TODAY IS SIGNIFICANTLY SLOWER than my published curve: the")
        print("     pooled-history curve A overstates the remaining draw's odds and")
        print("     the day effect, not the queue slope, is the correction that matters.")
    elif lo > pa:
        print("  => today is significantly FASTER than my published curve.")
    else:
        print("  => today is not distinguishable from my published curve; A stands.")

    print()
    print("-- limits, stated so nobody has to find them for me -----------------")
    print("  * d_win partly POSTDATES admission, so it is not an ex-ante predictor;")
    print("    it is usable only through a forecast of the depth process.  The")
    print("    campaign's forecast right now is 'flat at 12', from eight watcher")
    print("    polls, so the corrected column is the one to read today.")
    print("  * the slope split is observational: whatever makes the global queue")
    print("    rise may also be what makes rows slow.  It bounds the bias, it does")
    print("    not explain it.")
    print(f"  * rows created within W={W:.0f} min of the snapshot are dropped, so the")
    print("    freshest arrivals -- including our own resident row -- are excluded")
    print("    by construction; this is a statement about the population, not it.")
    print("  * nothing here changes the SERIAL verdict, which rests on the overlap")
    print("    sweep, not on any sojourn model.")


if __name__ == "__main__":
    main()
