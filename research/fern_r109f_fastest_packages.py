#!/usr/bin/env python3
"""Rank official receipts by NORMALIZED score to find the fastest executables.

The published leaderboard score is normalized x draw, where the draw is set by
the runner's own baseline legs and is pure luck (its cv is 0.54 %, 87 % of it
from the baseline prefill leg). Ranking by published therefore ranks luck.
Ranking by

    normalized = (REF_D / decode)^0.75 * (REF_P / prefill)^0.25

with the pinned constants ranks the executable. This script does that, dedupes
by submissionCommitSha keeping each package's best receipt, and prints fetch
targets so their source can be read with:

    git fetch origin <40-char-sha> && git tag -f pkg-<short> <sha>
    python3 research/fern_r109f_semantic_diff.py pkg-<short> HEAD

Usage: python3 research/fern_r109f_fastest_packages.py [receipts.json] [--top N]
"""
import json
import sys

REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626

path = "/tmp/subs_p4.json"
top = 20
args = sys.argv[1:]
i = 0
while i < len(args):
    if args[i] == "--top":
        top = int(args[i + 1])
        i += 2
    else:
        path = args[i]
        i += 1


def normalized(d, p):
    return (REF_D / d) ** 0.75 * (REF_P / p) ** 0.25


def main():
    with open(path) as fh:
        doc = json.load(fh)
    rows = doc["submissions"] if isinstance(doc, dict) else doc

    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        if not (d and p):
            continue
        if not m.get("passed_correctness", True):
            continue
        recs.append(
            {
                "id": r["id"],
                "solver": r.get("solverUsername"),
                "commit": r.get("submissionCommitSha") or m.get("commit") or "",
                "d": d * 1e6,
                "p": p * 1e6,
                "norm": normalized(d, p),
                "pub": r.get("officialScore"),
                "created": r.get("createdAt"),
            }
        )
    print("full-leg correct receipts: %d" % len(recs))

    best = {}
    for r in recs:
        key = r["commit"] or r["id"]
        if key not in best or r["norm"] > best[key]["norm"]:
            best[key] = r
    uniq = sorted(best.values(), key=lambda r: -r["norm"])
    print("distinct packages: %d" % len(uniq))

    ours = [r for r in recs if r["solver"] == "morganmcg1"]
    ourbest = max(ours, key=lambda r: r["norm"]) if ours else None

    print("\n=== top %d packages by NORMALIZED score ===" % top)
    print(
        "%-4s %-22s %-10s %9s %8s %-14s %-14s %s"
        % ("#", "solver", "commit", "decode us", "pref us", "normalized", "published", "created")
    )
    for n, r in enumerate(uniq[:top], 1):
        mark = " <== OURS" if r["solver"] == "morganmcg1" else ""
        print(
            "%-4d %-22s %-10s %9.1f %8.2f %-14.9f %-14.9f %s%s"
            % (
                n,
                r["solver"],
                r["commit"][:10],
                r["d"],
                r["p"],
                r["norm"],
                r["pub"] or 0.0,
                (r["created"] or "")[:19],
                mark,
            )
        )

    if ourbest:
        print(
            "\nour best normalized: %.9f (decode %.1f us, prefill %.2f us, commit %s)"
            % (ourbest["norm"], ourbest["d"], ourbest["p"], ourbest["commit"][:10])
        )
        rank = sum(1 for r in uniq if r["norm"] > ourbest["norm"]) + 1
        print("our rank among %d distinct packages by normalized: %d" % (len(uniq), rank))
        lead = uniq[0]
        print(
            "gap to best package %s (%s): normalized %+.4f %%, decode %+.1f us, prefill %+.2f us"
            % (
                lead["commit"][:10],
                lead["solver"],
                (lead["norm"] / ourbest["norm"] - 1) * 100,
                lead["d"] - ourbest["d"],
                lead["p"] - ourbest["p"],
            )
        )

    print("\n=== top %d packages by RAW DECODE (0.638 score elasticity) ===" % top)
    bydec = sorted(uniq, key=lambda r: r["d"])
    for n, r in enumerate(bydec[:top], 1):
        mark = " <== OURS" if r["solver"] == "morganmcg1" else ""
        print(
            "%-4d %-22s %-10s %9.1f %8.2f %-14.9f%s"
            % (n, r["solver"], r["commit"][:10], r["d"], r["p"], r["norm"], mark)
        )

    print("\n=== fetch targets (top 6 by normalized, full shas) ===")
    for r in uniq[:6]:
        print("git fetch origin %s   # %s norm=%.9f d=%.1f" % (r["commit"], r["solver"], r["norm"], r["d"]))


if __name__ == "__main__":
    main()
