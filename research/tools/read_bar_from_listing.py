#!/usr/bin/env python3
"""Recover the leaderboard bar from a saved `mlxfast submissions` listing.

Why this exists
---------------
The bar is never printed directly. Every ADJUDICATED row of our own account prints
`score` and `diff`, where `diff = score - bar_at_adjudication` in RAW score units, so

    bar = score - diff

Each adjudicated row therefore gives one independent reading of the bar *at the moment
that row was adjudicated*. A `validating` row gives nothing (score/diff are `n/a`), which
is exactly why a bar reading can only ever be as fresh as the newest terminal row.

`final_channel_read_1627Z.py` hard-codes the 16:27Z snapshot. This one is generic: point
it at any saved listing and it prints every recoverable reading plus their spread, so the
next person can answer "did the crown move?" mechanically instead of re-deriving it.

Usage
-----
    # listing.txt = captured stdout of the account's `mlxfast submissions` listing.
    # (Not written as a runnable command line on purpose: run_all_tools_smoke.sh scans
    #  research/tools/ for anything that looks like an invocation of the submission CLI
    #  and fails closed. That guard is correct; do not weaken it to make a docstring
    #  prettier. It caught this file at 16:54Z.)
    python3 research/tools/read_bar_from_listing.py listing.txt
    python3 research/tools/read_bar_from_listing.py listing.txt --published 2.6195531094824

Exit codes: 0 ok, 2 usage/no parsable rows.

Verified 16:53Z against the live 16:49Z listing: 108 rows matched (107 rejected + 1
validating), three newest readings 2.61955336 / 2.61955311 / 2.61955332, worst deviation
from the published bar 2.6195531094824 = 2.55e-07, i.e. print rounding. The 70 `failed`
rows do not match and are not counted: a failed run prints no score and no diff, so it
carries no bar information. Do not read "rows parsed: 108" as "the account has 108 rows".

CAVEAT that survives this script (manifest rule 23): the listing covers OUR account only.
A competitor taking the crown after our newest adjudication is invisible here. This tool
tells you where the bar was at our last terminal row, not where it is now.

PARSING TRAP, found the hard way: `mlxfast submissions` emits ANSI colour escapes even
when its stdout is redirected to a file, so the `status` and `diff` fields arrive wrapped
in \x1b[31m...\x1b[39m. A naive column regex silently matches zero rows and you conclude
"no data" when the data is right there. We strip ANSI before parsing.
"""

import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# submission  solver  status  score  metrics...  diff (pct)  commit  created
ROW = re.compile(
    r"^(?P<sub>[0-9a-f]{7,})\s+"
    r"(?P<solver>\S+)\s+"
    r"(?P<status>rejected|failed|promoted|validating|pending|running)\s+"
    r"(?P<score>n/a|[0-9.]+)\s+"
    r".*?"
    r"(?P<diff>n/a|-?[0-9.]+)\s+\((?P<pct>-?[0-9.]+)%\)\s+"
    r"(?P<commit>\S+)\s+"
    r"(?P<created>\d.*\S)\s*$"
)
# rows with no diff at all (validating): score and diff both print as bare n/a
ROW_NA = re.compile(
    r"^(?P<sub>[0-9a-f]{7,})\s+(?P<solver>\S+)\s+"
    r"(?P<status>validating|pending|running)\s+n/a\s+n/a\s+n/a\s+\S+\s+(?P<created>\d.*\S)\s*$"
)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        print("usage: read_bar_from_listing.py <listing.txt> [--published <float>]")
        return 2

    path = argv[1]
    published = None
    if "--published" in argv:
        published = float(argv[argv.index("--published") + 1])

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = [ANSI.sub("", ln) for ln in fh.read().splitlines()]

    readings = []          # (submission, created, score, diff, bar)
    in_flight = []         # (submission, created, status)
    status_counts = {}

    for line in lines:
        m_na = ROW_NA.match(line)
        if m_na:
            st = m_na.group("status")
            status_counts[st] = status_counts.get(st, 0) + 1
            in_flight.append((m_na.group("sub"), m_na.group("created"), st))
            continue
        m = ROW.match(line)
        if not m:
            continue
        st = m.group("status")
        status_counts[st] = status_counts.get(st, 0) + 1
        if m.group("score") == "n/a" or m.group("diff") == "n/a":
            in_flight.append((m.group("sub"), m.group("created"), st))
            continue
        score = float(m.group("score"))
        diff = float(m.group("diff"))
        readings.append((m.group("sub"), m.group("created"), score, diff, score - diff))

    if not readings:
        print("no adjudicated rows parsed from %s -- nothing to recover" % path)
        print("  three things produce this, in descending order of likelihood:")
        print("  1. the file is still being written (I hit this at 16:53Z reading a listing")
        print("     one second after launching the command that produced it) -- re-read it;")
        print("  2. every row is still in flight or `failed`, so no row carries a diff;")
        print("  3. the column layout changed and the regex above needs updating.")
        print("  %d line(s) scanned, %d row(s) matched as in-flight."
              % (len(lines), len(in_flight)))
        return 2

    total = sum(status_counts.values())
    print("listing: %s" % path)
    print("rows parsed: %d  (%s)" % (
        total, ", ".join("%s %d" % (k, v) for k, v in sorted(status_counts.items()))))

    if in_flight:
        print("\nIN FLIGHT (no bar recoverable from these):")
        for sub, created, st in in_flight:
            print("  %-9s %-11s created %s" % (sub, st, created))
        print("  -> the channel is SERIAL: nothing else can be fired until these terminate.")

    tail = readings[-3:] if len(readings) >= 3 else readings
    print("\nbar = score - diff, from the %d newest adjudicated row(s):" % len(tail))
    for sub, created, score, diff, bar in tail:
        print("  %-9s %-22s score %.14f  diff %+.6f  -> bar %.8f" % (sub, created, score, diff, bar))

    bars = [r[4] for r in tail]
    spread = max(bars) - min(bars)
    print("\nspread across those readings: %.2e" % spread)
    print("`diff` prints to 6 dp, so agreement to ~5e-7 is print rounding, NOT drift.")
    if spread > 5e-6:
        print("  !! spread exceeds print rounding -- the bar MOVED between these rows.")

    if published is not None:
        worst = max(abs(b - published) for b in bars)
        print("\npublished bar %.13f, worst deviation %.2e -> %s"
              % (published, worst, "agrees" if worst < 5e-6 else "DISAGREES"))

    newest = readings[-1]
    print("\nFRESHNESS: this bar is pinned to %s (row %s). Rule 23: the listing is our"
          % (newest[1], newest[0]))
    print("account only, so a competitor crown taken after that timestamp is invisible here.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
