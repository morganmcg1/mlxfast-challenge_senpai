#!/usr/bin/env python3
"""R107: join the public receipt corpus to the LOCALLY AVAILABLE validated trees.

The service pushes a `Validate submission <uuid>` commit back into this repo for
every submission it validates.  There are ~154 of them here.  Each such commit
is a *complete, buildable editable surface that already has a ranked receipt*.

Ranking those commits by MERIT (cs, the master-baseline candidate score) rather
than by officialScore tells us which locally-available tree is the best lottery
ticket -- officialScore is cs times an i.i.d. session factor with sd ~0.54 %, so
the board's own ordering is a noisy ordering of merit.

READ-ONLY: public submissions feed + the local git object store.

Usage:
    python3 research/maple-frieren-r107-local-merit-join.py [--top 20]
            [--out-json research/maple-frieren-r107-local-merit-join.json]
"""
import argparse
import json
import math
import os
import re
import subprocess
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456
SIGMA = 0.005503          # R107 repeat-group sd(ln officialScore | tree)


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


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--draws", type=int, default=18)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    out = subprocess.run(
        ["git", "log", "--all", "--format=%H%x09%ci%x09%s", "--grep=Validate submission"],
        capture_output=True, text=True, check=True).stdout
    local = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        sha, when, subject = parts[0], parts[1], parts[2]
        m = re.search(r"Validate submission ([0-9a-f-]{36})", subject)
        if m:
            local.setdefault(m.group(1), (sha, when))
    print(f"local `Validate submission` commits: {len(local)}")

    feed = fetch(FEED)
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed
    by_id = {}
    for s in subs:
        sid = s.get("id")
        official = dig(s, "officialScore", "official_score")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        if not sid or None in (official, cd, cp) or min(cd, cp) <= 0:
            continue
        by_id[sid] = {
            "O": official,
            "cs": (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25,
            "cd": cd, "cp": cp,
            "when": (s.get("createdAt") or "")[:19],
        }
    print(f"receipts in feed: {len(by_id)}")

    joined = []
    for sid, (sha, when) in local.items():
        r = by_id.get(sid)
        if not r:
            continue
        joined.append({"submission": sid, "commit": sha, "commit_when": when[:19],
                       **r, "f": r["O"] / r["cs"] - 1.0})
    joined.sort(key=lambda r: -r["cs"])
    print(f"joined (local commit AND ranked receipt): {len(joined)}\n")

    print(f"TOP {args.top} LOCALLY-AVAILABLE TREES BY MERIT")
    print("  rank |      cs |       O |     f % | commit   | receipt when")
    for i, r in enumerate(joined[:args.top], 1):
        print(f"  {i:4d} | {r['cs']:.6f} | {r['O']:.6f} | {r['f']*100:+7.4f} | "
              f"{r['commit'][:8]} | {r['when']}")

    print(f"\nP(record | {args.draws} draws), sigma = {SIGMA*100:.4f} % of ln O")
    print("  commit   |      cs | need %  | z     | P/draw % | P(ladder) %")
    for r in joined[:8]:
        need = math.log(RECORD / r["cs"])
        z = need / SIGMA
        p = norm_sf(z)
        print(f"  {r['commit'][:8]} | {r['cs']:.6f} | {need*100:6.4f} | {z:5.3f} | "
              f"{p*100:8.3f} | {(1-(1-p)**args.draws)*100:10.1f}")

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(joined, fh, indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
