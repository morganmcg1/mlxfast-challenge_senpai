#!/usr/bin/env python3
"""Census of the shared official submission channel.

Reads the benchmark feed, resolves every submission in a window to its full
record, and reports the paired candidate/baseline timings plus the derived
`cs` and limiter factor `L`. Answers two questions that cost zero slots:

  1. identity  -- which receipt is whose, by note heading rather than by
                  arrival order (arrival order has already misattributed one).
  2. noise     -- repeated legs of one ladder submit near-identical code, so
                  their spread estimates session-to-session reproducibility.

Usage: maple-frieren-r105b-channel-census.py [--since ISO8601] [--json OUT]
"""
import argparse
import json
import math
import os
import subprocess
import statistics

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
API = "https://api.mlx.fast/api"
X = -5.1831677111  # harness score constant: cs = exp(X - .75 ln(D/1e6) - .25 ln(P/1e6))


def get(url, token):
    r = subprocess.run(
        ["curl", "-s", "-H", "Authorization: Bearer " + token, url],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout)


def cs_of(dec, pre):
    if not dec or not pre:
        return None
    return math.exp(X - 0.75 * math.log(dec / 1e6) - 0.25 * math.log(pre / 1e6))


def heading(note):
    for line in (note or "").splitlines():
        s = line.strip().lstrip("#").strip()
        if s and not s.lower().startswith("model:"):
            return s[:46]
    return "(no heading)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-10T03:00")
    ap.add_argument("--json", dest="out")
    a = ap.parse_args()
    token = os.environ["MLXFAST_API_TOKEN"]

    feed = get(f"{API}/benchmarks/{BENCH}/submissions", token)
    if isinstance(feed, dict):
        feed = feed.get("submissions") or feed.get("data") or []
    rows = sorted(
        (r for r in feed if (r.get("createdAt") or "") >= a.since),
        key=lambda r: r["createdAt"],
    )

    recs = []
    for r in rows:
        d = get(f"{API}/submissions/{r['id']}", token)
        d = d.get("submission", d)
        m = d.get("officialMetrics") or {}
        us = lambda k: (m[k] * 1e6 if m.get(k) else None)  # feed reports seconds
        cd, cp = us("decode_seconds_per_token"), us("prefill_seconds_per_token")
        cs = cs_of(cd, cp)
        sc = d.get("officialScore")
        recs.append(dict(
            t=r["createdAt"], id=r["id"], status=d.get("status"),
            cand_dec=cd, cand_pre=cp,
            base_dec=us("baseline_decode_seconds_per_token"),
            base_pre=us("baseline_prefill_seconds_per_token"),
            cs=cs, score=sc, L=(sc / cs if sc and cs else None),
            dec_su=m.get("decode_speedup"), pre_su=m.get("prefill_speedup"),
            commit=m.get("commit"), correct=m.get("passed_correctness"),
            max_abs_diff=m.get("max_abs_diff"), golden=m.get("golden_hash"),
            reason=d.get("rejectionReason"), heading=heading(d.get("note")),
        ))

    fmt = lambda v, w, p=3: (f"{v:{w}.{p}f}" if isinstance(v, (int, float)) else " " * (w - 1) + "-")
    print(f"{'time':9}{'id':9}{'status':11}{'cand_dec':>10}{'cand_pre':>9}"
          f"{'base_dec':>10}{'cs':>10}{'L':>9}  heading")
    for r in recs:
        print(f"{r['t'][11:19]} {r['id'][:8]} {str(r['status'])[:10]:10}"
              f"{fmt(r['cand_dec'],10)}{fmt(r['cand_pre'],9)}{fmt(r['base_dec'],10)}"
              f"{fmt(r['cs'],10,6)}{fmt(r['L'],9,5)}  {r['heading']}")

    # Baseline re-measurement spread: the harness re-times the SAME pinned
    # baseline every session, so its scatter is pure session noise with no
    # code difference mixed in.
    bd = [r["base_dec"] for r in recs if r["base_dec"]]
    bp = [r["base_pre"] for r in recs if r["base_pre"]]
    print()
    for name, xs in (("baseline_decode_us_per_step", bd), ("baseline_prefill_us_per_token", bp)):
        if len(xs) >= 2:
            mu, sd = statistics.mean(xs), statistics.stdev(xs)
            print(f"{name}: n={len(xs)} mean={mu:.3f} sd={sd:.3f} "
                  f"cv={100*sd/mu:.3f}% min={min(xs):.3f} max={max(xs):.3f}")

    replicate_report(recs)

    if a.out:
        json.dump(recs, open(a.out, "w"), indent=1)
        print(f"\nwrote {a.out}")


# Receipts whose headings mark them as repeats of one arm. Ladder legs re-run
# identical code, so within-group scatter is receipt-level reproducibility with
# no code effect mixed in.
REPLICATE_GROUPS = {
    "r105-A arm A0": ("69fb349b", "c7930407", "d4a86ffd"),
    "r105-A arm A1": ("0b9ae917", "c52994dc"),
    "r104-A arm A": ("d5f2b4ce", "a8a80405", "8a09a941"),
}


def replicate_report(recs):
    by_id = {r["id"][:8]: r for r in recs}
    stats = {
        "decode D (us/step)": lambda r: r["cand_dec"],
        "prefill P (us/tok)": lambda r: r["cand_pre"],
        "T = D - 4P": lambda r: r["cand_dec"] - 4 * r["cand_pre"],
        "cs (unpaired)": lambda r: r["cs"],
        "decode_speedup": lambda r: r["dec_su"],
        "officialScore (ranked)": lambda r: r["score"],
    }
    print("\n=== within-arm replicate scatter (same code, different session) ===")
    print(f"{"quantity":24}{'pooled sd':>11}{'dof':>5}{'mean':>12}{'cv %':>8}"
          f"{'sd of a pair':>14}")
    for label, get_v in stats.items():
        ss, dof, vals = 0.0, 0, []
        for ids in REPLICATE_GROUPS.values():
            g = [get_v(by_id[i]) for i in ids if i in by_id and get_v(by_id[i])]
            if len(g) < 2:
                continue
            mu = statistics.mean(g)
            ss += sum((x - mu) ** 2 for x in g)
            dof += len(g) - 1
            vals += g
        if not dof:
            continue
        sd = math.sqrt(ss / dof)
        mu = statistics.mean(vals)
        print(f"{label:24}{sd:11.3f}{dof:5d}{mu:12.3f}{100*sd/mu:8.3f}"
              f"{sd*math.sqrt(2):14.3f}")


def power_note(sd_pair, effect):
    """Pairs needed to detect `effect` at 80% power, two-sided 5%."""
    return (2.8 * sd_pair / abs(effect)) ** 2


if __name__ == "__main__":
    main()
