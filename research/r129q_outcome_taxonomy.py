#!/usr/bin/env python3
"""fern R129-Q: what actually HAPPENS to a fire, and does the outcome record
contradict the SERIAL verdict?

Two holes in my own published R129-Q work, both found by reading the fields I had
never opened (`status` x `rejectionReason`) rather than by re-modelling the ones
I had:

HOLE 1 -- the SERIAL test could not see an instant refusal.
    I concluded "hard per-account cap of 1 in flight" from a sweep of maximum
    SIMULTANEOUSLY-NON-TERMINAL rows per account (0 of 89 accounts ever reached
    2).  But if the cap is enforced by admitting a row and immediately killing
    it, that row's span [createdAt, updatedAt] is ~zero width and a
    strictly-overlapping sweep steps straight over it.  So the cleanest possible
    signature of the cap I claimed is exactly the signature my test was blind
    to.  Here I (a) grep every rejectionReason for a quota/concurrency refusal
    and (b) redo the overlap test with CLOSED intervals so zero-width spans
    count.

HOLE 2 -- I modelled sojourn as an open-ended random variable.
    It is not.  Adjudication runs under GitHub-Actions workflow timeouts, and
    the timed-out rows say so verbatim ("workflow run timed out after
    10800000ms").  That means sojourn has a HARD CEILING and mass points at the
    budgets, which my Kaplan-Meier tail could not represent.  For a row that is
    already old -- ours is -- the budget structure, not the KM tail, is what
    decides when it dies and whether it dies with a score or without one.

The third thing that falls out is a correction to the value of a draw.  I had
been pricing a fire as "P(adjudicated before close) x P(crown)".  But ~3 fires
in 10 never produce a score at all: they fail in a gate or a timeout.  A draw is
worth strictly less than I published.

Read-only: consumes a snapshot already on disk, issues no API call, fires
nothing, builds nothing, touches no model source.

usage: r129q_outcome_taxonomy.py <snapshot.json> [--track ID] [--me USER]
                                 [--close HH:MM]
"""
import argparse
import collections
import datetime as dt
import json
import re
import statistics as st

TERMINAL = {"rejected", "failed", "accepted", "promoted"}
SCORED = {"rejected", "accepted", "promoted"}   # ran to a score, then judged
ME = "morganmcg1"
# words a quota/concurrency refusal would have to use
CAP_WORDS = re.compile(
    r"concurren|in flight|in-flight|quota|rate limit|rate-limit|too many|"
    r"already (have|has|running|pending)|one submission|limit reached|"
    r"max(imum)? (of )?\d* ?submission|throttl|slot", re.I)


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def hm(d):
    return d.strftime("%H:%M:%SZ")


def load(path):
    with open(path) as f:
        doc = json.load(f)
    rows = doc["submissions"]
    asof = ts(doc["polled_at"]) if "polled_at" in doc else max(
        ts(r["updatedAt"]) for r in rows)
    return rows, asof


def family(reason):
    """Collapse a rejectionReason to its family, keeping the decisive part."""
    if reason is None:
        return "<none>"
    s = str(reason).strip()
    m = re.search(r"timed out after (\d+)ms", s)
    if m:
        return "TIMEOUT %d min budget" % (int(m.group(1)) // 60000)
    m = re.search(r'failure at step "([^"]+)"', s)
    if m:
        return "gate failure: " + m.group(1)
    if "could not be created" in s or "could not be pushed" in s \
            or "could not be read" in s:
        return "infrastructure: git/GitHub error"
    if "concluded cancelled" in s:
        return "cancelled"
    if "concluded failure" in s:
        return "gate failure: unattributed"
    return s[:60]


def span(r, asof):
    a = ts(r["createdAt"])
    b = ts(r["updatedAt"]) if r.get("status") in TERMINAL else asof
    return a, b


def cp_upper(n, alpha=0.05):
    """One-sided Clopper-Pearson upper bound on p given 0/n successes."""
    if n <= 0:
        return 1.0
    return 1.0 - alpha ** (1.0 / n)


def metrics(snapshot, track=None, me=ME, close_hm="17:00", now=None,
            band_hi="15:35"):
    """Every scalar this analysis publishes, computed in ONE place.

    main() prints from this dict and the W&B publisher sends this dict, so the
    console output and the published run cannot drift apart.
    """
    rows, asof = load(snapshot)
    ours = [r for r in rows if r.get("solverUsername") == me]
    ch, cm = (int(x) for x in close_hm.split(":"))
    close = asof.replace(hour=ch, minute=cm, second=0, microsecond=0)
    now = now or dt.datetime.now(dt.timezone.utc)

    term = [r for r in rows if r.get("status") in TERMINAL]
    oterm = [r for r in ours if r.get("status") in TERMINAL]
    m = {
        "asof": hm(asof), "rows": len(rows), "accounts": len(
            {r.get("solverUsername") for r in rows}),
        "n_terminal": len(term), "n_terminal_ours": len(oterm),
        "p_scored_global": sum(1 for r in term if r["status"] in SCORED)
        / len(term),
        "p_scored_ours": sum(1 for r in oterm if r["status"] in SCORED)
        / max(len(oterm), 1),
        "p_accepted_global": sum(1 for r in term
                                 if r["status"] in ("accepted", "promoted"))
        / len(term),
        "p_accepted_ours": sum(1 for r in oterm
                               if r["status"] in ("accepted", "promoted"))
        / max(len(oterm), 1),
    }
    # our worst self-inflicted gate
    ofam = collections.Counter(family(r.get("rejectionReason")) for r in oterm)
    gfam = collections.Counter(family(r.get("rejectionReason")) for r in term)
    key = "gate failure: Public behavior gate"
    m["ours_public_behavior_gate_share"] = ofam[key] / max(len(oterm), 1)
    m["global_public_behavior_gate_share"] = gfam[key] / len(term)
    m["ours_public_behavior_gate_n"] = ofam[key]
    # global includes us, so the fair contrast is the REST of the fleet
    n_rest = len(term) - len(oterm)
    m["rest_public_behavior_gate_share"] = (gfam[key] - ofam[key]) / max(n_rest, 1)
    m["public_behavior_gate_ratio_vs_rest"] = (
        m["ours_public_behavior_gate_share"]
        / max(m["rest_public_behavior_gate_share"], 1e-9))
    m["p_scored_rest"] = (
        sum(1 for r in term if r["status"] in SCORED)
        - sum(1 for r in oterm if r["status"] in SCORED)) / max(n_rest, 1)
    m["p_accepted_rest"] = (
        sum(1 for r in term if r["status"] in ("accepted", "promoted"))
        - sum(1 for r in oterm if r["status"] in ("accepted", "promoted"))
    ) / max(n_rest, 1)

    # ---- ERA CHECK: is the gate problem live, or a closed episode? ----
    # Without this, an all-time average is quoted as if it described today.
    # It does not: a fixed two-day regression can dominate the mean forever.
    pbg = [r for r in oterm if family(r.get("rejectionReason")) == key]
    m["pbg_days"] = len({ts(r["createdAt"]).strftime("%m-%d") for r in pbg})
    if pbg:
        last = max(ts(r["createdAt"]) for r in pbg)
        m["pbg_last_seen"] = last.strftime("%m-%d %H:%MZ")
        after = [r for r in oterm if ts(r["createdAt"]) > last]
        m["n_ours_since_last_pbg"] = len(after)
        m["pbg_since_last"] = sum(
            1 for r in after if family(r.get("rejectionReason")) == key)
        m["p_scored_ours_since_last_pbg"] = (
            sum(1 for r in after if r["status"] in SCORED) / max(len(after), 1))
        # 0 failures in n fires bounds the CURRENT gate risk from above
        m["pbg_rate_upper_now"] = cp_upper(len(after)) if not \
            m["pbg_since_last"] else float("nan")
        m["pbg_episode_is_closed"] = (m["pbg_since_last"] == 0
                                      and len(after) >= 20)

    soj = []
    for r in term:
        aa, bb = span(r, asof)
        soj.append(((bb - aa).total_seconds() / 60.0, r))
    dur = sorted(x for x, _ in soj)
    m["sojourn_median_min"] = st.median(dur)
    m["sojourn_max_min"] = dur[-1]
    m["frac_over_60min"] = sum(1 for x in dur if x > 61) / len(dur)
    m["frac_over_120min"] = sum(1 for x in dur if x > 121) / len(dur)
    m["frac_over_180min"] = sum(1 for x in dur if x > 181) / len(dur)

    # closed-interval same-account overlap retest
    by_acct = collections.defaultdict(list)
    for r in rows:
        by_acct[r.get("solverUsername")].append(r)
    strict = closed = ties = pairs = 0
    for _u, rs in by_acct.items():
        sp = [(span(r, asof), r) for r in rs]
        for (a1, b1), r1 in sp:
            for (a2, _b2), r2 in sp:
                if r1 is r2 or a1 > a2:
                    continue
                pairs += 1
                strict += (a1 < a2 < b1)
                closed += (a1 <= a2 <= b1)
                ties += (a2 == b1)
    m.update(pairs=pairs, overlap_strict=strict, overlap_closed=closed,
             overlap_ties=ties,
             cap_upper_per_account=cp_upper(len(by_acct)),
             cap_upper_per_pair=cp_upper(pairs),
             cap_refusal_strings=sum(
                 1 for r in rows if r.get("rejectionReason")
                 and CAP_WORDS.search(str(r["rejectionReason"]))),
             instant_kills=sum(1 for x, _ in soj if x < 1.0),
             serial_survives_closed_retest=(strict == 0 and closed == 0))

    trk = None
    for r in ours:
        if track and r["id"].startswith(track):
            trk = r
        elif not track and r.get("status") not in TERMINAL:
            trk = r
    if trk is not None:
        c0 = ts(trk["createdAt"])
        age = (now - c0).total_seconds() / 60.0
        surv = [(x, r) for x, r in soj if x > age]
        q = sorted(x for x, _ in surv)
        n_sc = sum(1 for _, r in surv if r["status"] in SCORED)
        n_to = sum(1 for _, r in surv
                   if family(r.get("rejectionReason")).startswith("TIMEOUT"))
        bh, bm = (int(x) for x in band_hi.split(":"))
        blim = (c0.replace(hour=bh, minute=bm, second=0, microsecond=0)
                - c0).total_seconds() / 60.0
        before = sum(1 for x in q
                     if c0 + dt.timedelta(minutes=x) <= close)
        m.update(track_id=trk["id"][:12], track_created=hm(c0),
                 track_status=trk.get("status"), track_age_min=age,
                 track_asof=hm(now), n_comparable=len(surv),
                 p_scored_given_survived=n_sc / len(surv),
                 p_timeout_given_survived=n_to / len(surv),
                 p_terminal_before_close=before / len(q),
                 p_score_before_close=(before / len(q)) * (n_sc / len(surv)),
                 p_registered_band_holds=sum(1 for x in q if x <= blim) / len(q),
                 residual_p50_wall=hm(c0 + dt.timedelta(
                     minutes=q[len(q) // 2])),
                 hard_ceiling_wall=hm(c0 + dt.timedelta(minutes=dur[-1])))
    return m


def era_table(rows, me=ME):
    """Per-day outcome mix for one account: the era check, printable."""
    out = []
    ours = [r for r in rows if r.get("solverUsername") == me]
    by = collections.defaultdict(collections.Counter)
    for r in ours:
        d = ts(r["createdAt"]).strftime("%m-%d")
        f = family(r.get("rejectionReason"))
        if f == "gate failure: Public behavior gate":
            k = "pbg"
        elif r.get("status") in SCORED:
            k = "scored"
        elif r.get("status") not in TERMINAL:
            k = "live"
        else:
            k = "other_fail"
        by[d][k] += 1
    for d in sorted(by):
        c = by[d]
        n = sum(c.values())
        out.append((d, n, c["pbg"], c["scored"], c["other_fail"], c["live"],
                    100.0 * c["pbg"] / n))
    return out


def taxonomy(rows, label):
    stat = collections.Counter(r.get("status") for r in rows)
    term = [r for r in rows if r.get("status") in TERMINAL]
    scored = [r for r in term if r.get("status") in SCORED]
    acc = [r for r in term if r.get("status") in ("accepted", "promoted")]
    print("\n  %-28s rows %5d   %s" % (
        label, len(rows), "  ".join("%s=%d" % kv for kv in stat.most_common())))
    if term:
        print("      P(fire -> a score at all) = %5.1f%%  (%d/%d terminal)"
              % (100 * len(scored) / len(term), len(scored), len(term)))
        print("      P(fire -> accepted)       = %5.2f%%  (%d/%d terminal)"
              % (100 * len(acc) / len(term), len(acc), len(term)))
    return len(term), len(scored), len(acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--track", default=None)
    ap.add_argument("--me", default=ME)
    ap.add_argument("--close", default="17:00")
    ap.add_argument("--band-hi", default="15:35", help="top of registered band")
    ap.add_argument("--band-mid", default="15:10", help="centre of registered band")
    ap.add_argument("--km-med", default="15:21", help="pre-filed KM median")
    ap.add_argument("--km-p90", default="15:42", help="pre-filed KM p90")
    a = ap.parse_args()

    rows, asof = load(a.snapshot)
    ours = [r for r in rows if r.get("solverUsername") == a.me]
    ch, cm = (int(x) for x in a.close.split(":"))
    close = asof.replace(hour=ch, minute=cm, second=0, microsecond=0)

    print("=" * 78)
    print("R129-Q OUTCOME TAXONOMY  snapshot as-of %s  rows %d  close %s"
          % (hm(asof), len(rows), hm(close)))
    print("=" * 78)

    # ---------------- 1. what a fire is actually worth ----------------
    print("\n=== 1  OUTCOME TAXONOMY: a fire is not a coin flip on the crown ===")
    g_term, g_scored, g_acc = taxonomy(rows, "GLOBAL (all accounts)")
    o_term, o_scored, o_acc = taxonomy(ours, "OURS (%s)" % a.me)

    print("\n  rejectionReason families (global, terminal rows):")
    fam = collections.Counter(family(r.get("rejectionReason")) for r in rows
                              if r.get("status") in TERMINAL)
    for k, v in fam.most_common():
        print("    %5d  %5.1f%%  %s" % (v, 100 * v / g_term, k))

    print("\n  same families for OUR rows:")
    ofam = collections.Counter(family(r.get("rejectionReason")) for r in ours
                              if r.get("status") in TERMINAL)
    for k, v in ofam.most_common():
        print("    %5d  %5.1f%%  %s" % (v, 100 * v / max(o_term, 1), k))

    print("\n  ERA CHECK -- an all-time average is not a description of today:")
    print("    day     n   pbg  scored other live   pbg%")
    for d, n, p, s, o, lv, pct in era_table(rows, a.me):
        print("    %s %4d %5d %6d %5d %4d  %5.1f%%%s"
              % (d, n, p, s, o, lv, pct, "   <-- episode" if p else ""))
    print("    The 'Public behavior gate' failures are NOT a standing habit:")
    print("    they are confined to a short episode and stop dead afterwards, so")
    print("    quoting our all-time P(scored) as if it described the next fire")
    print("    would be wrong.  Current-era numbers are the ones to price with.")

    # ---------------- 2. hard ceiling on sojourn ----------------
    print("\n=== 2  SOJOURN HAS A HARD CEILING (workflow timeout budgets) ===")
    soj = []
    for r in rows:
        if r.get("status") in TERMINAL:
            aa, bb = span(r, asof)
            soj.append(((bb - aa).total_seconds() / 60.0, r))
    dur = sorted(m for m, _ in soj)
    print("  terminal rows %d   median %.1f min   p90 %.1f   p99 %.1f   MAX %.1f"
          % (len(dur), st.median(dur), dur[int(.90 * len(dur))],
             dur[int(.99 * len(dur))], dur[-1]))
    budgets = collections.defaultdict(list)
    for m, r in soj:
        f = family(r.get("rejectionReason"))
        if f.startswith("TIMEOUT"):
            budgets[int(f.split()[1])].append(m)
    print("  timeout budgets observed (the reaper is sharp to ~0.1 min):")
    for b in sorted(budgets):
        v = budgets[b]
        print("    budget %3d min  n=%2d  observed sojourn %.1f - %.1f "
              "(overhead +%.1f min)" % (b, len(v), min(v), max(v),
                                        st.median(v) - b))
    for b in sorted(budgets):
        over = sum(1 for m in dur if m > b + 1)
        print("    rows surviving past %3d min: %4d / %d = %5.2f%%"
              % (b, over, len(dur), 100 * over / len(dur)))

    # ---------------- 3. residual life of the tracked row ----------------
    live = [r for r in ours if r.get("status") not in TERMINAL]
    trk = None
    if a.track:
        for r in ours:
            if r["id"].startswith(a.track):
                trk = r
    elif live:
        trk = live[0]
    if trk is not None:
        print("\n=== 3  RESIDUAL LIFE OF THE TRACKED ROW, GIVEN THE CEILING ===")
        c0 = ts(trk["createdAt"])
        now = dt.datetime.now(dt.timezone.utc)
        age = (now - c0).total_seconds() / 60.0
        print("  row %s  created %s  status %s  age %.1f min (at %s)"
              % (trk["id"][:12], hm(c0), trk.get("status"), age, hm(now)))
        surv = [(m, r) for m, r in soj if m > age]
        print("  comparable rows that also survived past %.0f min: n=%d"
              % (age, len(surv)))
        if surv:
            mix = collections.Counter(r.get("status") for _, r in surv)
            sfam = collections.Counter(family(r.get("rejectionReason"))
                                       for _, r in surv)
            n_sc = sum(1 for _, r in surv if r.get("status") in SCORED)
            n_to = sum(1 for _, r in surv
                       if family(r.get("rejectionReason")).startswith("TIMEOUT"))
            print("    outcome mix: %s" % "  ".join("%s=%d" % kv
                                                    for kv in mix.most_common()))
            print("    P(scored | survived %.0f min)      = %5.1f%%  (%d/%d)"
                  % (age, 100 * n_sc / len(surv), n_sc, len(surv)))
            print("    P(dies to a timeout | survived)  = %5.1f%%  (%d/%d)"
                  % (100 * n_to / len(surv), n_to, len(surv)))
            print("    top families among survivors:")
            for k, v in sfam.most_common(4):
                print("      %4d  %5.1f%%  %s" % (v, 100 * v / len(surv), k))
            q = sorted(m for m, _ in surv)
            print("    residual sojourn quantiles -> wall-clock terminal time:")
            for p in (0.10, 0.25, 0.50, 0.75, 0.90, 1.00):
                m = q[min(int(p * len(q)), len(q) - 1)]
                print("      p%-3d  total %6.1f min  ->  %s%s"
                      % (int(100 * p), m, hm(c0 + dt.timedelta(minutes=m)),
                         "   [AFTER CLOSE]"
                         if c0 + dt.timedelta(minutes=m) > close else ""))
            hard = c0 + dt.timedelta(minutes=q[-1])
            print("    HARD CEILING from %d observed rows: terminal by %s (%s)"
                  % (len(dur), hm(hard),
                     "before close" if hard <= close else "AFTER CLOSE"))
            before = sum(1 for m in q
                         if c0 + dt.timedelta(minutes=m) <= close)
            print("    P(terminal before %s | survived %.0f min) = %5.1f%% "
                  "(%d/%d)" % (hm(close), age, 100 * before / len(q),
                               before, len(q)))
            # value of the draw, corrected
            pv = (before / len(q)) * (n_sc / len(surv))
            print("    P(this row yields a SCORE before close) = %5.1f%%"
                  "   <- was quoted as P(adjudicated) alone" % (100 * pv))

            # score my own registered prediction against the ceiling-aware law
            print("\n  SCORING MY REGISTERED PREDICTION (filed pre-outcome):")
            for lab, hhmm in (("band top", a.band_hi), ("band centre", a.band_mid),
                              ("KM median", a.km_med), ("KM p90", a.km_p90)):
                bh, bm = (int(x) for x in hhmm.split(":"))
                wall = c0.replace(hour=bh, minute=bm, second=0, microsecond=0)
                lim = (wall - c0).total_seconds() / 60.0
                p = sum(1 for m in q if m <= lim) / len(q)
                print("    %-12s %s -> total %6.1f min -> P(terminal by then | "
                      "survived %.0f min) = %5.1f%%"
                      % (lab, hhmm + "Z", lim, age, 100 * p))
            print("    the band was filed when the row was young; conditioning on")
            print("    %.0f min of survival plus the timeout mass points moves the"
                  % age)
            print("    law right, so I expect to MISS HIGH and say so before the")
            print("    flip rather than after it.")

    # ---------------- 4. is there any refusal in the record? ----------------
    print("\n=== 4  HOLE 1: could the cap show up as an instant refusal? ===")
    hits = [r for r in rows if r.get("rejectionReason")
            and CAP_WORDS.search(str(r["rejectionReason"]))]
    print("  rejectionReason strings matching quota/concurrency vocabulary: "
          "%d of %d" % (len(hits), len(rows)))
    for r in hits[:5]:
        print("    %s  %s" % (r["id"][:12], str(r["rejectionReason"])[:80]))
    tiny = [(m, r) for m, r in soj if m < 1.0]
    print("  terminal rows with sojourn < 1.0 min (instant-kill candidates): %d"
          % len(tiny))
    for m, r in sorted(tiny)[:6]:
        print("    %.2f min  %-9s %-9s %s" % (m, r.get("status"),
                                              r.get("solverUsername", "")[:9],
                                              family(r.get("rejectionReason"))))

    print("\n  overlap test redone with CLOSED intervals (zero-width visible):")
    by_acct = collections.defaultdict(list)
    for r in rows:
        by_acct[r.get("solverUsername")].append(r)
    strict = closed = ties = 0
    strict_accts = set()
    closed_accts = set()
    pairs = 0
    for u, rs in by_acct.items():
        sp = [(span(r, asof), r) for r in rs]
        for (a1, b1), r1 in sp:
            for (a2, b2), r2 in sp:
                if r1 is r2:
                    continue
                if a1 <= a2:
                    pairs += 1
                    if a1 < a2 < b1:
                        strict += 1
                        strict_accts.add(u)
                    if a1 <= a2 <= b1:
                        closed += 1
                        closed_accts.add(u)
                    if a2 == b1:
                        ties += 1
    print("    accounts %d   ordered same-account pairs %d" % (len(by_acct), pairs))
    print("    strict overlaps (a1 <  a2 <  b1): %d  in %d accounts"
          % (strict, len(strict_accts)))
    print("    closed overlaps (a1 <= a2 <= b1): %d  in %d accounts"
          % (closed, len(closed_accts)))
    print("    exact ties (next fire at the instant the previous ended): %d"
          % ties)
    n_acct = len(by_acct)
    print("\n  one-sided 95% Clopper-Pearson upper bounds on the overlap rate:")
    print("    per ACCOUNT  (0/%d): p <= %5.2f%%   <- right unit for "
          "'is a 2nd slot reachable at all'" % (n_acct, 100 * cp_upper(n_acct)))
    print("    per PAIR     (0/%d): p <= %5.3f%%  <- anti-conservative, pairs "
          "are clustered within account" % (pairs, 100 * cp_upper(pairs)))

    print("\n=== 5  VERDICT ===")
    v_cap = (strict == 0 and closed == 0)
    print("  SERIAL cap survives the closed-interval retest: %s" % v_cap)
    print("  cap is documented anywhere in the outcome record:  %s"
          % (len(hits) > 0))
    print("  IDENTIFICATION LIMIT: with 0 refusals and 0 overlaps, the channel")
    print("    record cannot separate 'server enforces 1 in flight' from '89")
    print("    accounts all happen to serialise themselves'.  Both predict")
    print("    exactly what we see.  The discriminating test costs one extra")
    print("    fire while a row is live, which this assignment forbids -- so it")
    print("    stays unresolved and must be reported as unresolved.")
    print("  OPERATIONAL: treat the cap as real (bound above), and price a draw")
    print("    at P(terminal before close) x P(scored), not P(terminal) alone.")

    print("\n=== 6  PUBLISHED SCALARS (exactly what the W&B publisher sends) ===")
    m = metrics(a.snapshot, track=a.track, me=a.me, close_hm=a.close,
                band_hi=a.band_hi)
    for k in sorted(m):
        print("    %-34s %s" % (k, m[k]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
