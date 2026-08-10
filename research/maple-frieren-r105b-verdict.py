#!/usr/bin/env python3
"""Render the R105-B section 10 verdict tables straight from the analyser JSON
and apply the preregistered A0 / A1 decision tables (committed d8a5af7 before
any Phase A data existed).  Read-only; prints Markdown to stdout.

usage: maple-frieren-r105b-verdict.py <phaseA-outdir>
"""
import json
import os
import sys

CS_US_PER_PCT = 65.67          # us/step per 1% of the composite score
SESSION_SIGMA_PCT = 0.5393     # between-receipt sd of cs, relative percent
DECODE_PCT_PER_US = 0.015228   # percent of decode time per us/step
A0_TRIGGER_US = 8.0            # |mean| at or above this fires N-1
A0_PRECISION_US = 12.0         # half-width above this is inconclusive
A1_PREDICTION_US = 34.58       # #571 rung-2 cycle-blocked B->C

# Phase A arm names, sorted the way analyze-multi.py sorts them.
P0, P1, P1B, P5 = "P0", "P1", "P1B", "P5"


def pick(stats, key):
    """Return (record, estimator_label) for a contrast, preferring the
    cycle-blocked estimator that analyze-multi.py designates primary."""
    cyc = stats.get("cycle_contrasts", {}).get(key)
    if cyc and cyc.get("k", 0) >= 2:
        return cyc, "cycle-blocked"
    return stats["contrasts"][key], "per-rep"


def fmt(rec):
    return "%+8.2f | %6.2f | [%+8.2f, %+8.2f] | %d/%d | %d" % (
        rec["mean"], rec["half_width"], rec["lo"], rec["hi"],
        rec["pos"], rec["neg"], rec["k"])


def a0_verdict(rec):
    """Preregistered A0 table: P1 vs P1B is an A/A null on the very estimator
    that produced +34.58."""
    covers_zero = rec["lo"] <= 0.0 <= rec["hi"]
    big = abs(rec["mean"]) >= A0_TRIGGER_US
    if (not covers_zero) or big:
        return ("A0-FIRES-N1",
                "the A/A null is not null: the contrast estimator carries a "
                "bias of the same order as the effect, so +34.58 us/step is "
                "retracted and no receipt is spent")
    if rec["half_width"] <= A0_PRECISION_US:
        return ("A0-CLEARS",
                "the A/A null covers zero at adequate precision, so the "
                "contrast estimator is unbiased at the scale of the effect")
    return ("A0-INCONCLUSIVE",
            "the A/A null covers zero but only because the interval is wide; "
            "the estimator is neither vindicated nor convicted")


def a1_verdict(d01, d05, d15):
    """Preregistered A1 table over P0->P1 (cost of the shipped default),
    P0->P5 (cost of the same loads placed late) and P1->P5."""
    default_costs = d01["lo"] > 0.0
    late_is_free = d05["lo"] <= 0.0 <= d05["hi"]
    late_recovers = d15["hi"] < 0.0
    if default_costs and late_is_free and late_recovers:
        return ("V-PLACEMENT",
                "the shipped default costs end to end, the identical loads "
                "placed below the barriers cost nothing, and moving them down "
                "recovers the loss: the cost is the cross-barrier hoist")
    if default_costs and (not late_is_free) and d05["lo"] > 0.0:
        return ("V-PEEL",
                "both placements cost, so the price is the prefetch block "
                "itself (loads plus the 4-of-16 peel), not where it sits")
    if default_costs:
        return ("V-MIXED",
                "the shipped default costs end to end but the placement "
                "control does not cleanly separate hoist from loads")
    return ("V-NEITHER",
            "the shipped default does not cost end to end on this host; the "
            "+34.58 us/step premise does not reproduce")


def main():
    outdir = sys.argv[1]
    d = json.load(open(os.path.join(outdir, "analysis-multi.json")))
    stats = d["stats"]["median"]
    arms = d["arms"]

    print("Phase A: reps=%s warmup=%s arms=%s" % (d["reps"], d["warmup"],
                                                  ",".join(arms)))
    print("primary_estimator=%s precision=%s n2_fires=%s n5_fires=%s"
          % (d["primary_estimator"], json.dumps(d["precision"]),
             d["n2_fires"], d["n5_fires"]))
    print()

    print("| contrast | estimator | mean us/step | 95% hw | CI | pos/neg | K |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    recs = {}
    for key in sorted(stats["contrasts"]):
        rec, label = pick(stats, key)
        recs[key] = rec
        print("| `%s` | %s | %s |" % (key, label, fmt(rec)))
    print()

    print("| arm | level us/step |")
    print("| --- | --- |")
    for a in arms:
        print("| %s | %.2f |" % (a, stats["levels"][a]))
    print()

    print("| within-arm null | mean | 95% hw | CI | pos/neg | K |")
    print("| --- | --- | --- | --- | --- | --- |")
    for key in sorted(stats["nulls"]):
        print("| `%s` | %s |" % (key, fmt(stats["nulls"][key])))
    print()

    a0 = recs["%s->%s" % (P1, P1B)]
    v0, why0 = a0_verdict(a0)
    print("A0 (%s->%s): %s" % (P1, P1B, v0))
    print("  %s" % why0)
    print("  mean %+.2f us/step, hw %.2f, CI [%+.2f, %+.2f], %d/%d, K=%d"
          % (a0["mean"], a0["half_width"], a0["lo"], a0["hi"],
             a0["pos"], a0["neg"], a0["k"]))
    print()

    d01 = recs["%s->%s" % (P0, P1)]
    d05 = recs["%s->%s" % (P0, P5)]
    d15 = recs["%s->%s" % (P1, P5)]
    v1, why1 = a1_verdict(d01, d05, d15)
    print("A1: %s" % v1)
    print("  %s" % why1)
    print()

    print("| quantity | value |")
    print("| --- | --- |")
    eff = d01["mean"]
    print("| shipped default cost, end to end | %+.2f us/step |" % eff)
    print("| as percent of composite score | %+.3f %% |" % (eff / CS_US_PER_PCT))
    print("| as multiples of the session sigma | %.2f sigma |"
          % (abs(eff) / CS_US_PER_PCT / SESSION_SIGMA_PCT))
    print("| as percent of decode time | %+.3f %% |" % (eff * DECODE_PCT_PER_US))
    rep = recs["%s->%s" % (P0, P1B)]["mean"]
    print("| replicate arm estimate of the same cost | %+.2f us/step |" % rep)
    print("| #571 rung-2 prediction | %+.2f us/step |" % A1_PREDICTION_US)
    print("| reproduction ratio (this run / #571) | %.2f |"
          % (eff / A1_PREDICTION_US))


main()
