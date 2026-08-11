#!/usr/bin/env python3
"""Audit the ranked acceptance band against the official receipt stream.

The harness once carried a notice (removed by advisor commit 279b6e24) claiming
the ranked run enforces decode_speedup in [0.980, 1.053] and prefill_speedup in
[0.952, 1.053] on top of the 0.95 floors, and that a larger gain must be
"CHUNKED across submissions or the ranked run fails with
failure_category=acceptance_band_failed".

Sources/MLXFastCore/Score.swift evaluateTimedRun() checks the CANDIDATE leg
against the SAME-RUN baseline leg with decodeBandUp=0.02, decodeBandDown=0.05,
prefillBandUp=0.05, prefillBandDown=0.05.

If that band were enforced on ranked submissions, no receipt could show a
candidate more than 5% faster than its own baseline. This script tests that
directly, and also tabulates every distinct rejectionReason in the stream.

Usage: python3 research/fern_r109f_band_audit.py [receipts.json]
"""
import collections
import json
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_p3.json"

DECODE_UP, DECODE_DOWN = 0.02, 0.05
PREFILL_UP, PREFILL_DOWN = 0.05, 0.05


def main():
    with open(PATH) as fh:
        doc = json.load(fh)
    rows = doc["submissions"] if isinstance(doc, dict) else doc
    print("receipts loaded: %d" % len(rows))

    reasons = collections.Counter()
    statuses = collections.Counter()
    band_text = []
    for r in rows:
        statuses[r.get("status")] += 1
        reason = (r.get("rejectionReason") or "").strip()
        reasons[reason] += 1
        blob = "%s %s" % (reason, r.get("note") or "")
        if "acceptance_band" in blob or "acceptance band" in blob:
            band_text.append((r.get("id"), r.get("solverUsername"), reason[:90]))

    print("\n=== statuses ===")
    for k, v in statuses.most_common():
        print("  %-12s %d" % (k, v))

    print("\n=== distinct rejectionReason values ===")
    for k, v in reasons.most_common():
        print("  %5d  %s" % (v, (k[:110] if k else "(empty)")))

    print("\n=== receipts whose reason/note mentions the acceptance band ===")
    if band_text:
        for t in band_text:
            print("  %s" % (t,))
    else:
        print("  NONE in %d receipts" % len(rows))

    # Does any scored receipt violate the code's band, candidate vs own baseline?
    n = 0
    dviol = pviol = 0
    worst_d = None
    tight_p = None
    for r in rows:
        m = r.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (d and p and bd and bp):
            continue
        n += 1
        # candidate must lie in [ref*(1-down), ref*(1+up)] for the band to pass
        if d < bd * (1 - DECODE_DOWN) or d > bd * (1 + DECODE_UP):
            dviol += 1
            ratio = d / bd
            if worst_d is None or ratio < worst_d[0]:
                worst_d = (ratio, r.get("id"), r.get("solverUsername"), r.get("status"))
        if p < bp * (1 - PREFILL_DOWN) or p > bp * (1 + PREFILL_UP):
            pviol += 1

    print("\n=== code-literal band applied to candidate vs same-run baseline ===")
    print("full-leg receipts: %d" % n)
    print("decode band violations : %d (%.1f%%)" % (dviol, 100.0 * dviol / max(n, 1)))
    print("prefill band violations: %d (%.1f%%)" % (pviol, 100.0 * pviol / max(n, 1)))
    if worst_d:
        print("most extreme decode ratio cand/base = %.5f  id=%s solver=%s status=%s" % worst_d)
    print(
        "\nVERDICT: if every scored receipt violates the band yet is scored and\n"
        "ranked, evaluateTimedRun()'s band is NOT the ranked gate for candidate\n"
        "submissions. It is an equivalence check for runs where candidate is\n"
        "expected to equal baseline."
    )

    # Second reading: band as a HOST-VALIDITY gate on the runner's own baseline
    # legs against the pinned constants.
    REF_D = 0.01385621216015625
    REF_P = 0.00036751938916015626
    print("\n=== band read as host-validity gate: same-run baseline vs pinned ===")
    dr = []
    pr = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        if not (bd and bp):
            continue
        dr.append(REF_D / bd)
        pr.append(REF_P / bp)
    if dr:
        dr.sort()
        pr.sort()
        print(
            "pinned/observed baseline decode : min %.5f  p1 %.5f  med %.5f  p99 %.5f  max %.5f"
            % (dr[0], dr[len(dr) // 100], dr[len(dr) // 2], dr[99 * len(dr) // 100], dr[-1])
        )
        print(
            "pinned/observed baseline prefill: min %.5f  p1 %.5f  med %.5f  p99 %.5f  max %.5f"
            % (pr[0], pr[len(pr) // 100], pr[len(pr) // 2], pr[99 * len(pr) // 100], pr[-1])
        )
        dout = sum(1 for x in dr if x < 1 - DECODE_DOWN or x > 1 + DECODE_UP)
        pout = sum(1 for x in pr if x < 1 - PREFILL_DOWN or x > 1 + PREFILL_UP)
        print("baseline decode outside [%.3f,%.3f] : %d / %d" % (1 - DECODE_DOWN, 1 + DECODE_UP, dout, len(dr)))
        print("baseline prefill outside [%.3f,%.3f]: %d / %d" % (1 - PREFILL_DOWN, 1 + PREFILL_UP, pout, len(pr)))


if __name__ == "__main__":
    main()
