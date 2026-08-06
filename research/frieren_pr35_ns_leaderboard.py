#!/usr/bin/env python3
"""Rank gate-passing receipts by `ns`, the session-normalised score plane.

`officialScore` is paired against whatever baseline the official session
measured, so it moves with baseline drift and is not comparable across
receipts. `ns` renormalises every candidate against the pinned constants, which
is what makes two receipts from different sessions comparable.

usage: frieren_pr35_ns_leaderboard.py <feed.json> [highlight-id-prefix]
"""
import json
import sys

BASE_D = 0.013890
BASE_P = 0.0003845


def coerce(m):
    if isinstance(m, str):
        try:
            return json.loads(m)
        except Exception:
            return {}
    return m or {}


def main():
    feed = json.load(open(sys.argv[1]))
    mark_id = sys.argv[2] if len(sys.argv) > 2 else ""
    if isinstance(feed, dict):
        for k in ("submissions", "data", "items", "results"):
            if k in feed:
                feed = feed[k]
                break

    rows = []
    for s in feed:
        m = coerce(s.get("officialMetrics"))
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        if not d or not p:
            continue
        if not (
            m.get("passed_correctness")
            and m.get("passed_prefill_speedup_floor")
            and m.get("passed_decode_speedup_floor")
        ):
            continue
        rows.append(
            {
                "ns": (BASE_D / d) ** 0.75 * (BASE_P / p) ** 0.25,
                "id": (s.get("id") or "")[:8],
                "status": s.get("status"),
                "base_d": m.get("baseline_decode_seconds_per_token"),
                "cand_d": d,
                "cand_p": p,
                "off": s.get("officialScore"),
                "improved": s.get("improved"),
            }
        )

    rows.sort(key=lambda r: -r["ns"])
    print("gate-passing receipts: %d" % len(rows))
    print()
    hdr = "%-4s %-9s %-9s %-10s %-13s %-13s %-9s %s"
    print(hdr % ("#", "ns", "id", "status", "base_dspt", "cand_dspt", "offScore", "improved"))
    for i, r in enumerate(rows[:12], 1):
        flag = "  <== THIS RECEIPT" if mark_id and r["id"].startswith(mark_id[:8]) else ""
        print(
            "%-4d %-9.5f %-9s %-10s %-13.9f %-13.9f %-9s %s%s"
            % (
                i,
                r["ns"],
                r["id"],
                r["status"],
                r["base_d"] or 0,
                r["cand_d"],
                ("%.5f" % r["off"]) if r["off"] else "n/a",
                r["improved"],
                flag,
            )
        )

    if mark_id:
        hits = [i for i, r in enumerate(rows) if r["id"].startswith(mark_id[:8])]
        if hits:
            k = hits[0]
            others = [r["ns"] for j, r in enumerate(rows) if j != k]
            print()
            print("rank of %s by ns    : %d of %d" % (mark_id[:8], k + 1, len(rows)))
            print("this receipt ns      : %.6f" % rows[k]["ns"])
            print("best other receipt ns: %.6f" % max(others))
            print("margin over field    : %+.4f %%" % ((rows[k]["ns"] / max(others) - 1) * 100))

    print()
    print("-- officialScore ranking, for contrast --")
    byoff = sorted([r for r in rows if r["off"]], key=lambda r: -r["off"])[:5]
    for i, r in enumerate(byoff, 1):
        print("%-4d off=%.6f ns=%.6f %-9s base_dspt=%.9f" % (i, r["off"], r["ns"], r["id"], r["base_d"] or 0))


if __name__ == "__main__":
    main()
