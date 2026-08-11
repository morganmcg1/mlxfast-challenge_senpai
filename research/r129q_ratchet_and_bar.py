#!/usr/bin/env python3
"""fern R129-Q addendum: what does a fire have to BEAT, and is the target moving?

Every value-of-a-draw number I have published today priced the *channel*: will
the row be adjudicated before 17:00Z, will it produce a score at all.  None of
them priced the *target*.  I had been quoting "per-draw crown probability
1.5-2%" from a noise model of our own score distribution around our own best
receipt.  That model never touched the leaderboard record itself.

This script opens the four snapshot fields I had never read -- `officialScore`,
`claimedScore`, `improved`, `promotionStatus` -- and asks three questions that
the channel work cannot answer:

Q-A  What does `accepted` mean?  Is it "a good submission" or something much
     narrower?  And is the comparison made when the row is FIRED or when it is
     ADJUDICATED?  Those differ operationally: if the bar is read at
     adjudication time, a competitor's record landing during our validation
     silently raises the bar under our own live row.

Q-B  Is the bar moving?  A ratchet that advanced 29 times in one day is a very
     different opponent from one that has advanced once in three days.

Q-C  Model-free crown probability.  Instead of a Gaussian around our best, ask
     the record itself: historically, what fraction of fires beat the standing
     best by at least the margin we currently need?  If that number disagrees
     with my published 1.5-2%, the published number is the one that has to move,
     because this one has no model in it.

Read-only: consumes a snapshot already on disk, issues no API call, fires
nothing, builds nothing, benchmarks nothing, touches no model source.

usage: r129q_ratchet_and_bar.py <snapshot.json> [--me USER] [--close HH:MM]
                                [--asof ISO] [--our-tree-score FLOAT]
                                [--era-start YYYY-MM-DD]
"""
import argparse
import collections
import datetime as dt
import itertools
import json

ME = "morganmcg1"
TERMINAL = {"rejected", "failed", "accepted", "promoted"}
SCORED = {"rejected", "accepted", "promoted"}


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def hm(d):
    return d.strftime("%H:%MZ")


def cp_upper(k, n, alpha=0.05):
    """one-sided upper Clopper-Pearson bound on a rate, bisection on Binom CDF."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0

    def cdf(p):
        # P(X <= k) for X ~ Bin(n, p)
        tot, term = 0.0, (1.0 - p) ** n
        for i in range(0, k + 1):
            tot += term
            term *= (n - i) / (i + 1) * (p / (1.0 - p)) if p < 1 else 0.0
        return tot

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def load(path):
    d = json.load(open(path))
    rows = d["submissions"] if isinstance(d, dict) and "submissions" in d else d
    return rows


def scored_rows(rows):
    """rows that reached a score, ordered by adjudication time."""
    s = [x for x in rows if x.get("officialScore") is not None]
    s.sort(key=lambda x: x["updatedAt"])
    return s


def ratchet(rows, order="updatedAt"):
    """running prior global max before each scored row, in `order` order.

    Returns list of (row, prior_max, rel_delta) with prior_max finite.
    """
    s = [x for x in rows if x.get("officialScore") is not None]
    s.sort(key=lambda x: x[order])
    pri = list(itertools.accumulate(
        (x["officialScore"] for x in s), max, initial=float("-inf")))[:-1]
    return [(x, p, (x["officialScore"] - p) / p if p > 0 else None)
            for x, p in zip(s, pri)]


def semantics(rows):
    """Q-A: is `improved` == 'beat the global best', and at which epoch?"""
    out = {}
    for order in ("updatedAt", "createdAt"):
        z = ratchet(rows, order)
        agree = sum(1 for x, p, _ in z if bool(x["improved"]) == (x["officialScore"] > p))
        out["agree_" + order] = agree
        out["n_" + order] = len(z)
    z = ratchet(rows, "updatedAt")
    out["anomalies"] = [
        {"id": x["id"][:8], "at": x["updatedAt"], "score": x["officialScore"],
         "prior_max": None if p == float("-inf") else p, "improved": bool(x["improved"])}
        for x, p, _ in z if bool(x["improved"]) != (x["officialScore"] > p)]
    # does `improved` instead track the ACCOUNT's own prior best?
    best = {}
    acct_agree = 0
    for x in scored_rows(rows):
        u = x["solverUsername"]
        prev = best.get(u, float("-inf"))
        if bool(x["improved"]) == (x["officialScore"] > prev):
            acct_agree += 1
        best[u] = max(prev, x["officialScore"])
    out["agree_account_best"] = acct_agree
    st = collections.Counter(x["status"] for x in rows)
    out["status_counts"] = dict(st)
    out["improved_true"] = sum(1 for x in rows if x.get("improved"))
    out["accepted"] = st.get("accepted", 0)
    out["promoted"] = sum(1 for x in rows if x.get("promotionStatus") == "promoted")
    out["promotion_failed"] = [x.get("promotionReason") for x in rows
                              if x.get("promotionStatus") == "failed"]
    out["claimed_non_null"] = sum(1 for x in rows if x.get("claimedScore") is not None)
    out["official_non_null"] = sum(1 for x in rows if x.get("officialScore") is not None)
    return out


def advances(rows):
    return sorted([x for x in rows if x.get("improved")], key=lambda x: x["updatedAt"])


def bar_now(rows):
    a = advances(rows)
    return a[-1] if a else None


def per_day_advances(rows):
    return collections.Counter(x["updatedAt"][:10] for x in advances(rows))


def hazard(rows, asof, close, era_days=(1, 3, 5)):
    """Q-B: P(the bar rises again before close), per era window.

    Two independent routes:
      (i) calendar rate  -- advances per minute over the last D days -> Poisson
     (ii) per-fire rate  -- P(a scored fire is an advance) in the era, times the
          number of currently-resident rows that can still adjudicate before
          close.  Route (ii) is the one that knows about the in-flight queue.
    """
    win = (close - asof).total_seconds() / 60.0
    a = advances(rows)
    inflight = [x for x in rows if x["status"] not in TERMINAL]
    out = {"window_min": win, "n_inflight": len(inflight)}
    for D in era_days:
        cut = asof - dt.timedelta(days=D)
        k = sum(1 for x in a if ts(x["updatedAt"]) >= cut)
        rate = k / (D * 1440.0)                      # advances per minute
        lam = rate * win
        out["cal_%dd" % D] = {
            "advances": k, "per_day": k / D, "lam": lam,
            "p_rise": 1.0 - pow(2.718281828459045, -lam)}
        z = [t for t in ratchet(rows) if ts(t[0]["updatedAt"]) >= cut]
        n, kk = len(z), sum(1 for t in z if t[0].get("improved"))
        p = kk / n if n else 0.0
        out["fire_%dd" % D] = {
            "scored_fires": n, "advances": kk, "p_per_fire": p,
            "p_per_fire_upper95": cp_upper(kk, n),
            "p_rise_from_inflight": 1.0 - (1.0 - p) ** len(inflight)}
    return out


def jump_rate(rows, need, era_start=None, me=ME):
    """Q-C: model-free P(a scored fire beats the standing best by >= need)."""
    z = [t for t in ratchet(rows) if t[2] is not None]
    def cut(sub):
        n = len(sub)
        k = sum(1 for t in sub if t[2] >= need)
        pos = sum(1 for t in sub if t[2] > 0)
        return {"n": n, "k": k, "rate": (k / n if n else 0.0),
                "rate_upper95": cp_upper(k, n),
                "any_positive": pos, "positive_rate": (pos / n if n else 0.0)}
    out = {"need": need, "all": cut(z)}
    if era_start:
        e = [t for t in z if t[0]["updatedAt"][:10] >= era_start]
        out["era"] = cut(e)
        out["era_start"] = era_start
        out["ours_era"] = cut([t for t in e if t[0]["solverUsername"] == me])
    out["ours"] = cut([t for t in z if t[0]["solverUsername"] == me])
    inc = sorted((t[2] for t in z if t[2] > 0), reverse=True)
    out["n_positive"] = len(inc)
    out["top_increments"] = inc[:10]
    out["max_increment"] = inc[0] if inc else None
    if era_start:
        out["era_increments"] = [t[2] for t in z
                                 if t[2] > 0 and t[0]["updatedAt"][:10] >= era_start]
    return out


def metrics(rows, asof, close, era_start, our_tree=None, me=ME):
    """single source of every published scalar."""
    sem = semantics(rows)
    b = bar_now(rows)
    bar = b["officialScore"]
    ours = [x for x in rows if x["solverUsername"] == me
            and x.get("officialScore") is not None]
    our_best = max(x["officialScore"] for x in ours)
    need_best = bar / our_best - 1.0
    m = {
        "rows": len(rows),
        "asof": asof.isoformat(),
        "close": close.isoformat(),
        # Q-A
        "improved_means_global_best_agree": sem["agree_updatedAt"],
        "improved_means_global_best_n": sem["n_updatedAt"],
        "improved_means_global_best_pct": 100.0 * sem["agree_updatedAt"] / sem["n_updatedAt"],
        "agree_if_compared_at_fire_time": sem["agree_createdAt"],
        "agree_if_compared_to_account_best": sem["agree_account_best"],
        "epoch_verdict": ("adjudication_time"
                          if sem["agree_updatedAt"] > sem["agree_createdAt"]
                          else "fire_time"),
        "accepted_rows": sem["accepted"],
        "improved_true": sem["improved_true"],
        "accepted_equals_improved": sem["accepted"] == sem["improved_true"],
        "claimed_score_non_null": sem["claimed_non_null"],
        # Q-B
        "bar": bar,
        "bar_owner": b["solverUsername"],
        "bar_row": b["id"][:8],
        "bar_set_at": b["updatedAt"],
        "bar_age_min": (asof - ts(b["updatedAt"])).total_seconds() / 60.0,
        "advances_total": len(advances(rows)),
        # Q-C
        "our_best": our_best,
        "our_best_at": max(ours, key=lambda x: x["officialScore"])["updatedAt"],
        "need_from_our_best_pct": 100.0 * need_best,
    }
    m["hazard"] = hazard(rows, asof, close)
    m["jump_best"] = jump_rate(rows, need_best, era_start, me)
    # bar-rise hazard: report the RANGE over both routes rather than one number,
    # because the calendar route and the in-flight route disagree by 3x and I
    # have no basis for preferring one.
    routes = [m["hazard"]["cal_%dd" % D]["p_rise"] for D in (1, 3, 5)]
    routes_if = [m["hazard"]["fire_%dd" % D]["p_rise_from_inflight"] for D in (1, 3, 5)]
    m["p_bar_rises_calendar_lo"] = min(routes)
    m["p_bar_rises_calendar_hi"] = max(routes)
    m["p_bar_rises_inflight_lo"] = min(routes_if)
    m["p_bar_rises_inflight_hi"] = max(routes_if)
    m["p_bar_rises_before_close_worst_route"] = max(routes + routes_if)
    if our_tree:
        m["our_tree_score"] = our_tree
        need_tree = bar / our_tree - 1.0
        m["need_from_our_tree_pct"] = 100.0 * need_tree
        m["jump_tree"] = jump_rate(rows, need_tree, era_start, me)
    # ---- the chain: crown from the last draw -------------------------------
    # ERA-FIRST, deliberately.  One result ago I published an 18-day average as
    # if it described today and had to retract it; the identical trap is live
    # here, because the bar is a RATCHET, so an all-time jump rate is measured
    # against bars far below today's.  The all-time figure is kept only as an
    # explicitly-labelled optimistic bound.
    m["p_scored_current_era_ours"] = 1.0     # 54/54 measured in prqj58j9
    m["p_adjudicated_published"] = 0.796     # E[.] from 6lpeg7oa
    m["p_crown_published_prior"] = 0.0175    # midpoint of my published 1.5-2%
    m["p_jump_alltime_optimistic"] = m["jump_best"]["all"]["rate"]
    m["p_jump_era_point"] = m["jump_best"]["era"]["rate"]
    m["p_jump_era_upper95"] = m["jump_best"]["era"]["rate_upper95"]
    m["era_jump_k"] = m["jump_best"]["era"]["k"]
    m["era_jump_n"] = m["jump_best"]["era"]["n"]
    m["p_crown_chain_alltime_optimistic"] = (m["p_adjudicated_published"]
                                             * m["p_scored_current_era_ours"]
                                             * m["p_jump_alltime_optimistic"])
    m["p_crown_chain_era_upper95"] = (m["p_adjudicated_published"]
                                      * m["p_scored_current_era_ours"]
                                      * m["p_jump_era_upper95"])
    m["published_prior_exceeds_era_ceiling"] = (
        m["p_crown_published_prior"] > m["p_crown_chain_era_upper95"])
    if our_tree:
        m["p_crown_tree_alltime_optimistic"] = m["jump_tree"]["all"]["rate"]
        m["p_crown_tree_era_upper95"] = m["jump_tree"]["era"]["rate_upper95"]
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--me", default=ME)
    ap.add_argument("--close", default="17:00")
    ap.add_argument("--asof", default=None,
                    help="ISO poll time; default = max updatedAt in snapshot")
    ap.add_argument("--our-tree-score", type=float, default=None)
    ap.add_argument("--era-start", default="2026-08-08")
    a = ap.parse_args()

    rows = load(a.snapshot)
    if a.asof:
        asof = ts(a.asof)
    else:
        asof = max(ts(x["updatedAt"]) for x in rows)
    hh, mm = (int(v) for v in a.close.split(":"))
    close = asof.replace(hour=hh, minute=mm, second=0, microsecond=0)

    m = metrics(rows, asof, close, a.era_start, a.our_tree_score, a.me)
    sem = semantics(rows)

    print("=== Q-A  WHAT DOES `accepted` MEAN? ===")
    print("rows %d   officialScore present %d   claimedScore present %d"
          % (m["rows"], sem["official_non_null"], sem["claimed_non_null"]))
    print("status:", sem["status_counts"])
    print("`improved`==True on %d rows; status==accepted on %d rows; equal: %s"
          % (m["improved_true"], m["accepted_rows"], m["accepted_equals_improved"]))
    print("promotionStatus promoted %d, failed %d %s"
          % (sem["promoted"], len(sem["promotion_failed"]), sem["promotion_failed"]))
    print("`improved` == (score > GLOBAL prior max):     %d/%d = %.2f%%"
          % (m["improved_means_global_best_agree"], m["improved_means_global_best_n"],
             m["improved_means_global_best_pct"]))
    print("  same test if the bar is read at FIRE time:  %d/%d"
          % (m["agree_if_compared_at_fire_time"], m["improved_means_global_best_n"]))
    print("  same test against the ACCOUNT's own best:   %d/%d"
          % (m["agree_if_compared_to_account_best"], m["improved_means_global_best_n"]))
    print("EPOCH VERDICT: the bar is read at %s" % m["epoch_verdict"])
    for an in sem["anomalies"]:
        print("  anomaly:", an)

    print()
    print("=== Q-B  IS THE BAR MOVING? ===")
    print("bar %.13f set by %s (row %s) at %s, age %.1f min"
          % (m["bar"], m["bar_owner"], m["bar_row"], m["bar_set_at"], m["bar_age_min"]))
    print("advances total %d" % m["advances_total"])
    pd = per_day_advances(rows)
    print("advances per day:", " ".join("%s=%d" % (k, pd[k]) for k in sorted(pd)))
    print("window to close: %.1f min, rows in flight now: %d"
          % (m["hazard"]["window_min"], m["hazard"]["n_inflight"]))
    for D in (1, 3, 5):
        c = m["hazard"]["cal_%dd" % D]
        f = m["hazard"]["fire_%dd" % D]
        print("  last %dd: %d advances (%.2f/day) -> P(rise before close)=%.1f%% "
              "| per-fire advance rate %d/%d=%.2f%% (<=%.2f%%) -> P(rise from %d in flight)=%.1f%%"
              % (D, c["advances"], c["per_day"], 100 * c["p_rise"],
                 f["advances"], f["scored_fires"], 100 * f["p_per_fire"],
                 100 * f["p_per_fire_upper95"], m["hazard"]["n_inflight"],
                 100 * f["p_rise_from_inflight"]))

    print()
    print("=== Q-C  MODEL-FREE CROWN PROBABILITY ===")
    print("our best receipt %.14f -> need +%.4f%% to take the bar"
          % (m["our_best"], m["need_from_our_best_pct"]))
    jb = m["jump_best"]
    print("historical fires that beat the standing best by >= that margin:")
    for lab in ("all", "era", "ours", "ours_era"):
        if lab in jb:
            c = jb[lab]
            print("  %-9s %4d/%-5d = %.3f%% (<=%.2f%% one-sided 95%%); any positive delta %d (%.1f%%)"
                  % (lab, c["k"], c["n"], 100 * c["rate"], 100 * c["rate_upper95"],
                     c["any_positive"], 100 * c["positive_rate"]))
    print("largest single record increment ever: +%.3f%%   (positives: %d)"
          % (100 * jb["max_increment"], jb["n_positive"]))
    print("top-10 increments (pct):", [round(100 * v, 3) for v in jb["top_increments"]])
    if "era_increments" in jb:
        print("increments since %s (%%):" % jb["era_start"],
              [round(100 * v, 3) for v in jb["era_increments"]])
    if "jump_tree" in m:
        jt = m["jump_tree"]
        print("our CURRENT TREE %.6f -> need +%.4f%%; historical rate %d/%d = %.3f%% (<=%.2f%%)"
              % (m["our_tree_score"], m["need_from_our_tree_pct"],
                 jt["all"]["k"], jt["all"]["n"], 100 * jt["all"]["rate"],
                 100 * jt["all"]["rate_upper95"]))

    print()
    print("=== PUBLISHED SCALARS (from metrics(), the publisher prints these too) ===")
    for k in ("improved_means_global_best_pct", "epoch_verdict", "bar",
              "our_best_at", "need_from_our_best_pct",
              "era_jump_k", "era_jump_n", "p_jump_era_upper95",
              "p_jump_alltime_optimistic", "p_crown_published_prior",
              "p_crown_chain_era_upper95", "published_prior_exceeds_era_ceiling",
              "p_bar_rises_before_close_worst_route"):
        print("  %-38s %s" % (k, m[k]))
    print("CHAIN, ERA-FIRST  P(crown from the last draw) <= P(adj) %.3f x "
          "P(scored|era) %.2f x P(jump)<=%.4f = <=%.4f  (<=%.2f%%)"
          % (m["p_adjudicated_published"], m["p_scored_current_era_ours"],
             m["p_jump_era_upper95"], m["p_crown_chain_era_upper95"],
             100 * m["p_crown_chain_era_upper95"]))
    print("  same chain on the ALL-TIME (ratchet-confounded, OPTIMISTIC) jump "
          "rate: %.2f%%" % (100 * m["p_crown_chain_alltime_optimistic"]))
    print("  my published per-draw crown prior was 1.5-2%% (mid %.2f%%): %s"
          % (100 * m["p_crown_published_prior"],
             "ABOVE the era ceiling, so unsupported"
             if m["published_prior_exceeds_era_ceiling"]
             else "inside the era ceiling"))
    print("  P(bar rises before close): calendar %.1f-%.1f%%, in-flight route "
          "%.1f-%.1f%%"
          % (100 * m["p_bar_rises_calendar_lo"], 100 * m["p_bar_rises_calendar_hi"],
             100 * m["p_bar_rises_inflight_lo"], 100 * m["p_bar_rises_inflight_hi"]))

    print()
    print("=== HONEST LIMITS ===")
    print("1. The jump rate pools 89 accounts with very different trees; it is the")
    print("   rate at which SOMEBODY's fire clears the standing bar, and our own")
    print("   sub-rate (`ours`) is the smaller, noisier, more relevant one.")
    print("2. Survivorship in the other direction: the bar is a ratchet, so the")
    print("   margin needed grew over the 18 days. Early fires faced a lower bar,")
    print("   which makes the pooled all-time rate OPTIMISTIC for today.")
    print("3. `--our-tree-score` is a locally normalised number, not an")
    print("   officialScore from this channel; treat that line as indicative.")
    print("4. P(rise from in flight) assumes the resident rows are exchangeable")
    print("   with the era's scored fires; it cannot see their contents.")
    print("5. Nothing here changes the SERIAL verdict or the 180.8-min ceiling.")


if __name__ == "__main__":
    main()
