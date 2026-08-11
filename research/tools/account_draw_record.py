#!/usr/bin/env python3
"""Nonparametric check on P(one draw clears the bar), from the shared account's own
official submission record.

Input: research/receipts/account_submissions_1254Z.tsv, a verbatim-derived dump of
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
TSV = os.path.join(HERE, os.pardir, "receipts", "account_submissions_1254Z.tsv")


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
            try:
                val = float(score)
            except ValueError:
                val = None
            rows.append((sub, solver, status, val, created))
    return rows


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
    print(f"non-terminal rows at 12:54Z        {[(r[0], r[2], r[4]) for r in nonterminal]}")
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
    for p, name in ((0.0095, "model, normal tail"), (0.0148, "model, empirical tail")):
        print(f"    {name:<24} {p * 100:.2f}%  ->  {p * (1 - fr) * 100:.2f}% "
              f"after the {fr * 100:.0f}% recent failure rate")
    print()

    print("Interpretation (the only claim this script supports):")
    print("  0 of", len(allv), "official scored draws on this account ever reached the bar;")
    print("  the best was", f"{max(allv):.8f}", f"({(max(allv)/BAR - 1)*100:+.4f}% vs bar).")
    print("  Rule of three on the full record bounds P(one draw >= bar) at",
          f"<= {3.0/len(allv)*100:.2f}%.")
    print("  Brief sec.2's model-based 0.95%-1.48% sits inside that bound, so the model")
    print("  survives a check that assumes no distribution at all. Anything like the")
    print("  retracted 15.6% does not: at p=0.156, seeing 0 clears in", len(allv),
          "draws has")
    print("  probability", f"{(1-0.156)**len(allv):.3g}", "- which is why that number was wrong.")
    print()
    print("What this does NOT show: these rows are not one program, so the sd printed")
    print("above mixes code changes with draw noise and must not be quoted as a draw sd.")
    print("The bound is valid regardless, because it counts clears, not variance.")


if __name__ == "__main__":
    main()
