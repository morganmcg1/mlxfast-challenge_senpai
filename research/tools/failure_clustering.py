#!/usr/bin/env python3
"""Is the recent clean fire record evidence that packaging is EASY, or evidence that
packaging is being WATCHED?

Context. In #746 the advisor bounded the value of my pre-flight gates by the current
per-fire probability of a `failed` receipt (a fire that returns no score at all):

    all terminal fires      n=176  failed=70  = 39.8%
    last 40 terminal fires  n=40   failed=0   =  0.0%   -> rule of three: <= 7.5%

and then flagged an open question that the aggregate rate cannot answer:

    "the 0/40 recent record may partly reflect that someone *was already checking*
     before firing ... consistent both with 'packaging is now easy' and with
     'packaging is being watched'. Neither is distinguishable from the data I have."

This script asks whether the *ordering* of the failures - which the aggregate throws
away - separates those two stories. It is deliberately assumption-light: no model of
score, no normal tail, only the chronological sequence of terminal statuses.

What the two stories predict about the sequence:

  EASY / EPOCH-CAUSE      failures arrive in a few dense contiguous bursts tied to a
                          particular window (one broken tree, one bad harness, one
                          bad host). Strong positive serial correlation; a runs test
                          sees far fewer runs than chance; failure probability is
                          near 1 inside a burst and near 0 outside it.

  WATCHED / LEARNING      failures thin out gradually as the operator gets better at
                          checking. Weak-to-moderate serial correlation, no sharp
                          boundary, and the per-day rate declines smoothly rather
                          than dropping off a cliff.

  BERNOULLI NULL          failures are independent with a constant rate; the runs
                          test is unremarkable and the recent clean stretch is just
                          luck. Under p_hat = 0.398 a clean run of 40 has
                          probability 0.602**40 = 2.9e-9, so this null is dead on
                          arrival - which is itself the point: SOMETHING changed.

Input: the verbatim `mlxfast submissions` dump the advisor took at 12:54Z on
2026-08-11. It lives on the advisor branch, not on mine, so by default this script
reads it out of git rather than duplicating it:

    git show <ref>:research/receipts/account_submissions_1254Z.tsv

Usage:
    python3 research/tools/failure_clustering.py
    python3 research/tools/failure_clustering.py --tsv /path/to/dump.tsv
"""

import argparse
import datetime as dt
import math
import os
import subprocess
import sys

ADVISOR_REF = "origin/codex/mlxfast-maple-20260804-advisor"
TSV_IN_REF = "research/receipts/account_submissions_1254Z.tsv"
TERMINAL = {"failed", "rejected", "promoted"}


def load_text(args):
    if args.tsv:
        with open(args.tsv) as fh:
            return fh.read(), args.tsv
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    local = os.path.join(root, TSV_IN_REF)
    if os.path.exists(local):
        with open(local) as fh:
            return fh.read(), local
    spec = f"{args.ref}:{TSV_IN_REF}"
    out = subprocess.run(
        ["git", "show", spec], capture_output=True, text=True, cwd=root,
    )
    if out.returncode != 0:
        sys.exit(f"could not read {spec}: {out.stderr.strip()}")
    return out.stdout, spec


def parse(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        sub, solver, status, score, created = (p.strip() for p in parts[:5])
        # "8/7/26, 5:06 AM"
        stamp = dt.datetime.strptime(created, "%m/%d/%y, %I:%M %p")
        try:
            val = float(score)
        except ValueError:
            val = None
        rows.append({"sub": sub, "solver": solver, "status": status,
                     "score": val, "t": stamp})
    rows.sort(key=lambda r: r["t"])
    return rows


def runs_test(seq):
    """Wald-Wolfowitz runs test on a binary sequence. Returns (runs, expected, sd, z)."""
    n1 = sum(seq)
    n0 = len(seq) - n1
    if n1 == 0 or n0 == 0:
        return None
    runs = 1 + sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    n = n0 + n1
    mu = 1.0 + 2.0 * n0 * n1 / n
    var = 2.0 * n0 * n1 * (2.0 * n0 * n1 - n) / (n * n * (n - 1.0))
    sd = math.sqrt(var)
    return runs, mu, sd, (runs - mu) / sd


def blocks(seq):
    """Contiguous run-lengths of 1s and 0s, in order."""
    out = []
    cur, count = seq[0], 1
    for v in seq[1:]:
        if v == cur:
            count += 1
        else:
            out.append((cur, count))
            cur, count = v, 1
    out.append((cur, count))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--ref", default=ADVISOR_REF)
    args = ap.parse_args()

    text, src = load_text(args)
    rows = parse(text)
    term = [r for r in rows if r["status"] in TERMINAL]
    seq = [1 if r["status"] == "failed" else 0 for r in term]
    nf = sum(seq)

    print(f"SOURCE            {src}")
    print(f"rows parsed       {len(rows)}   terminal {len(term)}   failed {nf} "
          f"({100.0 * nf / len(term):.1f}%)")
    print(f"window            {term[0]['t']:%Y-%m-%d %H:%M} .. {term[-1]['t']:%Y-%m-%d %H:%M}")
    print()

    print("== 1. chronological terminal sequence (F=failed, .=scored) ==")
    line = "".join("F" if v else "." for v in seq)
    for i in range(0, len(line), 60):
        print(f"  {i:>4}  {line[i:i + 60]}")
    print()

    print("== 2. block structure ==")
    bl = blocks(seq)
    fb = [n for v, n in bl if v == 1]
    print(f"  blocks total        {len(bl)}   failure blocks {len(fb)}")
    print(f"  failure block sizes {sorted(fb, reverse=True)}")
    biggest = max(fb) if fb else 0
    print(f"  largest failure block {biggest} of {nf} failures "
          f"({100.0 * biggest / nf:.1f}% of all failures)")
    top3 = sum(sorted(fb, reverse=True)[:3])
    print(f"  three largest blocks  {top3} of {nf} ({100.0 * top3 / nf:.1f}%)")
    print()

    print("== 3. Wald-Wolfowitz runs test (clustering vs independent order) ==")
    rt = runs_test(seq)
    if rt:
        runs, mu, sd, z = rt
        print(f"  observed runs {runs}   expected under independence {mu:.1f} "
              f"+/- {sd:.1f}   z = {z:+.2f}")
        print("  z very negative => failures clump (epoch cause). "
              "z near 0 => order looks independent.")
    print()

    print("== 4. per-calendar-day rate ==")
    print(f"  {'day':<12}{'n':>4}{'failed':>8}{'rate':>9}   sequence")
    days = {}
    for r, v in zip(term, seq):
        days.setdefault(r["t"].date(), []).append(v)
    for d in sorted(days):
        v = days[d]
        s = "".join("F" if x else "." for x in v)
        print(f"  {str(d):<12}{len(v):>4}{sum(v):>8}{100.0 * sum(v) / len(v):>8.0f}%   {s}")
    print()

    print("== 5. how clean is the clean stretch, and what preceded it ==")
    last_f = max(i for i, v in enumerate(seq) if v)
    since = len(seq) - 1 - last_f
    print(f"  last failure at terminal index {last_f} "
          f"({term[last_f]['t']:%Y-%m-%d %H:%M}, submission {term[last_f]['sub']})")
    print(f"  clean terminal fires since then: {since}")
    print(f"  elapsed since last failure: "
          f"{(term[-1]['t'] - term[last_f]['t']).total_seconds() / 3600.0:.1f} h")
    pre = seq[:last_f + 1]
    print(f"  rate BEFORE and including that failure: "
          f"{sum(pre)}/{len(pre)} = {100.0 * sum(pre) / len(pre):.1f}%")
    print(f"  rate AFTER: 0/{since} = 0.0%   rule of three bound "
          f"{300.0 / since:.1f}%" if since else "")
    print()

    print("== 6. was the pre-clean regime itself gradual or bursty? ==")
    # Sliding window of 20 terminal fires, printed sparsely.
    w = 20
    print(f"  window={w}, stride=10, rate in %:")
    marks = []
    for i in range(0, len(seq) - w + 1, 10):
        marks.append(f"[{i:>3}]{100.0 * sum(seq[i:i + w]) / w:>4.0f}")
    for i in range(0, len(marks), 8):
        print("   " + "  ".join(marks[i:i + 8]))
    print()

    print("== 7. repeated-commit check (was one broken tree fired many times?) ==")
    fails = [r for r in term if r["status"] == "failed"]
    subs = [r["sub"] for r in fails]
    print(f"  failed receipts {len(subs)}   distinct submission ids {len(set(subs))}")
    print("  (ids are per-submission, so this cannot prove tree identity; "
          "burst timing is the evidence.)")
    gaps = [(b["t"] - a["t"]).total_seconds() / 60.0 for a, b in zip(fails, fails[1:])]
    if gaps:
        gaps_sorted = sorted(gaps)
        med = gaps_sorted[len(gaps_sorted) // 2]
        under30 = sum(1 for g in gaps if g <= 30)
        print(f"  consecutive-failure gaps: median {med:.0f} min, "
              f"{under30}/{len(gaps)} within 30 min of the previous failure")
    print()

    print("== 8. first-order conditional risk (the decision rule that follows) ==")
    # If failures are time-local, the single most informative thing a slot-holder can
    # read before firing is the status of the PREVIOUS terminal receipt on the account.
    tt = {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}
    for a, b in zip(seq, seq[1:]):
        tt[(a, b)] += 1
    n_after_scored = tt[(0, 0)] + tt[(0, 1)]
    n_after_failed = tt[(1, 0)] + tt[(1, 1)]
    p_after_scored = tt[(0, 1)] / n_after_scored if n_after_scored else float("nan")
    p_after_failed = tt[(1, 1)] / n_after_failed if n_after_failed else float("nan")
    print(f"  P(this fire fails | previous terminal receipt SCORED) = "
          f"{tt[(0, 1)]}/{n_after_scored} = {100.0 * p_after_scored:.1f}%")
    print(f"  P(this fire fails | previous terminal receipt FAILED) = "
          f"{tt[(1, 1)]}/{n_after_failed} = {100.0 * p_after_failed:.1f}%")
    print(f"  unconditional                                        = "
          f"{nf}/{len(seq)} = {100.0 * nf / len(seq):.1f}%")
    # Two consecutive failures as the burst detector.
    two = [i for i in range(len(seq) - 2) if seq[i] and seq[i + 1]]
    if two:
        hit = sum(1 for i in two if seq[i + 2])
        print(f"  P(next fails | the previous TWO both failed)          = "
              f"{hit}/{len(two)} = {100.0 * hit / len(two):.1f}%")
    print()

    print("== 9. what this does and does not settle ==")
    print("  Read items 2, 3, 4 and 8 together. The verdict text is in")
    print("  research/r129g_failure_clustering.md; this script only prints evidence.")


if __name__ == "__main__":
    main()
