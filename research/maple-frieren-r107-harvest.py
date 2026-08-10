#!/usr/bin/env python3
"""Harvest the R106-E / Rule 95.7 draw-ladder receipts and decompose each one.

Every official receipt carries the two candidate legs, so for each of our own
submissions we can split the reported score into the part that belongs to the
tree and the part that belongs to the session:

    ln O = ln cs + f,   cs = (MB_D/cd)^0.75 (MB_P/cp)^0.25,   f = ln O - ln cs

`cs` is the merit of the surface we submitted (tree-only, session-free) and `f`
is the session draw (baseline-only, tree-free).  Rule 95.7 fixes the tree, so
across the ladder `cs` should be constant to ~0.05 % and every bit of spread in
O is `f`.  That is the whole point of the ladder, and this script is how we
watch it happen.

Usage:
    python3 research/maple-frieren-r107-harvest.py [--last 15] [--json PATH]
                                                   [--who morganmcg1]
Exit codes:
    0  harvested normally
    3  no API token
    4  a harvested receipt BEAT the record  (caller should stop and report)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456
BEST_CS = 2.590559          # merit of the 4b0e051b surface (Rule 95.1)


def token() -> str | None:
    t = os.environ.get("MLXFAST_API_TOKEN")
    if t:
        return t
    p = pathlib.Path.home() / ".config" / "mlxfast" / "config.json"
    if p.exists():
        return json.loads(p.read_text()).get("token")
    return None


def fetch(url: str, tok: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/json"})
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


def marker_of(note: str | None) -> str:
    if not note:
        return ""
    for tok in note.replace("`", " ").replace("#", " ").split():
        if tok.startswith("senpai-r106e-replay-") or tok.startswith("senpai-r93-"):
            return tok.strip(".,;:")
    return (note.splitlines() or [""])[0][:48]


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=15)
    ap.add_argument("--who", default="morganmcg1")
    ap.add_argument("--json", default="research/maple-frieren-r107-ladder-receipts.json")
    a = ap.parse_args()

    tok = token()
    if not tok:
        print("no MLXFAST_API_TOKEN available", file=sys.stderr)
        return 3

    feed = fetch(FEED, tok)
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed

    rows = []
    for s in subs:
        if s.get("solverUsername") != a.who:
            continue
        note = s.get("note") or ""
        ts = sdig(s, "createdAt", "created_at", "submittedAt") or ""
        status = str(s.get("status") or "").lower()
        O = dig(s, "officialScore", "official_score")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        row = {
            "ts": ts, "status": status,
            "sha": (sdig(s, "submissionCommitSha", "submission_commit_sha",
                         "commitSha") or "")[:12],
            "marker": marker_of(note),
            "O": O, "decode": cd, "prefill": cp,
        }
        if None not in (O, cd, cp) and min(cd or 0, cp or 0) > 0 and (O or 0) > 0:
            cs = (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25
            row["cs"] = cs
            row["f_pct"] = 100.0 * math.log(O / cs)
            row["cs_vs_best_pct"] = 100.0 * math.log(cs / BEST_CS)
            row["gap_to_record_pct"] = 100.0 * math.log(RECORD / O)
        rows.append(row)

    rows.sort(key=lambda r: r["ts"])
    tail = rows[-a.last:]

    print(f"receipts for {a.who}: {len(rows)}   (showing last {len(tail)})")
    print(f"{'when':<22} {'status':<11} {'sha':<13} {'marker':<26} "
          f"{'O':>10} {'cs':>10} {'f %':>8} {'dcs %':>7} {'need %':>7}")
    for r in tail:
        print(f"{r['ts'][:22]:<22} {r['status']:<11} {r['sha']:<13} "
              f"{r['marker'][:26]:<26} "
              f"{(r.get('O') or float('nan')):>10.6f} "
              f"{(r.get('cs') or float('nan')):>10.6f} "
              f"{(r.get('f_pct') or float('nan')):>8.4f} "
              f"{(r.get('cs_vs_best_pct') or float('nan')):>7.4f} "
              f"{(r.get('gap_to_record_pct') or float('nan')):>7.4f}")

    ladder = [r for r in rows if r["marker"].startswith("senpai-r106e-replay-")
              and "cs" in r]
    beat = [r for r in ladder if (r.get("O") or 0) > RECORD]
    if ladder:
        fs = [r["f_pct"] for r in ladder]
        css = [r["cs"] for r in ladder]
        print(f"\nladder legs with receipts: {len(ladder)}")
        print(f"  cs  mean {mean(css):.6f}  sd {sd(css):.6f}   "
              f"(tree is fixed, so this must be ~flat)")
        print(f"  f   mean {mean(fs):+.4f} %  sd {sd(fs):.4f} %  "
              f"min {min(fs):+.4f} %  max {max(fs):+.4f} %")
        print(f"  best O so far {max(r['O'] for r in ladder):.6f} "
              f"vs record {RECORD:.6f}")

    out = pathlib.Path(a.json)
    out.write_text(json.dumps({
        "record": RECORD, "best_cs": BEST_CS, "who": a.who,
        "n_receipts": len(rows), "rows": rows,
    }, indent=2) + "\n")
    print(f"\nwrote {out}")

    if beat:
        print("\n" + "!" * 68)
        print("RECORD BEATEN -- stop the ladder and adjudicate:")
        for r in beat:
            print(f"  {r['ts']}  {r['marker']}  O={r['O']:.9f} > {RECORD:.9f}")
        print("!" * 68)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
