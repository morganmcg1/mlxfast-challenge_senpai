#!/usr/bin/env python3
"""R128-D instrument-overhead ladder: matched-window arm deltas with CIs.

Each arm contributes one median step per run; deltas are medians of per-run
medians with a Welch-style t interval from the per-run spread, so the reported
uncertainty is the run-to-run reproducibility actually achieved (Rule 11).

  python3 research/alphonse-r128d-ladder.py
"""
import json
import math
import statistics as st

ARMS = ["clean", "clean-recheck", "hook-off", "hook-on", "hook-split"]
T = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447}


def load(path):
    blob = json.load(open(path))
    out = []
    for r in blob["runs"]:
        steps = [b - a for a, b in r["spans"][1:]]
        out.append((st.median(steps) * 1e6, st.median(steps[:127]) * 1e6))
    return out


def delta(arms, a, b, idx, label):
    A = [x[idx] for x in arms[a]]
    B = [x[idx] for x in arms[b]]
    ea = (st.stdev(A) if len(A) > 1 else 0.0) / math.sqrt(len(A))
    eb = (st.stdev(B) if len(B) > 1 else 0.0) / math.sqrt(len(B))
    df = max(1, min(len(A), len(B)) - 1)
    hw = T.get(df, 2.0) * math.hypot(ea, eb)
    print(f"{label:<46} {st.median(A)-st.median(B):+8.1f} +/- {hw:5.1f} us "
          f"(t{df})")
    return st.median(A) - st.median(B), hw


def main():
    arms = {n: load(f"/tmp/r128d-{n}.json") for n in ARMS}
    print(f"{'arm':<14}{'runs':>5} {'full-window':>12} {'sd':>7}   "
          f"{'128-window':>11} {'sd':>7}")
    for k, v in arms.items():
        f = [a for a, _ in v]
        w = [b for _, b in v]
        sf = st.stdev(f) if len(f) > 1 else 0.0
        sw = st.stdev(w) if len(w) > 1 else 0.0
        print(f"{k:<14}{len(v):>5} {st.median(f):12.1f} {sf:7.1f}   "
              f"{st.median(w):11.1f} {sw:7.1f}")

    print("\n--- ladder rungs, 128-step window (matched across all arms) ---")
    delta(arms, "hook-off", "clean-recheck", 1, "hook compiled in, disabled")
    delta(arms, "hook-off", "clean", 1, "hook compiled in, disabled (vs J1)")
    delta(arms, "hook-on", "hook-off", 1, "INSTRUMENT OVERHEAD")
    delta(arms, "hook-split", "hook-on", 1, "command-buffer fission")
    delta(arms, "hook-split", "clean-recheck", 1, "fission vs pristine")

    print("\n--- same rungs on each arm's own full window ---")
    delta(arms, "hook-off", "clean", 0, "hook compiled in, disabled (1023)")
    delta(arms, "hook-on", "hook-off", 0, "INSTRUMENT OVERHEAD (1023)")
    delta(arms, "hook-split", "clean-recheck", 0, "fission vs pristine (200)")


if __name__ == "__main__":
    main()
