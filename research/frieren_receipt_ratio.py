"""Derive the paired within-session steady-step ratio R = T_base/T_cand from
official receipts, and report how reproducible each candidate statistic is
across bit-identical submissions.

Analysis-only helper (not part of the challenge runtime).
Usage: python3 research/frieren_receipt_ratio.py <receipt.json> [...]
"""

import glob
import json
import statistics as st
import sys

NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845


def find(obj, key):
    if isinstance(obj, dict):
        v = obj.get(key)
        if isinstance(v, (int, float)):
            return v
        for sub in obj.values():
            got = find(sub, key)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for sub in obj:
            got = find(sub, key)
            if got is not None:
                return got
    return None


def load(path):
    doc = json.load(open(path))
    d = find(doc, "decode_seconds_per_token")
    p = find(doc, "prefill_seconds_per_token")
    db = find(doc, "baseline_decode_seconds_per_token")
    pb = find(doc, "baseline_prefill_seconds_per_token")
    score = find(doc, "officialScore")
    if score is None:
        score = find(doc, "score")
    # S: milliseconds for the whole 512-token seed forward.
    # T: milliseconds for one marginal steady decode step.
    s = 512000.0 * p
    t = 1000.0 * d - s / 128.0
    sb = 512000.0 * pb
    tb = 1000.0 * db - sb / 128.0
    ns = (NORM_DECODE / d) ** 0.75 * (NORM_PREFILL / p) ** 0.25
    return {
        "path": path.split("/")[-1],
        "T": t,
        "T_base": tb,
        "R": tb / t,
        "S": s,
        "S_base": sb,
        "RS": sb / s,
        "ns": ns,
        "score": score or float("nan"),
    }


def spread(name, vals):
    mean = st.mean(vals)
    sd = st.stdev(vals) if len(vals) > 1 else float("nan")
    print(f"  {name:9} mean={mean:12.6f}  sd={sd:10.6f}  cv={100 * sd / mean:7.4f}%  n={len(vals)}")


def main(paths):
    rows = [load(p) for p in paths]
    hdr = ("file", "T_cand", "T_base", "R=Tb/T", "S_cand", "S_base", "RS", "ns", "score")
    print(f"{hdr[0]:18}{hdr[1]:>9}{hdr[2]:>10}{hdr[3]:>10}{hdr[4]:>10}{hdr[5]:>10}{hdr[6]:>9}{hdr[7]:>9}{hdr[8]:>10}")
    for r in rows:
        print(
            f"{r['path']:18}{r['T']:9.4f}{r['T_base']:10.4f}{r['R']:10.5f}"
            f"{r['S']:10.4f}{r['S_base']:10.4f}{r['RS']:9.5f}{r['ns']:9.5f}{r['score']:10.5f}"
        )
    if len(rows) < 2:
        return
    print("\nreproducibility across these receipts:")
    for key in ("T", "T_base", "R", "S", "S_base", "RS", "ns", "score"):
        spread(key, [r[key] for r in rows])


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(glob.glob("research/m5-calibration/[ABC]_*.json"))
    main(args)
