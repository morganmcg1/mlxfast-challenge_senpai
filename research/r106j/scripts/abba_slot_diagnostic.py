#!/usr/bin/env python3
"""Diagnose position/build-reuse confounding in the T0-vs-T1 ABBA sweep.

`abba_t0_t1.sh` only rewrites `Sources/` when the arm actually changes, so the
third slot of every block reuses the previous run's build. That slot is not
symmetric across an odd number of blocks: with 3 blocks it is held by T1 twice
and by T0 once. This script measures how large the slot effect is and which
direction it biases the headline contrast.
"""

import math
import sys

sys.path.insert(0, "research/r106j/scripts")
from analyze_abba import read_rows  # noqa: E402

RUNS = "research/artifacts/maple-fern-r106j/abba/runs.tsv"


def annotate(rows):
    prev = None
    for i, r in enumerate(rows):
        r["pos"] = i % 4 + 1
        r["block"] = i // 4 + 1
        r["reused_build"] = prev is not None and prev["arm"] == r["arm"]
        for key in ("decode_s_per_token", "prefill_s_per_token"):
            r[key] = float(r[key])
        r["wall_s"] = int(r["wall_s"])
        prev = r
    for arm in ("T0", "T1"):
        sub = [r for r in rows if r["arm"] == arm]
        for key in ("decode_s_per_token", "prefill_s_per_token"):
            mean = sum(r[key] for r in sub) / len(sub)
            for r in sub:
                r[f"dev_{key}"] = 100 * math.log(r[key] / mean)
    return rows


def group(rows, key, values, label, metric):
    print(f"\n-- {metric} deviation from own-arm mean, %, by {label} --")
    for v in values:
        sub = [r[f"dev_{metric}"] for r in rows if r[key] == v]
        if not sub:
            continue
        mean = sum(sub) / len(sub)
        vals = ", ".join(f"{x:+.3f}" for x in sub)
        print(f"  {label}={v!s:<5} n={len(sub)}  mean={mean:+.4f}%  [{vals}]")


def main() -> int:
    rows = annotate(read_rows(RUNS))
    hdr = f"{'idx':>3} {'blk':>3} {'pos':>3} {'arm':>3} {'reused':>6} {'wall_s':>6}"
    print(hdr + f" {'decode':>13} {'prefill':>13}")
    for r in rows:
        print(
            f"{r['idx']:>3} {r['block']:>3} {r['pos']:>3} {r['arm']:>3} "
            f"{str(r['reused_build']):>6} {r['wall_s']:>6} "
            f"{r['decode_s_per_token']:>13.9f} {r['prefill_s_per_token']:>13.9f}"
        )

    for metric in ("decode_s_per_token", "prefill_s_per_token"):
        group(rows, "reused_build", [False, True], "reused_build", metric)
        group(rows, "pos", [1, 2, 3, 4], "pos", metric)

    print("\n-- arm holding the build-reuse slot in each block --")
    tally = {"T0": 0, "T1": 0}
    for b in sorted({r["block"] for r in rows}):
        slot = [r["arm"] for r in rows if r["block"] == b and r["reused_build"]]
        for a in slot:
            tally[a] += 1
        print(f"  block {b}: {slot}")
    print(f"  tally: {tally}")
    print(
        "  A slot penalty p biases the headline contrast by "
        "p*(n_T1_slots - n_T0_slots)/(2*nblocks) against T1."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
