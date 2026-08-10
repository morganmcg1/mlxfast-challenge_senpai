#!/usr/bin/env python3
"""R105-B Phase B: read the official M5 receipts for the P0/P1 prefetch arms.

Reports, per draw, exactly the fields rev2 asked for: raw cand_dec, cand_pre,
cs, L, status and submissionCommitSha, plus the rule-58 decomposition

    D = 4P + T          D = cand_dec us/step, P = cand_pre us/tok

which is exact by construction of the harness arithmetic, and the session
factor L = officialScore / cs, which separates "the candidate got faster" from
"the paired baseline was slower in that session".

Arms are identified by the unique marker embedded in each note body, never by
id ordering: the account is shared and the newest id is usually someone else's.

Usage: maple-frieren-r105b-phaseb-receipts.py [--json OUT]
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

MARKERS = {
    "P0": "R105-B Phase B, arm P0",
    "P1": "R105-B Phase B, arm P1",
}


def cs_of(D_us: float, P_us: float) -> float:
    return math.exp(X - 0.75 * math.log(D_us / 1e6) - 0.25 * math.log(P_us / 1e6))


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
        "short": row["id"][:7],
        "status": row["status"],
        "submissionCommitSha": row.get("submissionCommitSha"),
        "createdAt": row.get("createdAt"),
        "officialScore": row.get("officialScore"),
        "promotionStatus": row.get("promotionStatus"),
        "rejectionReason": row.get("rejectionReason"),
    }
    d = m.get("decode_seconds_per_token")
    p = m.get("prefill_seconds_per_token")
    if d and p:
        D, P = d * 1e6, p * 1e6
        out.update(
            cand_dec_us_step=D,
            cand_pre_us_tok=P,
            T_us_step=D - 4 * P,
            cs=cs_of(D, P),
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
        if out["officialScore"] and out["cs"]:
            out["L"] = out["officialScore"] / out["cs"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args()

    rows = fetch()
    found: dict[str, dict] = {}
    for row in rows:
        note = row.get("note") or ""
        for arm, marker in MARKERS.items():
            if marker in note:
                # Keep the newest receipt carrying each marker.
                prev = found.get(arm)
                if prev is None or row["createdAt"] > prev["createdAt"]:
                    found[arm] = row

    res = {arm: summarise(row) for arm, row in found.items()}

    for arm in ("P0", "P1"):
        r = res.get(arm)
        print(f"\n=== {arm} ===")
        if r is None:
            print("  not drawn / marker not found in feed")
            continue
        print(f"  receipt              {r['short']}  ({r['id']})")
        print(f"  status               {r['status']}")
        print(f"  submissionCommitSha  {r['submissionCommitSha']}")
        print(f"  createdAt            {r['createdAt']}")
        if "cand_dec_us_step" not in r:
            print("  (no officialMetrics yet)")
            continue
        print(f"  cand_dec  D          {r['cand_dec_us_step']:.3f} us/step")
        print(f"  cand_pre  P          {r['cand_pre_us_tok']:.3f} us/tok")
        print(f"  T = D - 4P           {r['T_us_step']:.3f} us/step")
        print(f"  cs                   {r['cs']:.6f}")
        print(f"  officialScore        {r['officialScore']}")
        print(f"  L = score/cs         {r.get('L', float('nan')):.6f}")
        print(f"  baseline D / P       {r['bl_dec_us_step']:.3f} / {r['bl_pre_us_tok']:.3f}")
        print(f"  speedups dec/pre     {r['decode_speedup']:.6f} / {r['prefill_speedup']:.6f}")
        print(f"  floors dec/pre       {r['passed_decode_floor']} / {r['passed_prefill_floor']}")
        print(f"  correctness          {r['passed_correctness']}  max_abs_diff={r['max_abs_diff']}")

    a, b = res.get("P0"), res.get("P1")
    if a and b and "cand_dec_us_step" in a and "cand_dec_us_step" in b:
        print("\n=== paired contrast  P0 - P1  (negative = prefetch-OFF faster) ===")
        for key, unit in (
            ("cand_dec_us_step", "us/step"),
            ("cand_pre_us_tok", "us/tok"),
            ("T_us_step", "us/step"),
        ):
            print(f"  d{key:<20} {a[key] - b[key]:+9.3f} {unit}")
        print(f"  dcs                  {a['cs'] - b['cs']:+.6f}"
              f"  ({100 * (a['cs'] / b['cs'] - 1):+.4f} %)")
        print(f"  dscore               {a['officialScore'] - b['officialScore']:+.6f}")
        print(f"  dL                   {a['L'] - b['L']:+.6f}"
              f"  ({100 * (a['L'] / b['L'] - 1):+.4f} %)")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
