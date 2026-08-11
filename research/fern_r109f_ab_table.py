#!/usr/bin/env python3
"""Print the local-iterate A/B arm table for R109-F.

Usage: python3 research/fern_r109f_ab_table.py
Walks research/artifacts/fern-r109f/ (and ab/) score JSONs, extracts the decode
and prefill legs plus the correctness/golden hash, and reports each arm's delta
against the HEAD baseline arm.
"""
import glob
import json
import os

BASE_KEY = "head-17868864"


def walk(obj, out):
    """Collect every dict that carries a decode_seconds_per_token key."""
    if isinstance(obj, dict):
        if "decode_seconds_per_token" in obj:
            out.append(obj)
        for v in obj.values():
            walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, out)


def load(path):
    with open(path) as fh:
        doc = json.load(fh)
    hits = []
    walk(doc, hits)
    if not hits:
        return None
    rec = hits[0]
    # golden hash / correctness may live at another level
    ghits = []

    def gwalk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("golden_hash", "goldenHash"):
                    ghits.append(v)
                gwalk(v)
        elif isinstance(o, list):
            for v in o:
                gwalk(v)

    gwalk(doc)
    return {
        "decode": rec.get("decode_seconds_per_token"),
        "prefill": rec.get("prefill_seconds_per_token"),
        "passed": rec.get("passed_correctness"),
        "golden": (ghits[0][:16] if ghits else None),
    }


def main():
    paths = sorted(glob.glob("research/artifacts/fern-r109f/score.*.json")) + sorted(
        glob.glob("research/artifacts/fern-r109f/ab/score.*.json")
    )
    rows = []
    for p in paths:
        rec = load(p)
        if rec is None:
            print("NO LEGS: %s" % p)
            continue
        label = os.path.basename(p)
        label = label[len("score.") :].replace(".local-iterate", "").replace(".json", "")
        rows.append((label, rec))

    base = None
    for label, rec in rows:
        if BASE_KEY in label:
            base = rec
            break

    print("%-28s %-20s %-11s %-22s %-8s %s" % ("arm", "decode s/tok", "d vs base", "prefill s/tok", "pass", "golden"))
    for label, rec in rows:
        d = rec["decode"]
        if base and base["decode"] and d:
            rel = (d - base["decode"]) / base["decode"] * 100.0
            delta = "%+.4f%%" % rel
        else:
            delta = "-"
        print(
            "%-28s %-20.12g %-11s %-22.12g %-8s %s"
            % (label, d, delta, rec["prefill"], rec["passed"], rec["golden"])
        )

    if base:
        print()
        print("baseline arm = %s (decode %.12g)" % (BASE_KEY, base["decode"]))
        print("absolute deltas in microseconds per token:")
        for label, rec in rows:
            if rec["decode"]:
                print("  %-28s %+9.2f us" % (label, (rec["decode"] - base["decode"]) * 1e6))


if __name__ == "__main__":
    main()
