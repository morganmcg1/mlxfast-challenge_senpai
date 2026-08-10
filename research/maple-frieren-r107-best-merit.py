#!/usr/bin/env python3
"""R107: rank every receipt by MERIT (cs), not by officialScore.

officialScore = cs * (1 + f) and f is i.i.d. session noise with sd ~0.54 %
(R107 timing + common-mode results).  So the board's ranking by officialScore
is a noisy ranking of merit, and the tree we should be drawing is the one with
the highest *cs*, not the one that happened to post the highest officialScore.

This lists the top receipts by cs so the ladder tree can be double-checked
against the whole public corpus rather than against our own archive alone.

READ-ONLY on the public submissions feed.
"""
import argparse
import json
import math
import os
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    feed = fetch(FEED)
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed

    rows = []
    for s in subs:
        official = dig(s, "officialScore", "official_score")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        if None in (official, cd, cp) or min(cd, cp) <= 0:
            continue
        cs = (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25
        rows.append({
            "id": s.get("id"),
            "sha": (s.get("submissionCommitSha") or s.get("commitSha") or "")[:12],
            "who": sdig(s, "userLogin", "user_login", "owner", "login") or "",
            "model": sdig(s, "model", "modelName") or "",
            "when": (s.get("createdAt") or s.get("completedAt") or "")[:19],
            "O": official, "cs": cs, "f": official / cs - 1.0,
        })

    rows.sort(key=lambda r: -r["cs"])
    print(f"receipts: {len(rows)}   record officialScore {RECORD:.6f}")
    print(f"\nTOP {args.top} BY MERIT (cs)")
    print("  rank |      cs |       O |     f % | when                | model / who | sha")
    for i, r in enumerate(rows[:args.top], 1):
        print(f"  {i:4d} | {r['cs']:.6f} | {r['O']:.6f} | {r['f']*100:+7.4f} | "
              f"{r['when']:19s} | {r['model'][:18]:18s} | {r['sha']}")

    best_o = max(rows, key=lambda r: r["O"])
    print(f"\nrecord holder by officialScore: cs={best_o['cs']:.6f} "
          f"O={best_o['O']:.6f} f={best_o['f']*100:+.4f} % model={best_o['model'][:24]}")
    print(f"best merit on the board:        cs={rows[0]['cs']:.6f} "
          f"O={rows[0]['O']:.6f} f={rows[0]['f']*100:+.4f} % model={rows[0]['model'][:24]}")
    print(f"merit gap record-holder minus best-merit = "
          f"{(best_o['cs']/rows[0]['cs']-1)*100:+.4f} %")

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(rows[:200], fh, indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
