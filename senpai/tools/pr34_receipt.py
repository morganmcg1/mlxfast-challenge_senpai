#!/usr/bin/env python3
"""Print one official receipt's axes and gate verdicts by id prefix.

Usage: pr34_receipt.py <subs.json> <id-prefix> [...]
       pr34_receipt.py <subs.json> --dt <id-prefix>:<n> [...]

`--dt` applies the pre-registered dT(n) estimator and emits an `n:dT` argument
line for pr34_fit_ladder.py. One pair must carry n=0.

Fetch subs.json first. The listing is leaderboard-wide and about 17 MB, so
write it to a file rather than piping it into a shell:

    curl -sS -o /tmp/subs.json -H "Authorization: Bearer ${MLXFAST_API_TOKEN}" \
      "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions"

Other routes on the same host: /api/submissions/{id} and /api/me.
"""

from __future__ import annotations

import json
import sys

KEYS = (
    "passed_correctness",
    "max_abs_diff",
    "passed_prefill_speedup_floor",
    "passed_decode_speedup_floor",
    "prefill_speedup",
    "decode_speedup",
    "gpqa_ttft_seconds",
    "gpqa_ttft_max_seconds",
    "gpqa_ttft_passed",
    "semantic_gpqa_passed",
    "benchmark_wall_seconds",
    "peak_ram_gb",
    "error",
)


def axes(m: dict) -> dict:
    """Candidate and paired-baseline prefill forward S and steady decode step T, in ms.

    The official baseline decode field is the full ms/token, not the steady step,
    so the seed-forward share S/128 must be removed from it as well.
    """
    S = 512_000.0 * m["prefill_seconds_per_token"]
    bS = 512_000.0 * m["baseline_prefill_seconds_per_token"]
    return {
        "S": S,
        "T": 1000.0 * m["decode_seconds_per_token"] - S / 128.0,
        "bS": bS,
        "bD": 1000.0 * m["baseline_decode_seconds_per_token"],
        "bT": 1000.0 * m["baseline_decode_seconds_per_token"] - bS / 128.0,
    }


def dt_ladder(subs: list, pairs: list) -> None:
    want = {p.split(":")[0]: int(p.split(":")[1]) for p in pairs}
    got = {}
    for s in subs:
        sid = s.get("id") or ""
        hit = [p for p in want if sid.startswith(p)]
        if not hit:
            continue
        m = s.get("officialMetrics") or {}
        if not m.get("prefill_seconds_per_token"):
            print(f"!! {sid[:8]} n={want[hit[0]]} has no timed metrics (status={s.get('status')})")
            continue
        got[want[hit[0]]] = dict(axes(m), id=sid[:8])
    if 0 not in got:
        sys.exit("--dt needs a receipt at n=0 to subtract")
    ref = got[0]
    print("   n   receipt        S      T     bS      bT   Ttilde=T-bT      dT   dT_candonly")
    for n in sorted(got):
        a = got[n]
        tt = a["T"] - a["bT"]
        print(
            f"{n:5d}   {a['id']}  {a['S']:8.4f} {a['T']:6.4f} {a['bS']:8.4f} {a['bT']:8.5f}"
            f"   {tt:10.5f}  {tt - (ref['T'] - ref['bT']):7.5f}  {a['T'] - ref['T']:9.5f}"
        )
    print("\nfit args (paired):   " + " ".join(
        f"{n}:{got[n]['T'] - got[n]['bT'] - (ref['T'] - ref['bT']):.5f}" for n in sorted(got)
    ))
    print("fit args (cand-only): " + " ".join(
        f"{n}:{got[n]['T'] - ref['T']:.5f}" for n in sorted(got)
    ))
    sc = [got[n]["S"] for n in sorted(got)]
    print(f"\nS control: min={min(sc):.4f} max={max(sc):.4f} range={100*(max(sc)-min(sc))/min(sc):.3f}%")


def main() -> None:
    path, prefixes = sys.argv[1], sys.argv[2:]
    subs = json.load(open(path))["submissions"]
    if prefixes and prefixes[0] == "--dt":
        return dt_ladder(subs, prefixes[1:])
    for s in subs:
        sid = s.get("id") or ""
        if not any(sid.startswith(p) for p in prefixes):
            continue
        m = s.get("officialMetrics") or {}
        print(f"=== {sid}")
        print(
            f"  status={s.get('status')} officialScore={s.get('officialScore')} "
            f"reason={s.get('rejectionReason')}"
        )
        print(f"  created={s.get('createdAt')} updated={s.get('updatedAt')}")
        if m.get("prefill_seconds_per_token"):
            a = axes(m)
            print(f"  S={a['S']:.4f} ms   T={a['T']:.5f} ms")
            print(
                f"  baseline S={a['bS']:.4f} ms   baseline ms/token={a['bD']:.5f}"
                f"   baseline T={a['bT']:.5f} ms"
            )
            for k in KEYS:
                if k in m:
                    print(f"  {k} = {m[k]}")
        else:
            print("  (no timed metrics yet)")


if __name__ == "__main__":
    main()
