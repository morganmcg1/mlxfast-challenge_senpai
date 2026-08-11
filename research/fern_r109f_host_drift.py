#!/usr/bin/env python3
"""fern R109-F: is the ranked host drifting, or are the legs i.i.d.?

Motivation.  Our three identical-executable atlas-v3 receipts (t4 01:07Z,
t5 01:31Z, t6 01:54Z on 2026-08-11) came back with a *monotone* improvement on
the candidate decode leg -- 4928.23 -> 4907.11 -> 4897.05 us, a 0.63 % slide in
one direction over 47 minutes -- and therefore a monotone rise in normalized
score.  Two readings are possible:

  (a) i.i.d. noise.  P(monotone in 3 draws) = 1/3! * 2 = 1/3 for "monotone in
      either direction", 1/6 for a specified direction.  Not evidence on its own.
  (b) the ranked host drifts on a ~1 hour scale, in which case receipts close in
      time are correlated, our base(23:03-23:33Z) vs atlasv3(01:07-01:54Z) class
      comparison is confounded with time, and the right A/B protocol is to
      interleave arms rather than to run them in blocks.

This script decides between them with the *field* as the control: every other
solver's receipts in the same wall-clock window are subject to the same host, so
if the host drifted, their legs drifted too.

Usage: python3 research/fern_r109f_host_drift.py [cache.json]
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626

OURS = {
    "c1c0ba2c": ("t1", "r109F-base"),
    "88584270": ("t2", "r109F-base"),
    "e4078827": ("t3", "r109F-qhoist"),
    "ed40f3ee": ("t4", "r109F-atlasv3"),
    "0531544b": ("t5", "r109F-atlasv3"),
    "cb4de9e0": ("t6", "r109F-atlasv3"),
}


def normalized(m: dict) -> float:
    return (REF_D / m["decode_seconds_per_token"]) ** 0.75 * (
        REF_P / m["prefill_seconds_per_token"]
    ) ** 0.25


def full_leg(r: dict) -> bool:
    m = r.get("officialMetrics") or {}
    keys = (
        "decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    )
    return (
        all(m.get(k) for k in keys)
        and bool(m.get("passed_correctness"))
        and bool(r.get("officialScore"))
    )


def ts(r: dict) -> datetime:
    return datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))


def spearman(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")

    def rank(v: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: v[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (
        sum((a - mx) ** 2 for a in rx) ** 0.5 * sum((b - my) ** 2 for b in ry) ** 0.5
    )
    return num / den if den else float("nan")


def main() -> None:
    cache = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_p9.json"
    rows = [r for r in json.load(open(cache))["submissions"] if full_leg(r)]
    rows.sort(key=ts)

    print("=" * 92)
    print("fern R109-F: ranked-host drift test")
    print(f"  cache {cache}   full-leg correct receipts {len(rows)}")
    print("=" * 92)

    # ---- 1. our atlas-v3 trio, verbatim ----------------------------------
    print("\n1. the observation: three receipts of one identical executable")
    print(f"  {'id':<4} {'created':<22} {'cand dec us':>12} {'cand pf us':>11} "
          f"{'base dec us':>12} {'normalized':>11}")
    mine = [r for r in rows if r["id"][:8] in OURS]
    for r in mine:
        tag, klass = OURS[r["id"][:8]]
        m = r["officialMetrics"]
        print(f"  {tag:<4} {r['createdAt']:<22} {1e6*m['decode_seconds_per_token']:12.2f} "
              f"{1e6*m['prefill_seconds_per_token']:11.2f} "
              f"{1e6*m['baseline_decode_seconds_per_token']:12.2f} {normalized(m):11.6f}"
              f"   {klass}")

    # ---- 2. the field in the same window ---------------------------------
    lo = datetime(2026, 8, 10, 22, 30, tzinfo=timezone.utc)
    hi = datetime(2026, 8, 11, 3, 0, tzinfo=timezone.utc)
    win = [r for r in rows if lo <= ts(r) <= hi]
    others = [r for r in win if r["id"][:8] not in OURS]
    print(f"\n2. control: the field over the same window "
          f"[{lo:%m-%dT%H:%M}Z, {hi:%m-%dT%H:%M}Z]")
    print(f"   receipts in window {len(win)}  (ours {len(win)-len(others)}, "
          f"other solvers {len(others)})")

    if len(others) >= 3:
        t0 = min(ts(r) for r in others)
        x = [(ts(r) - t0).total_seconds() / 60 for r in others]
        print(f"   {'leg':<16} {'n':>3} {'spearman rho vs time':>22} {'early mean':>13} "
              f"{'late mean':>13} {'late-early':>11}")
        for leg, key, scale in (
            ("base decode", "baseline_decode_seconds_per_token", 1e6),
            ("base prefill", "baseline_prefill_seconds_per_token", 1e6),
            ("cand decode", "decode_seconds_per_token", 1e6),
            ("cand prefill", "prefill_seconds_per_token", 1e6),
        ):
            y = [scale * r["officialMetrics"][key] for r in others]
            rho = spearman(x, y)
            half = len(y) // 2
            early, late = statistics.mean(y[:half]), statistics.mean(y[-half:])
            print(f"   {leg:<16} {len(y):>3} {rho:>22.3f} {early:>13.2f} {late:>13.2f} "
                  f"{100*(late-early)/early:>10.3f}%")
        print("   (baseline legs are the clean host probe: same trusted harness every run,")
        print("    so any drift there is the host and not anybody's code.)")

    # ---- 3. baseline-leg drift across the whole modern era ---------------
    print("\n3. baseline decode leg, hour by hour (the host's own clock)")
    modern = [r for r in rows if ts(r) >= datetime(2026, 8, 10, tzinfo=timezone.utc)]
    buckets: dict[str, list[float]] = {}
    for r in modern:
        k = ts(r).strftime("%m-%dT%HZ")
        buckets.setdefault(k, []).append(
            1e6 * r["officialMetrics"]["baseline_decode_seconds_per_token"]
        )
    print(f"   {'hour':<10} {'n':>3} {'base dec us':>12} {'sd':>8}")
    for k in sorted(buckets):
        v = buckets[k]
        sd = statistics.stdev(v) if len(v) > 1 else 0.0
        print(f"   {k:<10} {len(v):>3} {statistics.mean(v):12.2f} {sd:8.2f}")

    # ---- 4. lag-1 autocorrelation of the baseline decode leg -------------
    print("\n4. lag-1 autocorrelation of consecutive baseline-decode receipts")
    for label, sub in (("since 08-10", modern), ("since 08-06", [r for r in rows if ts(r) >= datetime(2026, 8, 6, tzinfo=timezone.utc)])):
        y = [1e6 * r["officialMetrics"]["baseline_decode_seconds_per_token"] for r in sub]
        if len(y) < 4:
            continue
        m = statistics.mean(y)
        num = sum((y[i] - m) * (y[i + 1] - m) for i in range(len(y) - 1))
        den = sum((v - m) ** 2 for v in y)
        print(f"   {label:<12} n {len(y):>4}   r1 = {num/den:+.3f}   "
              f"(|r1| < {2/len(y)**0.5:.3f} is white noise at 95 %)")

    # ---- 5. verdict on the class comparison ------------------------------
    print("\n5. what this does to the base-vs-atlasv3 class comparison")
    cls: dict[str, list[float]] = {}
    for r in mine:
        _, klass = OURS[r["id"][:8]]
        cls.setdefault(klass, []).append(normalized(r["officialMetrics"]))
    for k in sorted(cls):
        v = cls[k]
        sd = statistics.stdev(v) if len(v) > 1 else float("nan")
        print(f"   {k:<16} n {len(v)}  mean normalized {statistics.mean(v):.6f}  sd {sd:.6f}")
    if "r109F-base" in cls and "r109F-atlasv3" in cls:
        a, b = cls["r109F-atlasv3"], cls["r109F-base"]
        ma, mb = statistics.mean(a), statistics.mean(b)
        # pooled instrument sd from the two zero-code-variance groups
        sa = statistics.stdev(a) / ma
        sb = statistics.stdev(b) / mb
        pooled = (((len(a) - 1) * sa ** 2 + (len(b) - 1) * sb ** 2) / (len(a) + len(b) - 2)) ** 0.5
        se = pooled * (1 / len(a) + 1 / len(b)) ** 0.5
        d = (ma - mb) / mb
        print(f"   atlasv3 - base = {100*d:+.4f} %   pooled instrument sd {100*pooled:.4f} %"
              f"   se {100*se:.4f} %   =>  {d/se:.2f} sigma")
        print("   CAVEAT: the two classes were submitted in time-separated blocks")
        print("   (base 23:03-23:33Z, atlasv3 01:07-01:54Z), so this difference is")
        print("   confounded with any host drift measured in sections 2-4 above.")


if __name__ == "__main__":
    main()
