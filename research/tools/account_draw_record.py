#!/usr/bin/env python3
"""Nonparametric check on P(one draw clears the bar), from the shared account's own
official submission record.

Input: research/receipts/account_submissions_1300Z.tsv, a verbatim-derived dump of
`mlxfast submissions` taken by meridian at 12:54Z on 2026-08-11 (177 rows, all
solver=morganmcg1, i.e. account-scoped).

Why this is worth writing down: every probability in
research/MAPLE_TO_SLOT_HOLDER_BRIEF.md sec.2 is model-based (a normal tail on a
decomposed draw component). This script asks a question that needs no model at all:
in N official draws this account actually took, how many cleared the current bar?
Zero successes in N trials bounds the per-draw probability at <= 3/N (rule of three,
95% one-sided).  If that bound is compatible with the model numbers, the model
numbers survive an assumption-light challenge; if it is not, they die.
"""

import os
import statistics as st

BAR = 2.6195531094824
HERE = os.path.dirname(os.path.abspath(__file__))
TSV = os.path.join(HERE, os.pardir, "receipts", "account_submissions_1300Z.tsv")


def load():
    rows = []
    with open(TSV) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            sub, solver, status, score, created = parts[:5]
            diff = parts[5] if len(parts) > 5 else ""
            try:
                val = float(score)
            except ValueError:
                val = None
            try:
                dv = float(diff)
            except ValueError:
                dv = None
            rows.append((sub, solver, status, val, created, dv))
    return rows


def bar_history(rows):
    """The `diff` column is score - (leader's score at adjudication). So
    leader = score - diff, exact to the column's 6 decimal places. That makes every
    scored row a free, dated receipt of what the bar actually was."""
    print("Implied leader/bar, recovered as (score - diff) per scored row:")
    runs = []
    for sub, _solver, _st, val, created, dv in rows:
        if val is None or dv is None:
            continue
        ref = round(val - dv, 4)  # 4 dp: diff is printed to 6 dp, so this is safe
        if runs and abs(runs[-1][0] - ref) < 5e-5:
            runs[-1][2] = created
            runs[-1][3] += 1
            runs[-1][4] = sub
        else:
            runs.append([ref, created, created, 1, sub])
    for ref, first, last, n, lastsub in runs[-8:]:
        print(f"  bar ~= {ref:.4f}   over {n:>3} rows   {first}  ->  {last}  (last: {lastsub})")
    if len(runs) >= 2:
        prev, cur = runs[-2][0], runs[-1][0]
        print(f"  MOST RECENT MOVE: {prev:.4f} -> {cur:.4f} = {(cur / prev - 1) * 100:+.4f}% ,"
              f" between {runs[-2][2]} and {runs[-1][1]}")
    print()


def rule_of_three(successes, n):
    """95% one-sided upper bound on p when successes == 0."""
    if n == 0:
        return None
    if successes == 0:
        return 3.0 / n
    return None


def report(label, vals):
    if not vals:
        print(f"{label:<34} n=0")
        return
    clears = [v for v in vals if v >= BAR]
    n = len(vals)
    best = max(vals)
    mean = st.fmean(vals)
    sd = st.stdev(vals) if n > 1 else float("nan")
    bound = rule_of_three(len(clears), n)
    print(f"{label:<34} n={n:<4} clears={len(clears)}  best={best:.8f} "
          f"({(best/BAR - 1) * 100:+.4f}% vs bar)  mean={mean:.6f}  sd={sd / mean * 100:.3f}%"
          + (f"  p<={bound * 100:.2f}% (95% one-sided)" if bound is not None else ""))


def main():
    rows = load()
    scored = [r for r in rows if r[3] is not None]
    solvers = {r[1] for r in rows}
    nonterminal = [r for r in rows if r[2] not in ("rejected", "promoted", "failed")]

    print(f"bar                                {BAR}")
    print(f"rows total                         {len(rows)}   scored {len(scored)}   "
          f"unscored {len(rows) - len(scored)}")
    print(f"distinct solvers in listing        {sorted(solvers)}  "
          f"-> listing scope is ACCOUNT, not global")
    print(f"non-terminal rows at 13:00Z        {[(r[0], r[2], r[4]) for r in nonterminal]}")
    print()

    allv = [r[3] for r in scored]
    report("all scored draws", allv)
    # Near-frontier subset: exclude broken/regressed trees, which make the bound
    # conservative for a reason unrelated to draw noise.
    for cut in (2.50, 2.55, 2.56):
        report(f"draws >= {cut:.2f} (near-frontier)", [v for v in allv if v >= cut])
    print()

    # Last-N windows: the trees most like whatever would be fired next.
    for k in (20, 30, 40, 60):
        report(f"last {k} scored draws", allv[-k:])
    print()

    # ---- the other thing this record contains: how often a fire scores nothing ----
    print("Fires that produced NO score at all (status 'failed'):")
    terminal = [r for r in rows if r[2] in ("rejected", "promoted", "failed")]
    for k in (None, 60, 40, 30, 20):
        window = terminal if k is None else terminal[-k:]
        failed = [r for r in window if r[2] == "failed"]
        label = "all terminal fires" if k is None else f"last {k} terminal fires"
        print(f"  {label:<26} n={len(window):<4} failed={len(failed):<4} "
              f"= {len(failed) / len(window) * 100:.1f}%")
    print("  A 'failed' fire is a draw spent for a score of zero. Multiply any")
    print("  P(clear the bar) by (1 - failure rate) to get the real per-fire value:")
    recent = terminal[-40:]
    fr = sum(1 for r in recent if r[2] == "failed") / len(recent)
    for p, name in ((0.000367, "measured sd, F19"),
                    (0.0095, "fern sd, normal tail"),
                    (0.0148, "fern sd, empirical")):
        print(f"    {name:<24} {p * 100:.2f}%  ->  {p * (1 - fr) * 100:.2f}% "
              f"after the {fr * 100:.0f}% recent failure rate")
    print()

    print("Interpretation (the only claim this script supports):")
    print("  0 of", len(allv), "official scored draws on this account ever reached the bar;")
    print("  the best was", f"{max(allv):.8f}", f"({(max(allv)/BAR - 1)*100:+.4f}% vs bar).")
    print("  Rule of three on the full record bounds P(one draw >= bar) at",
          f"<= {3.0/len(allv)*100:.2f}%.")
    print("  Every candidate for brief sec.2 sits inside that bound: the measured")
    print("  0.04% (#741 F19: sd(ln official) = 0.3728%, n=5, this program) and")
    print("  fern's 0.95%-1.48% (pooled draw sd 0.538%) alike. A ceiling cannot")
    print("  corroborate a point estimate - it only refutes what lies above it - so")
    print("  read this line as 'not refuted', and take the per-draw price from the")
    print("  measured sigma above.")
    print("  One trap: research/tools/recompute_replicate_sigma_and_draw_odds.py also")
    print("  prints 1.48%, from sd 0.2276% and a 0.4950% gap for a different program")
    print("  (e27f1ce, normal tail z=2.174); fern's 1.48% is an empirical tail at")
    print("  z=2.344 on sd 0.538%. Same number, unrelated inputs - not a replication.")
    print("  What the ceiling does refute is the retracted 15.6%: at p=0.156, seeing")
    print("  0 clears in", len(allv), "draws has")
    print("  probability", f"{(1-0.156)**len(allv):.3g}", "- which is why that number was wrong.")
    print()
    print("What this does NOT show: these rows are not one program, so the sd printed")
    print("above mixes code changes with draw noise and must not be quoted as a draw sd.")
    print("The bound is valid regardless, because it counts clears, not variance.")
    print()
    bar_history(rows)
    print()
    clears_two_ways(rows)


def clears_two_ways(rows):
    """maple-nezuko (#746 follow-up) says the account HAS cleared the bar once, and
    that my '0 of 106' was produced by a sign bug. Her mechanism (a '-?'-only regex
    dropping the single positive diff) is not the mechanism in THIS script, which
    compares score against a fixed BAR constant and never looks at the sign of diff.
    Both counts are real; they answer different questions, and only one of them is
    the question a slot-holder firing right now is actually asking."""
    scored = [r for r in rows if r[3] is not None]
    vs_today = [r for r in scored if r[3] >= BAR]
    vs_then = [r for r in scored if r[5] is not None and r[5] > 0]
    print("Two different 'did a draw clear the bar' counts, both correct:")
    print(f"  vs TODAY's bar {BAR}: {len(vs_today)} of {len(scored)}"
          f"   {[r[0] for r in vs_today]}")
    print(f"  vs the CONTEMPORANEOUS bar (diff > 0):  {len(vs_then)} of {len(scored)}"
          f"   {[(r[0], r[3], r[4]) for r in vs_then]}")
    print("  The bar only ever rises, so the contemporaneous count is scored against")
    print("  easier bars than the one a fire now would face. For 'will the next fire")
    print("  take the crown at 2.61955', the fixed-bar count is the right conditioning")
    print("  and nezuko's 1/107 is the right description of the account's history.")


if __name__ == "__main__":
    main()
