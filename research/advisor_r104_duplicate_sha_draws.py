#!/usr/bin/env python3
"""Advisor r104: is a repeat submission of one identical commit SHA an
INDEPENDENT draw, or a cached replay?

Why this decides a strategy
---------------------------
advisor-r104-the-receipt-is-the-instrument.md SS8 established that the standing
record is held by an L draw near p99.95 and that (round-103 flagship SS3) L is an
exchangeable lottery nobody can steer.  SS2 established that the platform imposes
no receipt quota and tolerates a 13.1-minute inter-arrival gap.

Those two facts only combine into a strategy if the platform RE-BENCHMARKS an
identical submissionCommitSha.  Two worlds:

  CACHED : receipts sharing a sha carry bit-identical (cand_dec, cand_pre).
           Resubmission buys nothing.  The only path to the record is real cs.
  FRESH  : receipts sharing a sha differ, and differ by roughly the known
           identical-code noise floor.  A fixed tree can then buy unlimited
           independent lottery tickets at near-zero marginal cost.

This script decides between them from the receipt corpus, and -- in the FRESH
world -- measures the within-sha dispersion, which is the cleanest possible
estimate of the platform's own repeat-measurement noise because the tree is
literally the same object.

READ-ONLY.  Never submits.  Never prints the token.
Field names per rule 58 (advisor_r103_freeze_corpus.py).

usage: python3 research/advisor_r104_duplicate_sha_draws.py
"""

import json
import math
import os
import pathlib
import statistics
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

BENCHMARK = "eigenlabs/mlxfast-challenge"
MB_D = 0.013855009542
MB_P = 0.000372473193

# identical-code reference floors, advisor-r104 SS1 (trimmed, dof 14)
FLOOR_LN_CS = 0.001860       # 0.1860 %
FLOOR_SD_T_US = 12.079       # us/step
FLOOR_SD_P_US = 0.5802       # us/tok

token = os.environ.get("MLXFAST_API_TOKEN")
base = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
cfg_path = pathlib.Path.home() / ".config/mlxfast/config.json"
if not token and cfg_path.exists():
    cfg = json.loads(cfg_path.read_text())
    base = cfg.get("apiBaseUrl", base).rstrip("/")
    token = cfg["token"]
if not token:
    sys.exit("no MLXFAST_API_TOKEN and no ~/.config/mlxfast/config.json")

SECRET = token


def get(path):
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {SECRET}"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def cs_of(dec, pre):
    return (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25


def pooled(pairs):
    num = sum(d * s * s for d, s in pairs)
    den = sum(d for d, s in pairs)
    return (math.sqrt(num / den) if den else float("nan")), den


def main():
    bid = get(f"/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}")[
        "benchmark"
    ]["id"]
    rows = get(f"/api/benchmarks/{bid}/submissions")["submissions"]
    print(f"pulled {len(rows)} raw submission records")

    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        if not isinstance(m, dict):
            continue
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        sha = r.get("submissionCommitSha")
        if not (d and p and bd and bp and sha):
            continue
        cs = cs_of(d, p)
        score = (bd / d) ** 0.75 * (bp / p) ** 0.25
        recs.append(
            dict(
                sha=sha,
                who=r.get("solverUsername") or "?",
                ts=str(m.get("timestamp") or r.get("createdAt") or ""),
                status=(r.get("status") or "").lower(),
                dec=float(d),
                pre=float(p),
                cs=cs,
                score=score,
                L=score / cs,
            )
        )
    recs.sort(key=lambda x: x["ts"])
    print(f"{len(recs)} metric-bearing receipts that carry a submissionCommitSha")

    # How many metric-bearing receipts carry NO sha at all?  This matters
    # because a naive "distinct sha count vs receipt count" comparison collapses
    # every sha-less receipt into one bucket and manufactures phantom duplicates.
    nosha = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        if not isinstance(m, dict):
            continue
        if not (m.get("decode_seconds_per_token")
                and m.get("prefill_seconds_per_token")
                and m.get("baseline_decode_seconds_per_token")
                and m.get("baseline_prefill_seconds_per_token")):
            continue
        if not r.get("submissionCommitSha"):
            nosha.append(dict(
                who=r.get("solverUsername") or "?",
                ts=str(m.get("timestamp") or r.get("createdAt") or ""),
                status=(r.get("status") or "").lower(),
            ))
    nosha.sort(key=lambda x: x["ts"])
    print(f"metric-bearing receipts with NO submissionCommitSha : {len(nosha)}")
    if nosha:
        print(f"  first {nosha[0]['ts']}   last {nosha[-1]['ts']}")
        who = defaultdict(int)
        for x in nosha:
            who[x["who"]] += 1
        top = sorted(who.items(), key=lambda kv: -kv[1])[:8]
        print("  by solver: " + ", ".join(f"{k}={v}" for k, v in top))
        print(f"  accepted among them: {sum(1 for x in nosha if x['status']=='accepted')}")
    print()

    by_sha = defaultdict(list)
    for r in recs:
        by_sha[r["sha"]].append(r)
    dups = {s: v for s, v in by_sha.items() if len(v) > 1}

    print(f"distinct shas                 : {len(by_sha)}")
    print(f"shas submitted more than once : {len(dups)}")
    print(f"receipts inside those groups  : {sum(len(v) for v in dups.values())}")
    print()

    identical, differing = [], []
    for sha, v in dups.items():
        same = len({x["dec"] for x in v}) == 1 and len({x["pre"] for x in v}) == 1
        (identical if same else differing).append((sha, v))

    print("===== THE DECISIVE TEST =====")
    print(f"  repeat groups bit-identical in (cand_dec, cand_pre) : {len(identical)}")
    print(f"  repeat groups that DIFFER                            : {len(differing)}")
    if not dups:
        verdict = "NO-REPEAT"
    elif identical and not differing:
        verdict = "CACHED"
    elif differing and not identical:
        verdict = "FRESH"
    else:
        verdict = "MIXED"
    print(f"  verdict: {verdict}")
    if verdict == "NO-REPEAT":
        print("  Not one commit in the entire corpus has ever produced two receipts.")
        print("  The question 'cached or fresh' therefore does not arise: the draw")
        print("  cannot be replayed at all.  Every receipt costs a distinct commit.")
        print("  Corollary: a replicated design must submit two commits whose")
        print("  Sources/ trees are byte-identical -- which is exactly how the")
        print("  identical-code noise floor in SS1 was measured, so it does work.")
    print()

    if differing:
        dec_sds, pre_sds, cs_sds, l_sds = [], [], [], []
        for sha, v in differing:
            n = len(v)
            dec_sds.append((n - 1, statistics.stdev([math.log(x["dec"]) for x in v])))
            pre_sds.append((n - 1, statistics.stdev([math.log(x["pre"]) for x in v])))
            cs_sds.append((n - 1, statistics.stdev([math.log(x["cs"]) for x in v])))
            l_sds.append((n - 1, statistics.stdev([math.log(x["L"]) for x in v])))
        sd_dec, dof = pooled(dec_sds)
        sd_pre, _ = pooled(pre_sds)
        sd_cs, _ = pooled(cs_sds)
        sd_l, _ = pooled(l_sds)
        # absolute-unit versions at the corpus mean
        mean_dec_us = statistics.mean([x["dec"] for _, v in differing for x in v]) * 1e6
        mean_pre_us = statistics.mean([x["pre"] for _, v in differing for x in v]) * 1e6
        print("===== within-sha dispersion (same TREE, repeat measurement) =====")
        print(f"  dof {dof}")
        print(f"  sd(ln cand_dec) = {sd_dec*100:.4f} %  -> {sd_dec*mean_dec_us:8.3f} us/step")
        print(f"  sd(ln cand_pre) = {sd_pre*100:.4f} %  -> {sd_pre*mean_pre_us:8.4f} us/tok")
        print(f"  sd(ln cs)       = {sd_cs*100:.4f} %")
        print(f"  sd(ln L)        = {sd_l*100:.4f} %")
        print()
        print("  reference floors, advisor-r104 SS1 (identical CODE, dof 14):")
        print(f"    sd(ln cs) = {FLOOR_LN_CS*100:.4f} %   sd(T) = {FLOOR_SD_T_US:.3f} us/step"
              f"   sd(P) = {FLOOR_SD_P_US:.4f} us/tok")
        print()
        print("  interpretation: identical SHA is a strictly tighter condition than")
        print("  identical Sources/.  If these agree, SS1's floor is confirmed to be")
        print("  pure platform noise with no build-to-build component.")
        print()

    print("===== repeat groups, largest first =====")
    order = sorted(dups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for sha, v in order[:25]:
        v = sorted(v, key=lambda x: x["ts"])
        same = len({x["dec"] for x in v}) == 1 and len({x["pre"] for x in v}) == 1
        tag = "IDENTICAL" if same else "differs"
        who = ",".join(sorted({x["who"] for x in v}))
        print(f"  {sha[:12]}  n={len(v)}  {tag:9s}  {who}")
        for x in v:
            print(f"      {x['ts']:24s} dec {x['dec']*1e6:9.3f} us/step  "
                  f"pre {x['pre']*1e6:9.4f} us/tok  cs {x['cs']:.6f}  "
                  f"L {x['L']:.6f}  {x['status']}")

    # ---- what it is worth ---------------------------------------------------
    if differing:
        gaps = []
        for sha, v in differing:
            v = sorted(v, key=lambda x: x["ts"])
            for a, b in zip(v, v[1:]):
                if a["ts"] and b["ts"]:
                    gaps.append((a["ts"], b["ts"]))
        print()
        print(f"===== resubmission cadence: {len(gaps)} consecutive repeat pairs =====")
        for a, b in gaps[:10]:
            print(f"  {a}  ->  {b}")

    out = dict(
        raw_records=len(rows),
        metric_bearing_with_sha=len(recs),
        distinct_sha=len(by_sha),
        repeat_shas=len(dups),
        receipts_in_repeat_shas=sum(len(v) for v in dups.values()),
        identical_groups=len(identical),
        differing_groups=len(differing),
        verdict=verdict,
        groups=[
            dict(
                sha=sha[:12],
                n=len(v),
                identical=(len({x["dec"] for x in v}) == 1
                           and len({x["pre"] for x in v}) == 1),
                solvers=sorted({x["who"] for x in v}),
                receipts=[
                    dict(ts=x["ts"], dec_us=round(x["dec"] * 1e6, 4),
                         pre_us=round(x["pre"] * 1e6, 5),
                         cs=round(x["cs"], 6), L=round(x["L"], 6),
                         status=x["status"])
                    for x in sorted(v, key=lambda y: y["ts"])
                ],
            )
            for sha, v in order
        ],
    )
    root = os.environ.get("MLXFAST_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    dest = os.path.join(root, "research", "artifacts",
                        "advisor-r104-duplicate-sha-draws.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    print()
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
