#!/usr/bin/env python3
"""Pre-fire epoch gate: is the account in a state where a fire returns anything?

Motivation (measured, see research/r129g_failure_clustering.md). Across 176 terminal
receipts, 70 came back `failed` with no score and no error text. Those 70 are not
spread over the campaign: they are one time-local burst (8/7 09:59 - 8/8 17:38,
62 of 63 fires in that window failed), and the Wald-Wolfowitz runs test rejects
independence at z = -10.78. The practical consequence is that the state of the
PREVIOUS terminal receipt predicts the next one far better than anything about the
candidate tree:

    P(fail | previous terminal was scored)  =  8/105  =  7.6%
    P(fail | previous terminal failed)      = 62/70   = 88.6%
    P(fail | previous TWO failed)           = 58/62   = 93.5%
    P(fail) unconditional                   = 70/176  = 39.8%

So the cheapest way to protect a draw is not a better local packaging check - it is
one read of the account's own receipt list immediately before firing. This script is
that read, expressed in the same grammar as research/tools/preflight_gates.sh
(`GATE <name>: PASS|FAIL`, nonzero exit if any gate fails) so it can be dropped into
the same pre-fire ritual. It is read-only: it parses a dump you captured, it never
fires and never calls a mutating command.

Usage:
    COLUMNS=4000 mlxfast submissions > /tmp/subs.txt      # read-only
    python3 research/tools/epoch_gate.py --dump /tmp/subs.txt

Negative control (proves the gate can fail, no fire needed): truncate a real dump so
its newest rows land inside the 8/7-8/8 burst and re-run - the epoch gates flip to
FAIL. See the note for the recorded transcript of both directions.
"""

import argparse
import datetime as dt
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TERMINAL = {"failed", "rejected", "promoted"}
ROW = re.compile(
    r"^(?P<sub>\w+)\s+(?P<solver>\S+)\s+(?P<status>\w+)\s+(?P<rest>.*)$"
)
CREATED = re.compile(r"(\d{1,2}/\d{1,2}/\d{2},\s+\d{1,2}:\d{2}\s+[AP]M)\s*$")


def parse(text):
    rows = []
    for line in ANSI.sub("", text).splitlines():
        m = ROW.match(line.strip())
        if not m or m.group("status") not in TERMINAL | {"validating", "pending"}:
            continue
        c = CREATED.search(line)
        t = None
        if c:
            for fmt in ("%m/%d/%y, %I:%M %p", "%m/%d/%Y, %I:%M %p"):
                try:
                    t = dt.datetime.strptime(c.group(1), fmt)
                    break
                except ValueError:
                    pass
        rows.append({"sub": m.group("sub"), "status": m.group("status"), "t": t,
                     "created": c.group(1) if c else "?"})
    return [r for r in rows if r["t"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, help="output of `mlxfast submissions`")
    args = ap.parse_args()

    text = open(args.dump).read() if args.dump != "-" else sys.stdin.read()
    rows = parse(text)
    if not rows:
        print("GATE epoch_dump_parsed: FAIL - no receipt rows parsed from the dump.")
        print("  (the CLI colours its status column; a naive split() sees nothing.)")
        sys.exit(1)
    print(f"GATE epoch_dump_parsed: PASS - {len(rows)} receipts parsed")

    rows.sort(key=lambda r: r["t"])
    term = [r for r in rows if r["status"] in TERMINAL]
    inflight = [r for r in rows if r["status"] not in TERMINAL]

    # Historical conditionals recomputed from this very dump, so the numbers the
    # gate justifies itself with are never stale.
    nf = sum(1 for r in term if r["status"] == "failed")
    after_fail = after_scored = fail_after_fail = fail_after_scored = 0
    for prev, cur in zip(term, term[1:]):
        if prev["status"] == "failed":
            after_fail += 1
            fail_after_fail += cur["status"] == "failed"
        else:
            after_scored += 1
            fail_after_scored += cur["status"] == "failed"
    print(f"  history: {len(term)} terminal, {nf} failed ({100.0 * nf / len(term):.1f}%)")
    if after_scored:
        print(f"  P(fail | prev scored) = {fail_after_scored}/{after_scored} = "
              f"{100.0 * fail_after_scored / after_scored:.1f}%")
    if after_fail:
        print(f"  P(fail | prev failed) = {fail_after_fail}/{after_fail} = "
              f"{100.0 * fail_after_fail / after_fail:.1f}%")

    failures = 0

    last = term[-1]
    ok = last["status"] != "failed"
    print(f"GATE epoch_last_terminal_scored: {'PASS' if ok else 'FAIL'} - "
          f"newest terminal receipt {last['sub']} is {last['status']} ({last['created']})")
    if not ok:
        print("  HOLD. Historically ~89% of fires launched in this state returned")
        print("  nothing. Wait for a scored receipt before spending a draw.")
        failures += 1

    if len(term) >= 2:
        two = term[-2:]
        ok2 = not all(r["status"] == "failed" for r in two)
        print(f"GATE epoch_last_two_not_both_failed: {'PASS' if ok2 else 'FAIL'} - "
              f"{two[0]['sub']}={two[0]['status']}, {two[1]['sub']}={two[1]['status']}")
        if not ok2:
            print("  HOLD HARDER. Two consecutive failures preceded a third ~94% of")
            print("  the time in the record.")
            failures += 1

    clean = 0
    for r in reversed(term):
        if r["status"] == "failed":
            break
        clean += 1
    span = (term[-1]["t"] - term[-1 - clean]["t"]).total_seconds() / 3600.0 \
        if clean and len(term) > clean else float("nan")
    print(f"  consecutive clean terminal receipts: {clean}"
          + (f" over {span:.1f} h" if span == span else ""))

    ok3 = not inflight
    print(f"GATE epoch_slot_free: {'PASS' if ok3 else 'FAIL'} - "
          + ("no submission in flight" if ok3 else
             ", ".join(f"{r['sub']} {r['status']} since {r['created']}" for r in inflight)))
    if not ok3:
        print("  A submission is still being adjudicated. Firing now either queues")
        print("  behind it or wastes the slot; also, its verdict is the freshest")
        print("  reading of the bar you will ever get - wait for it.")
        failures += 1

    print()
    if failures:
        print(f"{failures} epoch gate(s) FAILED - do not fire.")
        sys.exit(1)
    print("all epoch gates PASS - the account is in a state that has historically")
    print("returned a score. This says nothing about whether the candidate is fast")
    print("enough; it only says a fire is unlikely to be thrown away.")


if __name__ == "__main__":
    main()
