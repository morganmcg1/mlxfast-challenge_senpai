#!/usr/bin/env python3
"""R107: which ranked receipt's tree do we actually HAVE, and which has best merit?

For recent submissions the service's `submissionCommitSha` is a commit that has
been pushed back into this repository, so the receipt can be re-materialised
exactly.  This script tests every receipt's `submissionCommitSha` against the
local object store and ranks the ones we hold by MERIT (cs), then prices the
draw ladder for each.

READ-ONLY: public submissions feed + `git cat-file -e` on the local store.
"""
import argparse
import json
import math
import os
import subprocess
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456
SIGMA = 0.005503


def fetch(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def dig(obj, *names):
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


def sdig(obj, *names):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, str) and v:
                    return v
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--draws", type=int, default=18)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    feed = fetch(FEED)
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed

    rows = []
    for s in subs:
        official = dig(s, "officialScore", "official_score")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        sha = sdig(s, "submissionCommitSha", "submission_commit_sha", "commitSha")
        if None in (official, cd, cp) or min(cd, cp) <= 0 or not sha:
            continue
        rows.append({
            "id": s.get("id"), "sha": sha,
            "when": (s.get("createdAt") or "")[:19],
            "O": official,
            "cs": (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25,
        })
    print(f"receipts with a commit sha: {len(rows)}")

    shas = sorted({r["sha"] for r in rows})
    have = set()
    proc = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                          input="\n".join(shas) + "\n",
                          capture_output=True, text=True)
    for line, sha in zip(proc.stdout.splitlines(), shas):
        if " commit" in line and "missing" not in line:
            have.add(sha)
    print(f"distinct shas: {len(shas)}   present locally: {len(have)}")

    local = [r for r in rows if r["sha"] in have]
    local.sort(key=lambda r: -r["cs"])
    print(f"\nTOP {args.top} LOCALLY-MATERIALISABLE TREES BY MERIT")
    print("  rank |      cs |       O |     f % | sha      | when")
    for i, r in enumerate(local[:args.top], 1):
        print(f"  {i:4d} | {r['cs']:.6f} | {r['O']:.6f} | {(r['O']/r['cs']-1)*100:+7.4f} | "
              f"{r['sha'][:8]} | {r['when']}")

    print(f"\nDRAW PRICING (sigma {SIGMA*100:.4f} %, {args.draws} draws)")
    print("  sha      |      cs | need %  |  z    | P/draw % | P(ladder) %")
    for r in local[:6]:
        need = math.log(RECORD / r["cs"])
        z = need / SIGMA
        p = norm_sf(z)
        print(f"  {r['sha'][:8]} | {r['cs']:.6f} | {need*100:6.4f} | {z:5.3f} | "
              f"{p*100:8.3f} | {(1-(1-p)**args.draws)*100:10.1f}")

    missing_better = [r for r in rows if r["sha"] not in have and r["cs"] > (local[0]["cs"] if local else 0)]
    missing_better.sort(key=lambda r: -r["cs"])
    print(f"\nranked trees with HIGHER merit that we do NOT hold locally: {len(missing_better)}")
    for r in missing_better[:10]:
        print(f"   cs {r['cs']:.6f}  O {r['O']:.6f}  sha {r['sha'][:12]}  {r['when']}")

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump({"local": local[:100], "missing_better": missing_better[:50]}, fh, indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
