#!/usr/bin/env python3
"""Scan local benchmark logs and print derived S/T for candidate and baseline.

S = 512000 * prefill_seconds_per_token (ms, one 512-token prefill)
T = 1000 * decode_seconds_per_token - S/128 (ms, one decode step net of amortised prefill)
"""
import glob
import os
import re
import sys

KEYS = (
    "baseline_prefill_seconds_per_token",
    "baseline_decode_seconds_per_token",
    "prefill_seconds_per_token",
    "decode_seconds_per_token",
)


def derive(pre, dec):
    s = 512000.0 * pre
    t = 1000.0 * dec - s / 128.0
    return s, t


def scan(path):
    vals = {}
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            m = re.match(r'\s*"([a-z_]+)"\s*:\s*([0-9.eE+-]+),?\s*$', line)
            if m and m.group(1) in KEYS:
                vals[m.group(1)] = float(m.group(2))
    return vals


def main():
    root = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    logs = sorted(glob.glob(os.path.join(root, "*.log")), key=os.path.getmtime, reverse=True)[:n]
    print(f"{'log':10} {'mtime':16} {'S_cand':>9} {'T_cand':>8} {'S_base':>9} {'T_base':>8} {'T/Tb':>7}")
    for p in logs:
        v = scan(p)
        if not all(k in v for k in KEYS):
            continue
        sc, tc = derive(v["prefill_seconds_per_token"], v["decode_seconds_per_token"])
        sb, tb = derive(v["baseline_prefill_seconds_per_token"], v["baseline_decode_seconds_per_token"])
        import datetime

        ts = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M")
        print(
            f"{os.path.basename(p)[:8]:10} {ts:16} {sc:9.3f} {tc:8.5f} {sb:9.3f} {tb:8.5f} {tc/tb:7.4f}"
        )


if __name__ == "__main__":
    main()
