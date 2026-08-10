#!/usr/bin/env python3
"""r105-D decode dispatch/occupancy census.

Reads the 105-C dispatch traces (research/r103b/scripts/trace.patch instrument)
and emits, for one steady-state one-token decode step:

  * research/artifacts/fern-r105d/decode-dispatch-census.csv
      one row per dispatch ordinal AND one row per kernel family.
  * research/artifacts/fern-r105d/decode-occupancy-summary.json
      the aggregate counters the report quotes.

Occupancy model
---------------
Every decode dispatch in the trace uses kind="threads" (dispatchThreads), so the
threadgroup count is grid/threadgroup componentwise.

Two distinct "waves" are reported and must not be conflated:

  waves_dispatch  = ceil(TGs / C)
      the PR #196 staircase. T(K) = a + b*ceil(K/C), a=1.661us, b=7.408us,
      C=20 measured on M4 Pro, C=40 extrapolated to the ranked M5. This is the
      quantity that actually prices a decode kernel, and it charges NOTHING for
      idle threadgroup slots inside a wave.

  waves_resident  = ceil(TGs / (C * R)),  R = residency in TGs per core
      R is modelled as floor(96 / simdgroups_per_TG) from two measured points:
        - PR #196: 1024 thr/TG (32 simdgroups) -> 3 TG/core   => 96
        - PR #138: 128 thr/TG  (4 simdgroups)  -> 24.0 TG/core => 96
      A rival "hard cap of 24 TGs/core" model fits #138 but is refuted by #196.
      At 64 thr/TG (2 simdgroups) the two models are NOT distinguished by any
      measurement in the programme: the simdgroup model says R=48, a TG-count
      cap would say R=24. Both are emitted; neither is verified.

Usage:
    python3 research/fern_r105d_census.py [--dump-dir /tmp/r105c/dump] [--arm a_base]
"""

import argparse
import csv
import json
import os
import re
from collections import Counter, OrderedDict

MARKER_PREFIX = "custom_kernel_laguna_decode_embedding_rope_atlas"

# PR #196 staircase constants, M4 Pro, microseconds.
PR196_A_US = 1.661
PR196_B_US = 7.408
# Rule 65: marginal cost of ADDING one dispatch on the ranked M5.
RULE65_US = 2.3403
# Decode score price: 1% of composite score = 65.67 us/step.
US_PER_PCT_SCORE = 65.67
# Reference M5 ranked decode step, us (4893.7 wall - 752.2 amortised seed prefill).
M5_STEP_US = 4141.5

DIM = re.compile(r"^(\d+)x(\d+)x(\d+)$")


def parse_dims(s):
    m = DIM.match(s.strip())
    if not m:
        raise ValueError(f"bad dims {s!r}")
    return tuple(int(g) for g in m.groups())


def load(path):
    rows = []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            try:
                seq = int(parts[0])
                grid = parse_dims(parts[3])
                tg = parse_dims(parts[4])
            except ValueError:
                continue
            rows.append((seq, parts[1], parts[2], grid, tg))
    return rows


def steady_window(rows):
    """Return the last complete inter-marker interval, plus all interval lengths."""
    idx = [i for i, r in enumerate(rows) if r[1].startswith(MARKER_PREFIX)]
    lens = [idx[i + 1] - idx[i] for i in range(len(idx) - 1)]
    if len(idx) < 3:
        raise SystemExit("not enough decode-step markers in trace")
    # last complete interval: between the final two markers
    return rows[idx[-2]:idx[-1]], lens


def short(name):
    n = name
    for pfx in ("custom_kernel_laguna_decode_", "custom_kernel_laguna_",
                "custom_kernel_", "steel_", "mlx_"):
        if n.startswith(pfx):
            n = n[len(pfx):]
            break
    return n


def family_stats(name, kind, grid, tg):
    if kind != "threads":
        raise SystemExit(f"unexpected dispatch kind {kind!r} for {name}")
    thr_per_tg = tg[0] * tg[1] * tg[2]
    grid_threads = grid[0] * grid[1] * grid[2]
    if any(g % t for g, t in zip(grid, tg)):
        # non-integral: Metal rounds the last group up per axis
        tgs = 1
        for g, t in zip(grid, tg):
            tgs *= -(-g // t)
    else:
        tgs = 1
        for g, t in zip(grid, tg):
            tgs *= g // t
    simd = -(-thr_per_tg // 32)
    return thr_per_tg, grid_threads, tgs, simd


def residency(simd_per_tg):
    """(R_simdgroup_model, R_tgcap24_model)."""
    return max(1, 96 // simd_per_tg), max(1, min(24, 96 // simd_per_tg))


def occupancy_class(tgs, C):
    if tgs == 1:
        return "SINGLE_TG"
    if tgs < C:
        return "SUB_C_UNDERFILL"
    if tgs < 4 * C:
        return "NEAR_C"
    return "SATURATING"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-dir", default="/tmp/r105c/dump")
    ap.add_argument("--arm", default="a_base")
    ap.add_argument("--out-dir", default="research/artifacts/fern-r105d")
    args = ap.parse_args()

    tsv = os.path.join(args.dump_dir, args.arm, "dispatch.tsv")
    rows = load(tsv)
    step, lens = steady_window(rows)
    n = len(step)

    # ---- per-ordinal rows -------------------------------------------------
    ordinals = []
    for k, (seq, name, kind, grid, tg) in enumerate(step):
        thr, gthr, tgs, simd = family_stats(name, kind, grid, tg)
        R48, R24 = residency(simd)
        ordinals.append(OrderedDict(
            row_type="ordinal",
            ordinal=k,
            family=short(name),
            pipeline=name,
            kind=kind,
            grid_threads=gthr,
            threads_per_tg=thr,
            threadgroups=tgs,
            simdgroups_per_tg=simd,
            tg_launches=tgs,
            tg_per_core_C20=round(tgs / 20.0, 4),
            tg_per_core_C40=round(tgs / 40.0, 4),
            waves_dispatch_C20=-(-tgs // 20),
            waves_dispatch_C40=-(-tgs // 40),
            waves_resident_C40_R96simd=-(-tgs // (40 * R48)),
            waves_resident_C40_Rcap24=-(-tgs // (40 * R24)),
            residency_tg_per_core_simd_model=R48,
            residency_tg_per_core_cap24_model=R24,
            occupancy_class_C40=occupancy_class(tgs, 40),
            pr196_us_C40=round(PR196_A_US + PR196_B_US * (-(-tgs // 40)), 4),
        ))

    # ---- per-family rows --------------------------------------------------
    fam = OrderedDict()
    for o in ordinals:
        key = (o["family"], o["grid_threads"], o["threads_per_tg"])
        if key not in fam:
            f = OrderedDict(o)
            f["row_type"] = "family"
            f["ordinal"] = ""
            f["calls_per_step"] = 0
            f["ordinals"] = []
            fam[key] = f
        fam[key]["calls_per_step"] += 1
        fam[key]["ordinals"].append(o["ordinal"])

    fam_rows = []
    for f in fam.values():
        c = f["calls_per_step"]
        f["tg_launches"] = f["threadgroups"] * c
        f["pr196_us_C40"] = round(f["pr196_us_C40"] * c, 4)
        f["rule65_add_us_per_step"] = round(RULE65_US * c, 4)
        ords = f.pop("ordinals")
        f["ordinal_list"] = ",".join(str(x) for x in (ords if len(ords) <= 6 else ords[:3] + ["..."] + ords[-2:]))
        fam_rows.append(f)
    fam_rows.sort(key=lambda r: -r["tg_launches"])

    # ---- aggregates -------------------------------------------------------
    tg_total = sum(o["threadgroups"] for o in ordinals)
    thread_total = sum(o["grid_threads"] for o in ordinals)
    single_tg = [o for o in ordinals if o["threadgroups"] == 1]
    sub_c40 = [o for o in ordinals if o["threadgroups"] < 40]
    sub_c20 = [o for o in ordinals if o["threadgroups"] < 20]
    waves40 = sum(o["waves_dispatch_C40"] for o in ordinals)
    waves20 = sum(o["waves_dispatch_C20"] for o in ordinals)
    res40 = sum(o["waves_resident_C40_R96simd"] for o in ordinals)

    summary = OrderedDict(
        arm=args.arm,
        trace=tsv,
        marker=MARKER_PREFIX,
        marker_interval_lengths=lens,
        marker_interval_tail=lens[-5:],
        dispatches_per_step=n,
        distinct_families=len(fam_rows),
        tg_launches_per_step=tg_total,
        gpu_threads_per_step=thread_total,
        single_tg_dispatches=len(single_tg),
        single_tg_families=sorted({o["family"] for o in single_tg}),
        sub_C40_dispatches=len(sub_c40),
        sub_C20_dispatches=len(sub_c20),
        waves_dispatch_C40_total=waves40,
        waves_dispatch_C20_total=waves20,
        waves_resident_C40_simdmodel_total=res40,
        pr196_modelled_us_C40=round(sum(
            PR196_A_US + PR196_B_US * o["waves_dispatch_C40"] for o in ordinals), 3),
        rule65_add_price_us_per_step=round(RULE65_US * n, 3),
        rule65_add_price_pct_score=round(RULE65_US * n / US_PER_PCT_SCORE, 4),
        rule65_single_tg_us_per_step=round(RULE65_US * len(single_tg), 3),
        m5_reference_step_us=M5_STEP_US,
        us_per_pct_score=US_PER_PCT_SCORE,
    )

    os.makedirs(args.out_dir, exist_ok=True)
    cols = list(ordinals[0].keys())
    for extra in ("calls_per_step", "rule65_add_us_per_step", "ordinal_list"):
        if extra not in cols:
            cols.append(extra)
    with open(os.path.join(args.out_dir, "decode-dispatch-census.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in fam_rows:
            w.writerow(r)
        for r in ordinals:
            w.writerow(r)

    with open(os.path.join(args.out_dir, "decode-occupancy-summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps(summary, indent=2))
    print("\nfamily  calls  TGs  thr/TG  simd/TG  TG-launches  class(C40)  waves_disp(C40)")
    for r in fam_rows:
        print(f"{r['family'][:42]:42s} {r['calls_per_step']:3d} {r['threadgroups']:6d} "
              f"{r['threads_per_tg']:5d} {r['simdgroups_per_tg']:3d} {r['tg_launches']:8d} "
              f"{r['occupancy_class_C40']:16s} {r['waves_dispatch_C40']:4d}")


if __name__ == "__main__":
    main()
