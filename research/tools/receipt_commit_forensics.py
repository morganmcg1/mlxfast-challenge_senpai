#!/usr/bin/env python3
"""Decisive discriminator for the #746 open question, using a column the earlier dump
threw away: the per-receipt `commit`.

`mlxfast submissions` prints eight columns. The 12:54Z dump on the advisor branch kept
five (submission, solver, status, score, created) and dropped `metrics`, `diff` and
`commit`. The `commit` column is the submitted tree's identity, which turns a
correlational question into a nearly experimental one:

  If the SAME commit appears with a `failed` receipt at one time and a scored receipt
  at another, then failure is not a property of the tree -> the 8/7-8/8 burst was
  time-local (service or shared harness), and no local pre-flight gate could have
  prevented it.

  If every failed commit is distinct from every scored commit, tree content and time
  are confounded in this record and the question stays open on this evidence.

Also reported: whether the burst fired distinct trees (a fleet iterating) or re-fired
a few (one broken tree fired repeatedly), and whether `failed` receipts carry any
error text at all (they do not - metrics is `n/a`, so the CLI gives no cause).

Run:
    COLUMNS=4000 mlxfast submissions > dump.txt
    python3 research/tools/receipt_commit_forensics.py --dump dump.txt

`--dump -` reads stdin. Without --dump the script runs the CLI itself with a wide
COLUMNS so the metrics column is not truncated. This script never submits.
"""

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

TERMINAL = {"failed", "rejected", "promoted"}
# The current bar, as used by research/tools/account_draw_record.py on the advisor
# branch. A submission is promoted only if it beats this.
BAR = 2.6195531094824


def read_dump(args):
    if args.dump == "-":
        return sys.stdin.read()
    if args.dump:
        with open(args.dump) as fh:
            return fh.read()
    env = dict(os.environ, COLUMNS="4000")
    out = subprocess.run(["mlxfast", "submissions"], capture_output=True,
                         text=True, env=env)
    if out.returncode != 0:
        sys.exit(f"mlxfast submissions failed: {out.stderr.strip()[:200]}")
    return out.stdout


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def parse(text):
    # The CLI colours the status and diff cells, so the raw dump carries ANSI escapes
    # (e.g. "\x1b[31mrejected\x1b[39m"). A naive split() therefore never matches
    # "rejected"/"failed" and silently yields zero rows - strip first.
    rows = []
    for line in ANSI.sub("", text).splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        if parts[2] not in TERMINAL and parts[2] not in {"validating", "queued"}:
            continue
        sub, solver, status = parts[0], parts[1], parts[2]
        score = parts[3]
        commit = parts[-4]
        created = " ".join(parts[-3:])
        try:
            stamp = dt.datetime.strptime(created, "%m/%d/%y, %I:%M %p")
        except ValueError:
            continue
        rows.append({"sub": sub, "solver": solver, "status": status,
                     "score": score, "commit": commit, "t": stamp})
    rows.sort(key=lambda r: r["t"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump")
    args = ap.parse_args()

    rows = parse(read_dump(args))
    term = [r for r in rows if r["status"] in TERMINAL]
    failed = [r for r in term if r["status"] == "failed"]
    scored = [r for r in term if r["status"] != "failed"]

    print(f"parsed rows        {len(rows)}   terminal {len(term)}   "
          f"failed {len(failed)}   scored {len(scored)}")
    if rows:
        print(f"window             {rows[0]['t']:%m-%d %H:%M} .. {rows[-1]['t']:%m-%d %H:%M}")
    nonterm = [r for r in rows if r["status"] not in TERMINAL]
    for r in nonterm:
        print(f"non-terminal now   {r['sub']} {r['status']} created {r['t']:%m-%d %H:%M}")
    print()

    fset, sset = {}, {}
    for r in failed:
        fset.setdefault(r["commit"], []).append(r)
    for r in scored:
        sset.setdefault(r["commit"], []).append(r)

    print("== A. did any single commit both fail and score? ==")
    both = sorted(set(fset) & set(sset))
    print(f"  distinct failed commits {len(fset)} of {len(failed)} failed receipts")
    print(f"  distinct scored commits {len(sset)} of {len(scored)} scored receipts")
    print(f"  commits seen in BOTH states: {len(both)}")
    for c in both:
        ftimes = ", ".join(f"{r['t']:%m-%d %H:%M}" for r in fset[c])
        stimes = ", ".join(f"{r['t']:%m-%d %H:%M}({r['score'][:6]})" for r in sset[c])
        print(f"    {c}  failed at [{ftimes}]  scored at [{stimes}]")
    if not both:
        print("    none -> tree content and time are confounded in this record;")
        print("    the commit column cannot settle service-vs-tree by itself.")
    print()

    print("== B. inside the burst, was one tree re-fired or many tried? ==")
    lo = dt.datetime(2026, 8, 7, 9, 40)
    hi = dt.datetime(2026, 8, 8, 18, 0)
    burst = [r for r in term if lo <= r["t"] <= hi]
    bf = [r for r in burst if r["status"] == "failed"]
    print(f"  burst window {lo:%m-%d %H:%M} .. {hi:%m-%d %H:%M}: "
          f"{len(burst)} terminal, {len(bf)} failed")
    print(f"  distinct commits among burst failures: {len({r['commit'] for r in bf})}")
    reused = {c: v for c, v in fset.items() if len(v) > 1}
    print(f"  commits with more than one failed receipt: {len(reused)}")
    for c, v in sorted(reused.items(), key=lambda kv: -len(kv[1]))[:8]:
        print(f"    {c} x{len(v)}  " + ", ".join(f"{r['t']:%m-%d %H:%M}" for r in v))
    print()

    print("== C. do failed receipts carry any diagnosable cause? ==")
    print("  the CLI prints metrics/diff as n/a for every failed receipt, so no")
    print("  error string is available from this surface; cause must be inferred.")
    print()

    print("== D. most recent terminal receipt (the pre-fire read) ==")
    last = term[-1]
    print(f"  {last['sub']}  {last['status']}  score {last['score']}  "
          f"{last['t']:%m-%d %H:%M}  commit {last['commit']}")
    tail = [1 if r["status"] == "failed" else 0 for r in term[-10:]]
    print("  last 10 terminal: " + "".join("F" if v else "." for v in tail))
    print()

    print("== E. what a draw has actually been worth lately (vs the bar) ==")
    vals = []
    for r in scored:
        try:
            vals.append((r["t"], r["sub"], float(r["score"])))
        except ValueError:
            continue
    print(f"  bar (best promoted) = {BAR:.13f}")
    if vals:
        bt, bs, bv = max(vals, key=lambda x: x[2])
        print(f"  account best ever   = {bv:.6f}  ({bs}, {bt:%m-%d %H:%M})  "
              f"gap {100.0 * (bv / BAR - 1.0):+.2f}%")
        recent = vals[-12:]
        print("  last 12 scored fires:")
        for t, s, v in recent:
            print(f"    {t:%m-%d %H:%M}  {s}  {v:.6f}   {100.0 * (v / BAR - 1.0):+6.2f}%")
        clears = [v for _, _, v in vals if v >= BAR]
        print(f"  scored fires at or above the bar: {len(clears)}/{len(vals)}")


if __name__ == "__main__":
    main()
