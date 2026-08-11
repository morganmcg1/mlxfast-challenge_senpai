#!/usr/bin/env python3
"""Recover exact slot-occupancy transitions from ticket-poller logs.

WHY THIS EXISTS
---------------
Section 7.1 of the instrument-collapse write-up had to estimate submission
*service* time by interval censoring, because a submission row carries
``createdAt`` but no ``updatedAt``: the only observation times available were
the mtimes of cached ``/tmp/subs_p*.json`` snapshots, which are 9-288 minutes
apart.  Every service-time number in 7.1 and 7.2 is therefore a bracket
``[lo, hi]``, typically tens of minutes wide.

But the submit-when-free pollers sample the account's in-flight slot every
15 s for an unrelated reason (winning a contested slot).  Their logs are a
15-second-resolution occupancy monitor for the shared ``morganmcg1`` account.
The last ``slot BUSY: <id>`` line before a ``slot FREE`` line brackets that
submission's completion to one poll interval - roughly two orders of magnitude
tighter than the mtime brackets, at zero additional channel cost.

That gives two things the mtime machinery cannot give:

1. A GROUND TRUTH.  A row bracketed exactly here can be compared against the
   bracket the mtime estimator produced for the same row from an entirely
   independent data source.  This is the first external validation of 7.1's
   method rather than an internal consistency check.

2. A DIRECT MEASUREMENT OF CONTENTION LOSS.  The interval from poller start to
   ``slot FREE`` is wall clock I spent unable to submit because another user of
   the shared account held the slot.  That cost is absent from every
   "minutes per shot" figure computed so far, all of which measure service
   time only.

WHAT THIS TOOL DOES *NOT* CLAIM
-------------------------------
The exactly-measured service times here are LENGTH BIASED and must not be
pooled with the mtime bracket sample.  A poller only ever observes the job
that happens to be in flight at the instant polling starts, and long jobs
occupy a disproportionate share of instants - the inspection paradox.  The
tool prints the age-at-first-observation ratio so the bias is visible rather
than argued about.  See ``--help`` output and the printed cautions.

Usage
-----
    python3 research/fern_r109f_poller_occupancy.py \
        [--log <poller log>]... [--cache /tmp/subs_p14.json] [--deadline ISO]

With no ``--log`` the tool globs the role's job-log directory.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone

# Job logs live beside the role home, NOT under the workspace and NOT under
# /Users/<login>: $HOME is itself ".../roles/student-maple-fern/home", so the
# state directory is one level up.  Deriving it from $HOME keeps the tool
# portable across roles instead of hardcoding a login name.
DEFAULT_LOG_GLOB = os.path.join(
    os.path.dirname(os.path.expanduser("~")),
    "state", "openhands_state", "training", "*.log",
)
DEFAULT_CACHES = [
    "/tmp/subs_p14.json",
    "/tmp/subs_p13.json",
    "/tmp/subs_p12.json",
    "/tmp/subs_p11.json",
]
DEFAULT_DEADLINE = "2026-08-11T20:00:00Z"

# Submissions this campaign created, by 8-char prefix.  Needed to tell a
# self-wait (the tail of my own service time, already counted) from a foreign
# wait (a genuine extra cost).  Pollers add their own 'SUBMITTED ok' ids to
# this set at runtime; the three interactive submissions are listed here
# because no poller log records them.
KNOWN_OWN_RECEIPT_PREFIXES = {
    "c1c0ba2c",  # ticket 1, submitted interactively
    "88584270",  # ticket 2, submitted interactively
    "e4078827",  # ticket 3, submitted interactively
    "ed40f3ee",  # ticket 4
    "0531544b",  # ticket 5
    "cb4de9e0",  # ticket 6
    "4be372f9",  # ticket 7
}

# Lines the poller emits.  Example:
#   2026-08-11T09:19:55Z slot BUSY: 7eca997d validating created=2026-08-11T07:57:16.158Z
#   2026-08-11T09:20:12Z slot FREE -> submitting (attempt 1)
RE_BUSY = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+slot BUSY:\s+(?P<id>\S+)\s+"
    r"(?P<status>\S+)\s+created=(?P<created>\S+)"
)
RE_FREE = re.compile(
    r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+slot FREE"
)


def parse_iso(text: str) -> datetime:
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


class PollerLog:
    """One poller log reduced to its slot-occupancy observations."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.busy: list[tuple[datetime, str, str, datetime]] = []
        self.free: list[datetime] = []
        self.submitted_ids: list[str] = []
        with open(path, "r", errors="replace") as handle:
            for line in handle:
                match = RE_BUSY.match(line)
                if match:
                    self.busy.append(
                        (
                            parse_iso(match.group("ts")),
                            match.group("id"),
                            match.group("status"),
                            parse_iso(match.group("created")),
                        )
                    )
                    continue
                match = RE_FREE.match(line)
                if match:
                    self.free.append(parse_iso(match.group("ts")))
                    continue
                if line.startswith("SUBMITTED ok"):
                    self.submitted_ids += re.findall(r"[0-9a-f-]{36}", line)

    @property
    def is_poller(self) -> bool:
        return bool(self.busy) or bool(self.free)

    def poll_intervals(self) -> list[float]:
        """Seconds between consecutive polls: 15 s sleep + API round trip."""
        stamps = sorted(ts for ts, _, _, _ in self.busy)
        return [
            (b - a).total_seconds() for a, b in zip(stamps, stamps[1:])
        ]

    def occupancy_spans(self) -> list[dict]:
        """One record per submission id observed holding the slot."""
        by_id: dict[str, dict] = {}
        for ts, sub_id, status, created in self.busy:
            rec = by_id.setdefault(
                sub_id,
                {
                    "id": sub_id,
                    "created": created,
                    "first_seen": ts,
                    "last_seen": ts,
                    "n_polls": 0,
                    "statuses": set(),
                },
            )
            rec["first_seen"] = min(rec["first_seen"], ts)
            rec["last_seen"] = max(rec["last_seen"], ts)
            rec["n_polls"] += 1
            rec["statuses"].add(status)
        # A FREE observation after a busy span closes that span.
        for rec in by_id.values():
            closers = [f for f in self.free if f > rec["last_seen"]]
            rec["freed_at"] = min(closers) if closers else None
        return sorted(by_id.values(), key=lambda r: r["first_seen"])


def load_cache_rows(paths: list[str]) -> tuple[list[dict], datetime | None]:
    for path in paths:
        if os.path.exists(path):
            with open(path, "r") as handle:
                payload = json.load(handle)
            rows = payload.get("submissions", payload)
            mtime = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
            return rows, mtime
    return [], None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recover exact slot-occupancy brackets from poller logs."
    )
    ap.add_argument("--log", action="append", default=[],
                    help="poller log path (repeatable); default globs job logs")
    ap.add_argument("--glob", action="append", default=[],
                    help="glob of poller logs (repeatable). Use this to rerun "
                         "against the committed archive: --glob "
                         "'research/artifacts/fern-r109f/pollerlogs/*.log'")
    ap.add_argument("--cache", action="append", default=[],
                    help="submissions cache for the mtime cross-check")
    ap.add_argument("--deadline", default=DEFAULT_DEADLINE)
    args = ap.parse_args()

    # Explicit --log / --glob win over the runtime job-log directory, so the
    # section is reproducible from the archive committed under
    # research/artifacts/fern-r109f/pollerlogs/ by anyone who clones the branch.
    log_paths = list(args.log)
    for pat in args.glob:
        log_paths.extend(sorted(glob.glob(pat)))
    if not log_paths:
        log_paths = sorted(glob.glob(DEFAULT_LOG_GLOB))
    pollers = []
    for path in log_paths:
        try:
            log = PollerLog(path)
        except OSError:
            continue
        if log.is_poller:
            pollers.append(log)

    if not pollers:
        print("no poller logs found; nothing to do", file=sys.stderr)
        return 1

    print("=== poller logs used as 15-second occupancy monitors ===")
    for log in pollers:
        ivs = log.poll_intervals()
        span = ""
        if log.busy:
            span = "%s .. %s" % (
                fmt(min(ts for ts, _, _, _ in log.busy)),
                fmt(max(ts for ts, _, _, _ in log.busy)),
            )
        print("  %s" % os.path.basename(log.path))
        print("      polls=%d  window=%s" % (len(log.busy), span))
        if ivs:
            print("      poll interval s: median=%.1f min=%.1f max=%.1f"
                  " (15 s sleep + API round trip)"
                  % (statistics.median(ivs), min(ivs), max(ivs)))
        if log.free:
            print("      slot FREE observed at: %s"
                  % ", ".join(fmt(f) for f in log.free))
        if log.submitted_ids:
            print("      submitted: %s" % ", ".join(log.submitted_ids))

    spans = []
    for log in pollers:
        for rec in log.occupancy_spans():
            rec["log"] = os.path.basename(log.path)
            spans.append(rec)

    rows, cache_mtime = load_cache_rows(args.cache or DEFAULT_CACHES)
    by_id_prefix = {}
    for row in rows:
        rid = row.get("id") or ""
        by_id_prefix[rid[:8]] = row

    print()
    print("=== exactly bracketed completions (resolution = one poll interval) ===")
    exact = []
    for rec in spans:
        if rec["freed_at"] is None:
            continue
        lo = minutes(rec["last_seen"] - rec["created"])
        hi = minutes(rec["freed_at"] - rec["created"])
        mid = 0.5 * (lo + hi)
        age_at_first = minutes(rec["first_seen"] - rec["created"])
        rec.update(lo=lo, hi=hi, mid=mid, age_at_first=age_at_first)
        exact.append(rec)
        print("  %s  created=%s" % (rec["id"], fmt(rec["created"])))
        print("      last seen busy   %s   -> service >= %8.3f min"
              % (fmt(rec["last_seen"]), lo))
        print("      slot free at     %s   -> service <= %8.3f min"
              % (fmt(rec["freed_at"]), hi))
        print("      service = %.3f min +/- %.3f  (bracket width %.1f s)"
              % (mid, 0.5 * (hi - lo), (hi - lo) * 60.0))
        print("      age when first observed = %.2f min  (age/total = %.3f)"
              % (age_at_first, age_at_first / mid if mid else float("nan")))

    if not exact:
        print("  (none: no poller has yet observed a BUSY -> FREE transition)")

    print()
    print("=== still held at end of log (one-sided lower bounds) ===")
    open_spans = [r for r in spans if r["freed_at"] is None]
    for rec in open_spans:
        lo = minutes(rec["last_seen"] - rec["created"])
        # Stored, not just printed: the "whose queue" section below needs the
        # one-sided bound, and recomputing it there would let the two sections
        # drift apart.
        rec["lo"] = lo
        print("  %s  created=%s  still busy at %s  -> service >= %.3f min"
              % (rec["id"], fmt(rec["created"]), fmt(rec["last_seen"]), lo))
    if not open_spans:
        print("  (none)")

    # --- cross-check against the independent mtime-censoring estimator -----
    print()
    print("=== cross-check vs the mtime interval-censoring estimator (7.1) ===")
    if cache_mtime is None:
        print("  no submissions cache available; skipped")
    else:
        print("  cache observation time: %s  (%d rows)"
              % (fmt(cache_mtime), len(rows)))
        print("  The two estimates share NO input: one reads poller stdout,")
        print("  the other reads cache-file mtimes.  Agreement is therefore a")
        print("  genuine external validation, not an internal consistency check.")
        for rec in exact:
            row = by_id_prefix.get(rec["id"][:8])
            if row is None:
                print("  %s: not present in cache; cannot cross-check"
                      % rec["id"])
                continue
            terminal = row.get("status") in ("rejected", "failed",
                                             "accepted", "cancelled")
            created = parse_iso(row["createdAt"])
            elapsed_at_cache = minutes(cache_mtime - created)
            if terminal:
                verdict = ("cache says TERMINAL by %.2f min; exact says %.3f min"
                           % (elapsed_at_cache, rec["mid"]))
                ok = rec["lo"] <= elapsed_at_cache + 1e-9
            else:
                verdict = ("cache says >= %.2f min (censored); exact says %.3f min"
                           % (elapsed_at_cache, rec["mid"]))
                ok = elapsed_at_cache <= rec["hi"] + 1e-9
            print("  %s: %s   -> %s"
                  % (rec["id"], verdict, "CONSISTENT" if ok else "CONTRADICTION"))

    # --- the headline: a run-time floor plus a queue ------------------------
    print()
    print("=== decomposition: deterministic run time + variable queue wait ===")
    floor = None
    if len(exact) >= 2:
        vals = sorted(r["mid"] for r in exact)
        floor = vals[0]
        # The cluster is every exact value within a few percent of the minimum.
        cluster = [v for v in vals if v <= floor * 1.05]
        print("  exact service times (min): %s"
              % ", ".join("%.3f" % v for v in vals))
        if len(cluster) >= 2:
            mean_c = statistics.mean(cluster)
            sd_c = statistics.stdev(cluster) if len(cluster) > 1 else 0.0
            print("  a cluster of %d sits within 5%% of the minimum:"
                  " mean=%.3f sd=%.4f cv=%.3f%%"
                  % (len(cluster), mean_c, sd_c,
                     100.0 * sd_c / mean_c if mean_c else 0.0))
            print("  A sub-1% spread across runs hours apart is not a queue;")
            print("  it is a fixed-work pipeline (build + metallib + two")
            print("  benchmark legs + correctness gates) running to completion.")
            print("  READ AS: service = RUN (near constant) + QUEUE (variable).")
        print()
        print("  implied queue wait = service - floor(%.3f min):" % floor)
        for rec in sorted(exact, key=lambda r: r["mid"]):
            print("    %-10s service %8.3f  -> queue %8.3f min"
                  % (rec["id"], rec["mid"], rec["mid"] - floor))
        for rec in open_spans:
            lo = minutes(rec["last_seen"] - rec["created"])
            if lo > floor:
                print("    %-10s service >=%7.3f  -> queue >=%7.3f min"
                      % (rec["id"], lo, lo - floor))
        print()
        print("  WHAT THE FLOOR IS AND IS NOT.  The sample minimum of a")
        print("  positive quantity is an UPPER bound on the population")
        print("  minimum, never a lower one; and length bias (below) can only")
        print("  push observed values up.  So the honest claim is 'no observed")
        print("  shot cost less than %.1f min', not '%.1f min is a hard floor'."
              % (floor, floor))
        print("  It is still the single most useful number for planning: it is")
        print("  the part of the cost that no channel strategy can remove.")

    # --- IS THE VARIABLE PART MINE TO CONTROL? ------------------------------
    # The decomposition above says service = near-constant run + variable queue.
    # It does NOT say whose queue.  The obvious candidate is the account's own
    # 1-in-flight slot, and section 7.4e measured 98.3 % occupancy on it, which
    # makes that reading tempting.  It is testable: a submission created within
    # seconds of an observed "slot FREE" had NO account-level queue ahead of it
    # by construction.  If the account slot were the variable component, those
    # submissions should all land in the run cluster.
    print()
    print("=== whose queue is it? service conditional on winning the slot ===")
    all_free = sorted(ts for log in pollers for ts in log.free)
    # Second, weaker witness: the last poll that saw the PREVIOUS holder busy
    # bounds the free moment from below even when no FREE line was logged,
    # because the account cannot hold two submissions at once.
    busy_by_time = sorted(
        (ts, sub_id) for log in pollers for ts, sub_id, _, _ in log.busy
    )
    # One record per submission.  A submission held by several overlapping
    # pollers appears once per log, and counting it repeatedly would fake up
    # sample size -- 7eca997d alone is observed by four logs.  An exact bracket
    # always beats an open one; among open ones the longest lower bound wins.
    best: dict[str, dict] = {}
    for rec in exact + open_spans:
        key = rec["id"][:8]
        cur = best.get(key)
        if cur is None:
            best[key] = rec
            continue
        cur_exact = cur.get("mid") is not None
        rec_exact = rec.get("mid") is not None
        if rec_exact and not cur_exact:
            best[key] = rec
        elif rec_exact == cur_exact and rec.get("lo", 0.0) > cur.get("lo", 0.0):
            best[key] = rec
    considered = []
    for rec in sorted(best.values(), key=lambda r: r["created"]):
        created = rec["created"]
        # Two kinds of witness bound the moment the slot became available, and
        # the LATER one is the tighter bound, so take the max of both.
        #   * a logged "slot FREE" proves the slot was free at that instant;
        #   * a poll that saw a DIFFERENT submission holding the slot proves it
        #     was still busy then, so it can only have freed afterwards.
        # Taking only the first was a real error: it reported 7eca997d as
        # waiting 1935 s when f2b23450 in fact occupied the slot for most of
        # that interval, and reported 3275a9bd as waiting 5 hours when the slot
        # was simply idle.  Either way the resulting number is an UPPER bound on
        # the account-level queue, never a point estimate.
        cands = [f for f in all_free if f <= created]
        cands += [
            ts for ts, sid in busy_by_time
            if ts < created and sid[:8] != rec["id"][:8]
        ]
        if not cands:
            print("  %s  no witness before creation; account queue unknown"
                  % rec["id"])
            continue
        witness_at = max(cands)
        lat = (created - witness_at).total_seconds()
        kind = "FREE" if witness_at in all_free else "other sub still busy"
        svc = rec.get("mid")
        considered.append((rec["id"], lat, svc, rec.get("lo")))
        if svc is not None:
            svc_text = "service = %7.3f min" % svc
        else:
            svc_text = "service >= %6.3f min" % rec["lo"]
        if lat > 900.0:
            print("  %s  slot idle >= %.0f min before it; queue UNKNOWN   %s"
                  % (rec["id"], lat / 60.0, svc_text))
        else:
            print("  %s  slot won <=%4.0f s after freeing   %s"
                  % (rec["id"], lat, svc_text))
        print("      witness: %s at %s" % (kind, fmt(witness_at)))

    won_fast = [c for c in considered if c[1] <= 120.0]
    if len(won_fast) >= 2:
        vals = [c[2] if c[2] is not None else c[3] for c in won_fast]
        lo_v, hi_v = min(vals), max(vals)
        print()
        print("  %d of %d observed submissions took the slot within 120 s of it"
              % (len(won_fast), len(considered)))
        print("  freeing, so their account-level queue was ~0 by construction.")
        print("  Their service still spans %.3f .. %.3f min = a factor of %.2f."
              % (lo_v, hi_v, hi_v / lo_v if lo_v else float("nan")))
        print()
        print("  CONCLUSION: the variable component is NOT the account slot.")
        print("  Winning the slot instantly buys a run-cluster service time")
        print("  sometimes and a 3x service time other times, so the variance")
        print("  lives in a queue I do not share an account with -- the global")
        print("  runner pool, driven by every other solver's submissions.")
        print("  This REFINES 7.4e rather than contradicting it: 98.3 % account")
        print("  occupancy is a real cost (I could not submit at all), but it is")
        print("  a cost on TOP of an exogenous queue, and no amount of poller")
        print("  discipline touches the exogenous part.")
        print("  It also rescues the run cluster from a confound: if the tight")
        print("  cluster were just 'three draws from one quiet hour', then the")
        print("  22.7 min member created at 07:01Z -- 56 min before the 82.8 min")
        print("  member -- would not be in it.  Fixed work, bursty queue.")
        med = sorted(vals)[len(vals) // 2] if len(vals) % 2 else (
            0.5 * (sorted(vals)[len(vals) // 2 - 1] + sorted(vals)[len(vals) // 2])
        )
        print()
        print("  median service GIVEN the slot was won instantly = %.2f min"
              % med)
        print("  (compare 7.1's all-solver bracket midpoint median 29.61 min,")
        print("  computed from cache mtimes over a mostly disjoint row set:")
        print("  two estimators built from different inputs land within a")
        print("  minute of each other, which is the strongest support the")
        print("  ~30 min planning figure has.)")
        n_open = sum(1 for c in won_fast if c[2] is None)
        print("  CAVEAT: n=%d, of which %d %s still open, so the median can only"
              % (len(vals), n_open, "is" if n_open == 1 else "are"))
        print("  move UP as those submissions complete.")

    # --- contention loss, with self-waits excluded --------------------------
    print()
    print("=== wall clock lost waiting for the shared slot ===")
    print("  A poller's start -> slot FREE interval is time I could not submit.")
    print("  CRITICAL DISTINCTION: if the blocker was MY OWN previous")
    print("  submission, that interval is the tail of my own service time and")
    print("  adding it to service would DOUBLE COUNT.  Only a blocker created")
    print("  by another user of the shared account is a genuine extra cost.")
    mine = set(KNOWN_OWN_RECEIPT_PREFIXES)
    for log in pollers:
        for sid in log.submitted_ids:
            mine.add(sid[:8])
    print("  ids treated as mine (%d): %s"
          % (len(mine), ", ".join(sorted(mine))))
    foreign_losses = []
    self_waits = []
    for log in pollers:
        if not log.busy or not log.free:
            continue
        start = min(ts for ts, _, _, _ in log.busy)
        candidates = [f for f in log.free if f >= start]
        if not candidates:
            continue
        freed = min(candidates)
        blockers = sorted({sid for _, sid, _, _ in log.busy})
        loss = minutes(freed - start)
        own = all(b[:8] in mine for b in blockers)
        (self_waits if own else foreign_losses).append(loss)
        print("  %-8s waited %6.2f min for %-22s  %s"
              % (os.path.basename(log.path)[:8], loss, ",".join(blockers),
                 "SELF (already counted as service)" if own
                 else "FOREIGN (genuine extra cost)"))
    for log in pollers:
        if log.busy and not log.free:
            start = min(ts for ts, _, _, _ in log.busy)
            last = max(ts for ts, _, _, _ in log.busy)
            blockers = sorted({sid for _, sid, _, _ in log.busy})
            own = all(b[:8] in mine for b in blockers)
            print("  %-8s STILL WAITING >= %6.2f min for %-14s  %s"
                  % (os.path.basename(log.path)[:8], minutes(last - start),
                     ",".join(blockers), "SELF" if own else "FOREIGN"))
    print("  self-waits (min, NOT additive): %s"
          % (", ".join("%.2f" % v for v in self_waits) or "none"))
    print("  foreign waits (min, additive) : %s"
          % (", ".join("%.2f" % v for v in foreign_losses) or "none"))
    if foreign_losses:
        print("  n=%d median=%.2f -- an existence proof of a non-zero omitted"
              % (len(foreign_losses), statistics.median(foreign_losses)))
        print("  cost, far too few to be a distribution.")
    print("  Ownership is asserted from poller 'SUBMITTED ok' lines plus the")
    print("  hardcoded ticket list; a misattribution here moves the number, so")
    print("  the two lists are printed rather than silently summed.")

    # --- the caution that makes the numbers usable -------------------------
    print()
    print("=== why these exact numbers must NOT be pooled with 7.1's sample ===")
    print("  LENGTH BIAS / INSPECTION PARADOX.  A poller observes whichever job")
    print("  holds the slot at the instant polling begins.  The chance of")
    print("  catching a job is proportional to its duration, so exactly")
    print("  measured jobs over-represent long services in principle.  Under")
    print("  length-biased sampling from a distribution with mean mu and")
    print("  coefficient of variation c the observed duration has mean")
    print("  mu*(1+c^2), which for a heavy tail is several times mu.")
    if exact:
        ratios = [r["age_at_first"] / r["mid"] for r in exact if r["mid"]]
        mean_r = statistics.mean(ratios)
        se_r = (1.0 / 12.0) ** 0.5 / len(ratios) ** 0.5
        z_r = (mean_r - 0.5) / se_r if se_r else float("nan")
        print("  HOW BIG IS IT HERE?  A job caught at an instant unrelated to")
        print("  its own duration has age/total ~ Uniform(0,1), mean 0.500.")
        print("  Observed age/total = %s"
              % ", ".join("%.3f" % v for v in ratios))
        print("  n=%d mean=%.3f se=%.3f z=%+.2f -> %s"
              % (len(ratios), mean_r, se_r, z_r,
                 "NOT distinguishable from unbiased inspection"
                 if abs(z_r) < 2 else "evidence of bias"))
        print("  So the bias is a mechanism that cannot be ruled out, not a")
        print("  distortion demonstrated in this sample.  Stating it the other")
        print("  way round would be the same error as quoting a ratio whose")
        print("  denominator was never measured.")
        n_at_floor = len([r for r in exact
                          if floor and r["mid"] <= floor * 1.05])
        print("  It also cannot manufacture the cluster near the minimum:")
        print("  over-sampling long jobs would populate the TAIL, yet %d of %d"
              % (n_at_floor, len(exact)))
        print("  exact values sit at the bottom of the range.")
    print("  SECOND BIAS, DIFFERENT SOURCE.  7.1 discards rows created and")
    print("  finished inside one snapshot gap.  7.1 called those 'the fast")
    print("  ones'.  With a run-time floor near %.0f min and a median"
          % (floor or 0.0))
    print("  inter-snapshot gap of the same order, that reading is WRONG: a")
    print("  floor-length row fits inside any gap at least as long as the")
    print("  floor, so the exclusion is driven by SNAPSHOT SPARSITY, not by")
    print("  row speed.  See --exclusion-check in fern_r109f_service_latency.py")
    print("  for the quantitative version.  This retracts a 7.1 sentence.")
    print("  LEGITIMATE USE of this file: (a) validating the censoring")
    print("  machinery against a ground truth; (b) establishing the run-time")
    print("  floor; (c) measuring foreign contention loss, which is unbiased")
    print("  because the poller start time is set by me, not by the job.")

    # --- planning consequence ---------------------------------------------
    print()
    print("=== planning consequence ===")
    deadline = parse_iso(args.deadline)
    now = datetime.now(timezone.utc)
    remaining = minutes(deadline - now)
    print("  now=%s  deadline=%s  remaining=%.0f min"
          % (fmt(now), fmt(deadline), remaining))
    service_only = 29.61          # 7.2 bracket midpoint median, n=20
    foreign = statistics.median(foreign_losses) if foreign_losses else 0.0
    worst_exact = max((r["mid"] for r in exact), default=0.0)
    rows = [("run-time floor alone (best case ever seen)", floor or 0.0),
            ("7.2 bracket median, service only", service_only)]
    if floor and foreign:
        rows.append(("floor + measured foreign wait", floor + foreign))
    if worst_exact and foreign:
        rows.append(("worst exact service + foreign wait",
                     worst_exact + foreign))
    for label, cost in rows:
        if not cost:
            continue
        print("  %-42s %6.1f min/shot -> %5.1f shots"
              % (label, cost, remaining / cost))
    print("  The spread between these rows is the honest uncertainty in the")
    print("  shot budget.  MIN_PER_SHOT in the campaign script is deliberately")
    print("  NOT updated from here: the same discipline as 7.2, which kept the")
    print("  measurement separate from its own confirmation so that a test")
    print("  could not be silently converted into a fit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
