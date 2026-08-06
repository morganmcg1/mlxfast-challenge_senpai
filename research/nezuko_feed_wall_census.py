#!/usr/bin/env python3
"""Wall-time budget census over the official mlxfast submission feed.

Research-only. Answers one question for the receipt-channel prefill ledger
instrument (research/PREFILL_LEDGER_INSTRUMENT.md): how much wall time does an
intentionally slowed candidate add to an official measure job, and how close
does that come to the workflow timeout?

Fetch the feed first (token is injected into the shell, never printed):

  curl -sS -H "Authorization: Bearer ${MLXFAST_API_TOKEN}" \
    "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions" \
    -o /tmp/feed.json

  python3 research/nezuko_feed_wall_census.py /tmp/feed.json

Key finding: the published wall fields are integer-quantized and the feed is
split into harness generations. Grouping by (harness_hash, checked_steps,
case_count) is mandatory; a pooled regression of wall time on candidate speed
returns a *negative* slope purely because the older harness did less
correctness work and happens to hold all the slow candidates.
"""
import json
import statistics
import sys
from collections import defaultdict

WALL = "benchmark_wall_seconds"
CORR = "correctness_seconds"
TIMED = "timed_benchmark_seconds"
PRE = "prefill_seconds_per_token"
DEC = "decode_seconds_per_token"
ERA_KEY = ("harness_hash", "checked_steps", "case_count")


def load(path):
    with open(path) as fh:
        raw = json.load(fh)
    subs = raw["submissions"] if isinstance(raw, dict) else raw
    rows = []
    for s in subs:
        m = s.get("officialMetrics") or {}
        if not isinstance(m, dict):
            continue
        m = (m.get("submission") or {}).get("officialMetrics", m)
        if m.get(PRE) is None or m.get(WALL) is None:
            continue
        rows.append(
            {
                "createdAt": s.get("createdAt"),
                "status": s.get("status"),
                "prefill_ms": m[PRE] * 512 * 1000.0,
                "decode_ms": m[DEC] * 1000.0 if m.get(DEC) else None,
                **{k: m.get(k) for k in (WALL, CORR, TIMED, "preflight_seconds")},
                **{k: m.get(k) for k in ERA_KEY},
            }
        )
    rows.sort(key=lambda r: r["createdAt"] or "")
    return rows


def q(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]


def describe(tag, rows):
    print(f"\n== {tag} (n={len(rows)}) ==")
    for f in (WALL, CORR, TIMED):
        v = [r[f] for r in rows if r[f] is not None]
        if not v:
            continue
        print(
            f"  {f:26s} med={statistics.median(v):7.2f} p90={q(v, 0.90):6.1f} "
            f"min={min(v):6.1f} max={max(v):6.1f}"
        )
    for f in ("prefill_ms", "decode_ms"):
        v = [r[f] for r in rows if r[f] is not None]
        if v:
            print(
                f"  {f:26s} med={statistics.median(v):7.3f} "
                f"min={min(v):7.3f} max={max(v):7.3f}"
            )


def ols2(rows, y):
    """y = a + b1*prefill_ms + b2*decode_ms via normal equations."""
    pts = [
        (r["prefill_ms"], r["decode_ms"], r[y])
        for r in rows
        if r[y] is not None and r["decode_ms"] is not None
    ]
    n = len(pts)
    if n < 6:
        return None
    mx1 = sum(p[0] for p in pts) / n
    mx2 = sum(p[1] for p in pts) / n
    my = sum(p[2] for p in pts) / n
    s11 = sum((p[0] - mx1) ** 2 for p in pts)
    s22 = sum((p[1] - mx2) ** 2 for p in pts)
    s12 = sum((p[0] - mx1) * (p[1] - mx2) for p in pts)
    s1y = sum((p[0] - mx1) * (p[2] - my) for p in pts)
    s2y = sum((p[1] - mx2) * (p[2] - my) for p in pts)
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-12:
        return None
    b1 = (s22 * s1y - s12 * s2y) / det
    b2 = (s11 * s2y - s12 * s1y) / det
    a = my - b1 * mx1 - b2 * mx2
    rmse = (
        sum((p[2] - (a + b1 * p[0] + b2 * p[1])) ** 2 for p in pts) / n
    ) ** 0.5
    return n, a, b1, b2, rmse


def main():
    rows = load(sys.argv[1] if len(sys.argv) > 1 else "/tmp/feed.json")
    describe("whole population with officialMetrics", rows)

    ok = [r for r in rows if r["status"] not in (None, "failed", "error")]
    describe("last 20 receipts carrying metrics", ok[-20:])

    print("\n== pooled OLS (INVALID: era-confounded, keep as a warning) ==")
    for y in (WALL, CORR, TIMED):
        f = ols2(rows, y)
        if f:
            n, a, b1, b2, rmse = f
            print(
                f"  {y:26s} n={n:5d} = {a:8.3f} {b1:+.5f}*prefill_ms "
                f"{b2:+.5f}*decode_ms  rmse={rmse:.2f}"
            )

    print("\n== harness eras (era key = harness_hash, checked_steps, case_count) ==")
    eras = defaultdict(list)
    for r in rows:
        eras[tuple(r[k] for k in ERA_KEY)].append(r)
    for key, grp in sorted(eras.items(), key=lambda kv: -len(kv[1])):
        if len(grp) < 5:
            continue
        hh = (key[0] or "?")[:10]
        dates = f"{(grp[0]['createdAt'] or '?')[:10]}..{(grp[-1]['createdAt'] or '?')[:10]}"
        dm = [r["decode_ms"] for r in grp if r["decode_ms"]] or [float("nan")]
        pm = [r["prefill_ms"] for r in grp]
        print(
            f"  n={len(grp):4d} h={hh} steps={key[1]} cases={key[2]} {dates}"
            f" P={min(pm):6.1f}-{max(pm):6.1f} D={min(dm):5.2f}-{max(dm):5.2f}"
            f" corr={q([r[CORR] for r in grp], 0.0)}-{q([r[CORR] for r in grp], 1.0)}"
            f" timed={q([r[TIMED] for r in grp], 0.0)}-{q([r[TIMED] for r in grp], 1.0)}"
            f" wall={q([r[WALL] for r in grp], 0.0)}-{q([r[WALL] for r in grp], 1.0)}"
        )

    print("\n== R1 envelope test (routed_gather_gemm x2, m=1) ==")
    cur = [r for r in rows if r["checked_steps"] == 1344]
    recent = cur[-20:]
    base_pre = statistics.median(r["prefill_ms"] for r in recent)
    base_dec = statistics.median(r["decode_ms"] for r in recent)
    inj_pre, inj_dec = 40.0, 1.95  # routed MoE share of each phase
    tgt_pre, tgt_dec = base_pre + inj_pre, base_dec + inj_dec
    print(f"  frontier now (current era): P={base_pre:.1f} ms  D={base_dec:.3f} ms/step")
    print(f"  R1 probe projection:        P={tgt_pre:.1f} ms  D={tgt_dec:.3f} ms/step")
    # Receipts already measured under the identical correctness configuration
    # that were at least as slow as the probe on the axis in question.
    for axis, key, tgt in (("prefill", "prefill_ms", tgt_pre), ("decode", "decode_ms", tgt_dec)):
        sl = [r for r in cur if (r[key] or 0) >= tgt]
        if sl:
            print(
                f"  receipts with {axis} >= probe under steps=1344: n={len(sl)}"
                f"  wall max={max(r[WALL] for r in sl)}"
                f"  corr max={max(r[CORR] for r in sl if r[CORR])}"
                f"  timed max={max(r[TIMED] for r in sl if r[TIMED])}"
            )
        else:
            print(f"  receipts with {axis} >= probe under steps=1344: NONE (extrapolating)")
    print(f"  observed all-time maxima: wall={max(r[WALL] for r in rows)} "
          f"corr={max(r[CORR] for r in rows if r[CORR])} "
          f"timed={max(r[TIMED] for r in rows if r[TIMED])}")


if __name__ == "__main__":
    main()
