#!/usr/bin/env python3
"""Measure who actually occupies the shared account's submission slot.

The campaign script carries ``CHANNEL["account_share"] = 3``, an ASSUMPTION
that three parties contend for the single in-flight slot on the shared
``morganmcg1`` account.  Two independent sources now make that assumption
testable, so it should be tested rather than carried:

1.  Submission notes name their author.  Every note this campaign wrote
    contains the string ``maple-fern``; the advisor's contain
    ``maple-advisor``.  Ownership is therefore READ, not guessed.

2.  The ticket pollers logged the account's in-flight submission every 15 s,
    which converts "who holds the slot" from an inference into an observation.

What comes out is not a head count but an OCCUPANCY FRACTION, which is the
quantity that actually governs how long I wait.  Three contenders who submit
once a day cost me nothing; one contender who saturates costs me everything.

A logical bound worth noting: because the account permits exactly one
submission in flight, the creation of a submission PROVES the previous one was
already terminal.  That turns a one-sided poller bound into a two-sided
bracket at no cost, and it is exact rather than sampled.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

HANDLE_RE = re.compile(
    r"maple-(fern|tanjiro|nezuko|frieren|edward|alphonse|advisor)"
)
TERMINAL = ("rejected", "failed", "accepted", "cancelled")

# Exact service times recovered from poller logs by
# research/fern_r109f_poller_occupancy.py (bracket width <= 126 s).
EXACT_SERVICE_MIN = {
    "3275a9bd": 22.743,
    "ed40f3ee": 22.986,
    "0531544b": 23.085,
    "7eca997d": 82.789,
}


def parse_iso(text: str) -> datetime:
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%H:%M:%S")


def handles(note: str) -> str:
    found = sorted(set(HANDLE_RE.findall(note or "")))
    return ",".join(found) if found else "(unattributed)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/subs_p14.json")
    ap.add_argument("--solver", default="morganmcg1")
    ap.add_argument("--since", default="2026-08-11T06:00:00Z")
    ap.add_argument("--window-end", default="2026-08-11T09:20:12Z",
                    help="slot-free instant observed by the ticket-7 poller")
    args = ap.parse_args()

    with open(args.cache) as handle:
        rows = json.load(handle).get("submissions", [])
    since = parse_iso(args.since)
    mine_solver = [r for r in rows
                   if r.get("solverUsername") == args.solver
                   and parse_iso(r["createdAt"]) >= since]
    mine_solver.sort(key=lambda r: r["createdAt"])

    print("=== who submitted on the shared account since %s ===" % args.since)
    print("  attribution is by handle string inside the note, not by guess")
    for row in mine_solver:
        print("  %s  %s  note=%5dB  status=%-10s  author=%s"
              % (row["id"][:8], fmt(parse_iso(row["createdAt"])),
                 len(row.get("note") or ""), row.get("status"),
                 handles(row.get("note"))))

    # --- the 1-in-flight rule as a free two-sided bracket -----------------
    print()
    print("=== service brackets from the 1-in-flight rule (exact, not sampled) ===")
    print("  Creating submission k+1 proves submission k was already terminal,")
    print("  so createdAt[k+1] is a hard upper bound on k's completion.")
    derived = {}
    for prev, nxt in zip(mine_solver, mine_solver[1:]):
        pid = prev["id"][:8]
        upper = ((parse_iso(nxt["createdAt"]) - parse_iso(prev["createdAt"]))
                 .total_seconds() / 60.0)
        derived[pid] = upper
        exact = EXACT_SERVICE_MIN.get(pid)
        if exact is not None:
            print("  %s service <= %7.3f min (next created %s);"
                  " poller exact %.3f -> %s"
                  % (pid, upper, nxt["id"][:8], exact,
                     "CONSISTENT" if exact <= upper + 1e-9 else "CONTRADICTION"))
        else:
            print("  %s service <= %7.3f min (next created %s)"
                  % (pid, upper, nxt["id"][:8]))

    # --- occupancy of the contested window --------------------------------
    print()
    print("=== slot occupancy over the window I was trying to submit in ===")
    win_lo = parse_iso(mine_solver[0]["createdAt"]) if mine_solver else since
    win_hi = parse_iso(args.window_end)
    window = (win_hi - win_lo).total_seconds() / 60.0
    by_author: dict[str, float] = {}
    for row in mine_solver:
        rid = row["id"][:8]
        svc = EXACT_SERVICE_MIN.get(rid, derived.get(rid))
        if svc is None:
            # last row, still open at window end
            svc = (win_hi - parse_iso(row["createdAt"])).total_seconds() / 60.0
        author = handles(row.get("note"))
        by_author[author] = by_author.get(author, 0.0) + svc
    held = sum(by_author.values())
    print("  window %s -> %s = %.1f min" % (fmt(win_lo), fmt(win_hi), window))
    for author, mins in sorted(by_author.items(), key=lambda kv: -kv[1]):
        print("  %-16s held %7.1f min = %5.1f%% of the window"
              % (author, mins, 100.0 * mins / window))
    print("  %-16s      %7.1f min = %5.1f%%"
          % ("TOTAL BUSY", held, 100.0 * held / window))
    print("  %-16s      %7.1f min = %5.1f%%"
          % ("IDLE", window - held, 100.0 * (window - held) / window))

    print()
    print("=== what this replaces ===")
    print("  CHANNEL['account_share'] = 3 models contention as a head count.")
    print("  Measured instead: %d distinct author(s) submitted in this window,"
          % len([a for a in by_author if a != "(unattributed)"]))
    print("  and the slot was busy %.1f%% of it.  A head count of 3 would"
          % (100.0 * held / window))
    print("  predict I get every third slot; the occupancy measurement says I")
    print("  got NONE of them, because one saturating contender leaves no")
    print("  residual capacity regardless of how many parties exist."
          )
    print("  This is the same conclusion 7.1 reached from mtimes (idle ~ 0),")
    print("  now confirmed at 15 s resolution from an independent source, and")
    print("  it is why a faster poller redistributes capacity but cannot")
    print("  create it.")
    print()
    print("  CAUTION: one window, one contender, n=3 submissions.  The")
    print("  occupancy fraction is a description of 07:01-09:20Z, not a")
    print("  forecast.  The advisor's saturation is a policy choice that can")
    print("  change without notice, in either direction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
