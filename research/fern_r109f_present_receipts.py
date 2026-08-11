#!/usr/bin/env python3
"""fern r109-f item (d): which official receipts are *replayable in this fork*?

An official receipt is only usable as a fallback if its `submissionCommitSha`
is an object this checkout can actually resolve. Many high-scoring receipts on
the public listing were produced by other solvers from trees that were never
pushed to (or were pruned from) `morganmcg1/mlxfast-challenge_senpai`, so their
commits are simply absent and their scores are unreachable here.

Ranks every receipt by `officialScore` descending, resolves presence with
`git cat-file -e <sha>^{commit}`, and reports the highest-scoring present one.

Usage: research/fern_r109f_present_receipts.py <submissions.json> [top_n]
"""
import json
import subprocess
import sys


def present(sha: str, cache: dict) -> bool:
    if sha in cache:
        return cache[sha]
    ok = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
    ).returncode == 0
    cache[sha] = ok
    return ok


def main() -> int:
    path = sys.argv[1]
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    rows = json.load(open(path))["submissions"]

    scored = [
        r for r in rows
        if isinstance(r.get("officialScore"), (int, float))
        and r["officialScore"] > 0
        and r.get("submissionCommitSha")
    ]
    scored.sort(key=lambda r: -r["officialScore"])
    print(f"rows={len(rows)} scored_with_sha={len(scored)}")

    cache: dict = {}
    first_present = None
    print(f"\n=== top {top_n} by officialScore, with fork presence ===")
    print(f"{'rank':>4} {'score':>17} {'sha':>12} {'present':>7} "
          f"{'status':>10} {'promotion':>10}  solver")
    for i, r in enumerate(scored[:top_n], 1):
        sha = r["submissionCommitSha"]
        p = present(sha, cache)
        if p and first_present is None:
            first_present = (i, r)
        print(f"{i:>4} {r['officialScore']:>17.11f} {sha[:12]:>12} "
              f"{'YES' if p else 'no':>7} {str(r.get('status'))[:10]:>10} "
              f"{str(r.get('promotionStatus'))[:10]:>10}  {r.get('solverUsername')}")

    # Exhaustive scan: the answer must not depend on top_n.
    print("\n=== exhaustive scan for the highest-scoring PRESENT receipt ===")
    best = None
    n_present = 0
    for r in scored:
        if present(r["submissionCommitSha"], cache):
            n_present += 1
            if best is None:
                best = r
    print(f"present_receipts={n_present} of {len(scored)} scored")
    if best:
        m = best.get("officialMetrics") or {}
        print(f"ANSWER: id={best['id'][:8]} score={best['officialScore']:.11f} "
              f"sha={best['submissionCommitSha']}")
        print(f"  solver={best.get('solverUsername')} status={best.get('status')} "
              f"promotion={best.get('promotionStatus')} created={best.get('createdAt')}")
        print(f"  decode={m.get('decode_seconds_per_token')} "
              f"prefill={m.get('prefill_seconds_per_token')}")
        print(f"  baseline_decode={m.get('baseline_decode_seconds_per_token')} "
              f"baseline_prefill={m.get('baseline_prefill_seconds_per_token')}")
        rank = scored.index(best) + 1
        print(f"  overall rank among scored receipts: {rank}")

    # Next few present ones, so a fallback has alternates.
    print("\n=== next present receipts (fallback alternates) ===")
    shown = 0
    for r in scored:
        if present(r["submissionCommitSha"], cache):
            shown += 1
            if shown == 1:
                continue
            print(f"  score={r['officialScore']:.11f} "
                  f"sha={r['submissionCommitSha'][:12]} "
                  f"solver={r.get('solverUsername')} "
                  f"promotion={r.get('promotionStatus')}")
            if shown >= 8:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
