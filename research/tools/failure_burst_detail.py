#!/usr/bin/env python3
"""Second discriminator for the #746 open question.

failure_clustering.py shows the 70 `failed` receipts are one time-local burst
(8/7-8/8, runs-test z = -10.78, 91.4% of all failures in three blocks). That leaves
two very different causes still standing, and they price a pre-flight gate in
opposite directions:

  PER-CANDIDATE DEFECT   the trees being iterated during those two days shared a
                         packaging/environment defect. A local pre-flight gate would
                         have caught them -> gates are worth something.

  EPOCH / SERVICE-LOCAL  during that window the service (or the shared harness) was
                         returning no-score receipts largely irrespective of what was
                         fired. A local pre-flight gate cannot see this and cannot
                         prevent it -> gates are worth ~0 against this failure mode,
                         and the useful guard is instead "is the account currently
                         scoring at all?"

The discriminator: inside the burst there are a few receipts that DID score. If those
scoring receipts are the *only* thing that differs (i.e. a different tree scored while
the iterated family failed), that favours a per-candidate defect. If scoring receipts
are scattered through the burst with ordinary scores, that favours an epoch cause
which was merely mostly-on rather than fully-on.

Prints the raw window so the reader can judge rather than trust a label.
"""

import argparse
import datetime as dt
import os
import subprocess
import sys

ADVISOR_REF = "origin/codex/mlxfast-maple-20260804-advisor"
TSV_IN_REF = "research/receipts/account_submissions_1254Z.tsv"
TERMINAL = {"failed", "rejected", "promoted"}


def load(args):
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if args.tsv:
        return open(args.tsv).read()
    local = os.path.join(root, TSV_IN_REF)
    if os.path.exists(local):
        return open(local).read()
    out = subprocess.run(["git", "show", f"{args.ref}:{TSV_IN_REF}"],
                         capture_output=True, text=True, cwd=root)
    if out.returncode != 0:
        sys.exit(f"could not read tsv: {out.stderr.strip()}")
    return out.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--ref", default=ADVISOR_REF)
    ap.add_argument("--lo", type=int, default=55)
    ap.add_argument("--hi", type=int, default=126)
    args = ap.parse_args()

    rows = []
    for line in load(args).splitlines():
        if line.startswith("#") or not line.strip():
            continue
        p = line.split("\t")
        if len(p) < 5:
            continue
        sub, solver, status, score, created = (x.strip() for x in p[:5])
        rows.append({"sub": sub, "status": status, "score": score,
                     "t": dt.datetime.strptime(created, "%m/%d/%y, %I:%M %p")})
    rows.sort(key=lambda r: r["t"])
    term = [r for r in rows if r["status"] in TERMINAL]

    print("idx  when              status     score              gap_min")
    prev = None
    for i, r in enumerate(term):
        if not (args.lo <= i <= args.hi):
            prev = r
            continue
        gap = "" if prev is None else f"{(r['t'] - prev['t']).total_seconds() / 60.0:7.0f}"
        star = "  <== SCORED INSIDE BURST" if r["status"] != "failed" else ""
        print(f"{i:>3}  {r['t']:%m-%d %H:%M}     {r['status']:<10} "
              f"{r['score']:<18} {gap}{star}")
        prev = r

    print()
    burst = [r for r in term[args.lo:args.hi + 1]]
    scored = [r for r in burst if r["status"] != "failed"]
    print(f"window rows {len(burst)}   failed {len(burst) - len(scored)}   scored {len(scored)}")
    print("scored-inside-burst scores: " + ", ".join(r["score"] for r in scored))
    print()
    print("Also: the whole-record cadence, to see whether the account simply fired")
    print("faster during the burst (a fast loop failing is different from a slow one).")
    for label, lo, hi in (("pre-burst   ", 0, 59), ("burst       ", 60, 122),
                          ("post-burst  ", 123, len(term) - 1)):
        seg = term[lo:hi + 1]
        span = (seg[-1]["t"] - seg[0]["t"]).total_seconds() / 3600.0
        print(f"  {label} n={len(seg):>3}  span {span:6.1f} h  "
              f"mean spacing {60.0 * span / max(1, len(seg) - 1):5.1f} min  "
              f"failed {sum(1 for r in seg if r['status'] == 'failed')}")


if __name__ == "__main__":
    main()
