#!/usr/bin/env python3
"""R106-E: read the official M5 receipt(s) for the fixed-tree replication draws.

Prints the five numbers the charter asks for per draw --- cs, officialScore,
baseline_decode, baseline_prefill, and the derived session factor
f = officialScore / cs --- plus the candidate legs and gate verdicts.

Draws are located by id prefix, not by recency: the upload account is shared
across three concurrent launches, so the newest receipt is usually not ours.

Usage: maple-frieren-r106e-draws.py [ID_PREFIX ...] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
FEED = f"https://api.mlx.fast/api/benchmarks/{BENCH}/submissions"

# ln cs = X - 0.75 ln cand_dec - 0.25 ln cand_pre  (SI units), frozen in r103.
X = -5.1831677111

# R106-E draw 1 (fixed tree, commit 8db6ffaf). Draw 2 deduped onto this id.
DEFAULT_IDS = ("2771067f",)


def cs_of(D_s: float, P_s: float) -> float:
    return math.exp(X - 0.75 * math.log(D_s) - 0.25 * math.log(P_s))


def fetch() -> list[dict]:
    token = os.environ["MLXFAST_API_TOKEN"]
    req = urllib.request.Request(FEED, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        data = json.load(fh)
    return data["submissions"] if isinstance(data, dict) else data


def summarise(row: dict) -> dict:
    m = row.get("officialMetrics") or {}
    out = {
        "id": row["id"],
        "short": row["id"][:8],
        "status": row["status"],
        "submissionCommitSha": row.get("submissionCommitSha"),
        "createdAt": row.get("createdAt"),
        "officialScore": row.get("officialScore"),
        "promotionStatus": row.get("promotionStatus"),
        "rejectionReason": row.get("rejectionReason"),
        "note": (row.get("note") or "")[:200],
    }
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    if d and p:
        out.update(
            cand_dec_us_step=d * 1e6,
            cand_pre_us_tok=p * 1e6,
            cs=cs_of(d, p),
            bl_dec_us_step=(m.get("baseline_decode_seconds_per_token") or 0) * 1e6,
            bl_pre_us_tok=(m.get("baseline_prefill_seconds_per_token") or 0) * 1e6,
            decode_speedup=m.get("decode_speedup"),
            prefill_speedup=m.get("prefill_speedup"),
            passed_correctness=m.get("passed_correctness"),
            passed_decode_floor=m.get("passed_decode_speedup_floor"),
            passed_prefill_floor=m.get("passed_prefill_speedup_floor"),
            max_abs_diff=m.get("max_abs_diff"),
            error=m.get("error"),
        )
        if out["officialScore"]:
            out["f"] = out["officialScore"] / out["cs"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", default=None)
    ap.add_argument("--json")
    args = ap.parse_args()
    ids = tuple(args.ids) if args.ids else DEFAULT_IDS

    rows = fetch()
    res: dict[str, dict] = {}
    for pref in ids:
        hit = [r for r in rows if r["id"].startswith(pref)]
        if not hit:
            print(f"\n=== {pref} ===\n  not found in feed")
            continue
        r = summarise(hit[0])
        res[pref] = r
        print(f"\n=== {pref} ===")
        print(f"  receipt              {r['id']}")
        print(f"  status               {r['status']}   promotion={r['promotionStatus']}")
        print(f"  rejectionReason      {r['rejectionReason']}")
        print(f"  submissionCommitSha  {r['submissionCommitSha']}")
        print(f"  createdAt            {r['createdAt']}")
        print(f"  note[:200]           {r['note']!r}")
        if "cs" not in r:
            print("  (no officialMetrics)")
            continue
        print(f"  cand_dec  D          {r['cand_dec_us_step']:.4f} us/step")
        print(f"  cand_pre  P          {r['cand_pre_us_tok']:.4f} us/tok")
        print(f"  cs                   {r['cs']:.6f}")
        print(f"  officialScore        {r['officialScore']}")
        print(f"  f = score/cs         {r.get('f', float('nan')):.6f}")
        print(f"  baseline_decode      {r['bl_dec_us_step']:.4f} us/step")
        print(f"  baseline_prefill     {r['bl_pre_us_tok']:.4f} us/tok")
        print(f"  speedups dec/pre     {r['decode_speedup']} / {r['prefill_speedup']}")
        print(f"  floors dec/pre       {r['passed_decode_floor']} / {r['passed_prefill_floor']}")
        print(f"  correctness          {r['passed_correctness']}  max_abs_diff={r['max_abs_diff']}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
