#!/usr/bin/env python3
"""R107: is the ranked *session factor* f predictable from wall-clock time?

WHY
---
The official score decomposes as

    officialScore = cs * (1 + f)

where `cs` is the candidate score measured against the fixed master-baseline
constants and `f` is a per-session factor produced by the ranked runner's own
freshly measured baseline.  R106-E measured sd(f) = 0.53 % within a single
tree, and showed that **96 % of Var(f) comes from the baseline prefill leg**.
The record is 1.00 % of merit above our best tree, so f is the lottery we are
playing.

If f has *structure* -- a diurnal cycle, a drift, or autocorrelation between
consecutive receipts -- then a draw is not an i.i.d. sample and the draws can
be *timed*.  Timing is free: it costs no merit and no engineering.  This
script tests for that structure on the entire public feed.

It is READ-ONLY: it touches only the public submissions feed.

Usage:
    python3 research/maple-frieren-r107-session-timing.py \
            [--out-json research/maple-frieren-r107-session-timing.json]
"""
import argparse
import datetime as dt
import json
import math
import os
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542      # master-baseline decode  s/token
MB_P = 0.000372473193      # master-baseline prefill s/token


def fetch():
    req = urllib.request.Request(FEED, headers={
        "Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def dig(obj, *names):
    """Depth-first search for the first key whose name matches any of *names."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else float("nan")


def pearson(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    feed = fetch()
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed

    rows = []
    for s in subs:
        official = dig(s, "officialScore", "official_score")
        if official is None:
            continue
        bd = dig(s, "baselineDecodeSecondsPerToken", "baseline_decode_seconds_per_token")
        bp = dig(s, "baselinePrefillSecondsPerToken", "baseline_prefill_seconds_per_token")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        ts = None
        for key in ("completedAt", "createdAt", "updatedAt", "submittedAt"):
            v = s.get(key) if isinstance(s, dict) else None
            if isinstance(v, str):
                ts = v
                break
        if None in (bd, bp, cd, cp) or ts is None:
            continue
        try:
            when = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        cs = (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25
        f = official / cs - 1.0
        rows.append({
            "id": s.get("id"),
            "when": when.isoformat(),
            "epoch": when.timestamp(),
            "hour": when.hour + when.minute / 60.0,
            "official": official,
            "cs": cs,
            "f": f,
            "bd": bd,
            "bp": bp,
        })

    rows.sort(key=lambda r: r["epoch"])
    if len(rows) < 8:
        print(f"only {len(rows)} usable receipts; nothing to test")
        return

    fs = [r["f"] for r in rows]
    bps = [r["bp"] for r in rows]
    bds = [r["bd"] for r in rows]
    hours = [r["hour"] for r in rows]

    print(f"usable receipts: {len(rows)}")
    print(f"f            mean {mean(fs)*100:+.4f} %   sd {sd(fs)*100:.4f} %")
    print(f"baseline dec mean {mean(bds)*1e6:.1f} us  sd {sd(bds)/mean(bds)*100:.4f} %")
    print(f"baseline pre mean {mean(bps)*1e6:.1f} us  sd {sd(bps)/mean(bps)*100:.4f} %")

    # --- lag-1 autocorrelation in arrival order ------------------------------
    lag1_f = pearson(fs[:-1], fs[1:])
    lag1_bp = pearson(bps[:-1], bps[1:])
    n = len(fs) - 1
    print(f"\nlag-1 autocorrelation (arrival order, n={n})")
    print(f"  f            r = {lag1_f:+.4f}   (|r| > {1.96/math.sqrt(n):.4f} is 5 % significant)")
    print(f"  baseline pre r = {lag1_bp:+.4f}")

    # --- diurnal structure ---------------------------------------------------
    cos_h = [math.cos(2 * math.pi * h / 24.0) for h in hours]
    sin_h = [math.sin(2 * math.pi * h / 24.0) for h in hours]
    rc, rs = pearson(fs, cos_h), pearson(fs, sin_h)
    r2 = rc * rc + rs * rs
    print(f"\ndiurnal (24 h) harmonic on f")
    print(f"  r_cos = {rc:+.4f}  r_sin = {rs:+.4f}  R^2 = {r2:.4f}")
    amp = math.sqrt(r2) * sd(fs)
    print(f"  implied amplitude = {amp*100:+.4f} % of merit")

    # --- bucketed table ------------------------------------------------------
    print("\nf by UTC hour bucket")
    print("  bucket |  n |   mean f % |    sd %")
    buckets = {}
    for r in rows:
        b = int(r["hour"] // 4) * 4
        buckets.setdefault(b, []).append(r["f"])
    for b in sorted(buckets):
        v = buckets[b]
        s_ = sd(v) * 100 if len(v) > 1 else float("nan")
        print(f"  {b:02d}-{b+4:02d}  | {len(v):2d} | {mean(v)*100:+9.4f} | {s_:7.4f}")

    out = {
        "n": len(rows),
        "f_mean": mean(fs), "f_sd": sd(fs),
        "lag1_f": lag1_f, "lag1_baseline_prefill": lag1_bp,
        "diurnal_r_cos": rc, "diurnal_r_sin": rs, "diurnal_R2": r2,
        "diurnal_amplitude": amp,
        "rows": rows,
    }
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
