#!/usr/bin/env python3
"""Research-only (PR #571, R103-A rung 2): per-kernel census of the OLD->NEW arm.

Parses the `--profile` tables written by the rung-2 ABBA session (the same
driver as rung 1, run with PROFILE=1 SPLIT=1 against the hook-built snapshots)
and forms, per kernel, the same two paired contrasts rung 1 used:

    real  =  new  - old     (interior slots)
    null  =  oldB - oldA    (exterior slots, identical code)

The null column is the point of the exercise. A per-kernel table with no null
invites reading the largest number in a 60-row list as the answer; with 60 rows
the largest *noise* entry is expected to be sizeable. A kernel is only a
candidate if its real contrast stands clear of what the same rig produces
between two byte-identical binaries.

SPLIT=1 puts one dispatch per command buffer to buy attribution, which inflates
absolute GPU time. Every number here is therefore an arm-vs-arm relative
estimator (rule 43), never an end-to-end magnitude, and the reconciliation is
against this session's own wall delta -- not against rung 1's unprofiled one.

Usage: python3 research/maple-frieren-r103a-census.py OUTDIR [WARMUP_REPS]
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}

ROW = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+(\S.*)$")
# decode_probe.py emits everything past --profile-top as one blank-column row.
# It has to enter the census as a pseudo-kernel, otherwise the reconciliation
# residual would silently absorb the truncated tail.
TAIL = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+\.\.\.\s+(\d+) more\s*$")
TAIL_KEY = "<tail beyond --profile-top>"
SUMMARY = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms")


def t95(df: int) -> float:
    if df <= 0:
        return float("nan")
    return _T95.get(df, 1.96 + 2.4 / df)


def paired(diffs: list[float]) -> dict[str, float]:
    k = len(diffs)
    if k < 2:
        return {"k": k, "mean": float("nan"), "lo": float("nan"),
                "hi": float("nan"), "sd": float("nan"), "pos": 0, "neg": 0}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    hw = t95(k - 1) * sd / math.sqrt(k)
    return {"k": k, "mean": m, "sd": sd, "half_width": hw,
            "lo": m - hw, "hi": m + hw,
            "pos": sum(1 for d in diffs if d > 0),
            "neg": sum(1 for d in diffs if d < 0)}


def parse_slot(path: Path) -> dict:
    """One profiled slot: per-kernel us/step plus the wall/busy summary."""
    kernels: dict[str, float] = {}
    totals: dict[str, float] = {}
    for line in path.read_text().splitlines():
        m = SUMMARY.search(line)
        if m:
            totals = {"wall_us": float(m.group(1)) * 1e3,
                      "busy_sum_us": float(m.group(2)) * 1e3,
                      "busy_union_us": float(m.group(3)) * 1e3,
                      "gap_us": float(m.group(4)) * 1e3}
            continue
        t = TAIL.match(line)
        if t:
            kernels[TAIL_KEY] = kernels.get(TAIL_KEY, 0.0) + float(t.group(1))
            continue
        r = ROW.match(line)
        if r:
            # A kernel may legitimately appear twice (different command-buffer
            # groupings); accumulate rather than overwrite.
            kernels[r.group(5).strip()] = \
                kernels.get(r.group(5).strip(), 0.0) + float(r.group(1))
    return {"kernels": kernels, **totals}


def main() -> None:
    out = Path(sys.argv[1])
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    rows = [ln.split("\t") for ln in
            (out / "index.tsv").read_text().strip().splitlines()[1:]]
    by_rep: dict[int, dict[str, dict]] = defaultdict(dict)
    for rep_s, _pos, arm, tag in rows:
        f = out / f"{tag}.log"
        if not f.exists():
            print(f"MISSING {f}", file=sys.stderr)
            continue
        by_rep[int(rep_s)][arm] = parse_slot(f)

    reps = [r for r in sorted(by_rep) if r >= warmup
            and all(a in by_rep[r] for a in ("oldA", "old", "new", "oldB"))]
    if not reps:
        sys.exit("no complete repetitions to analyse")

    names = sorted({k for r in reps for a in by_rep[r]
                    for k in by_rep[r][a]["kernels"]})

    def series(rep: int, arm: str, kern: str) -> float:
        # Absence is a real zero: a kernel dispatched by only one arm is
        # exactly the kind of difference this census exists to find.
        return by_rep[rep][arm]["kernels"].get(kern, 0.0)

    per_kernel = []
    for kern in names:
        real = paired([series(r, "new", kern) - series(r, "old", kern)
                       for r in reps])
        null = paired([series(r, "oldB", kern) - series(r, "oldA", kern)
                       for r in reps])
        level = statistics.mean([series(r, "old", kern) for r in reps])
        present = {a: sum(1 for r in reps if kern in by_rep[r][a]["kernels"])
                   for a in ("old", "new")}
        per_kernel.append({"kernel": kern, "old_us_step": level,
                           "real": real, "null": null, "present": present,
                           # A kernel clears the rig's own floor only if its
                           # real CI excludes zero *and* its magnitude exceeds
                           # the identical-code null's CI half-width.
                           "clears_null": bool(
                               real["lo"] * real["hi"] > 0
                               and abs(real["mean"])
                               > abs(null.get("half_width", float("inf"))))})
    per_kernel.sort(key=lambda d: -abs(d["real"]["mean"]))

    tot = {}
    for key in ("wall_us", "busy_sum_us", "busy_union_us", "gap_us"):
        tot[key] = {
            "real": paired([by_rep[r]["new"][key] - by_rep[r]["old"][key]
                            for r in reps]),
            "null": paired([by_rep[r]["oldB"][key] - by_rep[r]["oldA"][key]
                            for r in reps])}

    kernel_sum = sum(d["real"]["mean"] for d in per_kernel)
    result = {"warmup_reps": warmup, "analysed_reps": reps,
              "n_kernels": len(names), "totals": tot,
              "reconciliation": {
                  "sum_per_kernel_real_us": kernel_sum,
                  "busy_sum_real_us": tot["busy_sum_us"]["real"]["mean"],
                  "residual_vs_busy_sum_us":
                      tot["busy_sum_us"]["real"]["mean"] - kernel_sum,
                  "wall_real_us": tot["wall_us"]["real"]["mean"],
                  "residual_vs_wall_us":
                      tot["wall_us"]["real"]["mean"] - kernel_sum},
              "per_kernel": per_kernel}
    (out / "census.json").write_text(json.dumps(result, indent=2))

    print(f"reps analysed: {reps}   kernels seen: {len(names)}")
    print("\n--- session totals (us/step, SPLIT=1 inflated: relative only) ---")
    for key, blk in tot.items():
        for nm in ("real", "null"):
            p = blk[nm]
            print(f"  {key:14s} {nm:4s} mean={p['mean']:+9.2f} "
                  f"95% CI [{p['lo']:+9.2f}, {p['hi']:+9.2f}]")

    print(f"\n--- per-kernel, sorted by |new-old| (top 25 of {len(names)}) ---")
    print(f"  {'new-old us/step':>16} {'95% CI':>22} "
          f"{'null oldB-oldA':>16} {'OLD level':>10}  kernel")
    for d in per_kernel[:25]:
        r, nl = d["real"], d["null"]
        flag = "*" if d["clears_null"] else " "
        print(f" {flag}{r['mean']:+15.2f} "
              f"[{r['lo']:+9.2f},{r['hi']:+9.2f}] "
              f"{nl['mean']:+16.2f} {d['old_us_step']:10.1f}  {d['kernel'][:70]}")
    print("  (* = real CI excludes 0 and |real| exceeds the null CI "
          "half-width on the same kernel)")

    rec = result["reconciliation"]
    print("\n--- reconciliation ---")
    print(f"  sum of per-kernel real diffs : {rec['sum_per_kernel_real_us']:+9.2f} us/step")
    print(f"  measured gpu_busy_sum diff   : {rec['busy_sum_real_us']:+9.2f} us/step")
    print(f"  residual (unattributed)      : {rec['residual_vs_busy_sum_us']:+9.2f} us/step")
    print(f"  measured wall diff           : {rec['wall_real_us']:+9.2f} us/step")
    print(f"  residual vs wall             : {rec['residual_vs_wall_us']:+9.2f} us/step")


if __name__ == "__main__":
    main()
