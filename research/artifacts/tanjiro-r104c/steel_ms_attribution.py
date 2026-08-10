#!/usr/bin/env python3
"""Exhaustive, non-overlapping millisecond attribution of the 237 prefill steel
GEMM dispatches, joined to the r104-c shape census.

Tier 2 only: every millisecond here was measured on this M4 Pro. The source is
the PR #270 SPLIT=1 acquisition (`research/pr270-logs/split1.worker.err`), in
which each command buffer carries exactly one steel GEMM dispatch (a split-K
GEMM carries its inseparable `steel_gemm_splitk_accum` in the same buffer, and
is charged with it).

The join is positional and is *proved*, not assumed: the 237-long kernel-name
sequence recovered from the GPUPROF stream must equal the 237-long kernel-name
sequence of the census, in every one of the 7 recorded forward passes.

Usage:  python3 research/artifacts/tanjiro-r104c/steel_ms_attribution.py
"""

import csv
import json
import os
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LOG = os.path.join(ROOT, "research", "pr270-logs", "split1.worker.err")
CENSUS = os.path.join(ROOT, "research", "artifacts", "tanjiro-r104c",
                      "steel_census_237.json")
OUT_CSV = os.path.join(ROOT, "research", "artifacts", "tanjiro-r104c",
                       "steel_ms_attribution_m4.csv")
OUT_JSON = os.path.join(ROOT, "research", "artifacts", "tanjiro-r104c",
                        "steel_ms_attribution_m4.json")

# NMPC section 2.2: SPLIT=1 per-kernel times sum to 550.148 ms once the fully
# hidden `arangeuint32` is dropped, against the SPLIT=0 serial busy anchor of
# 540.396 ms. Every family is deflated by this factor so the ledger closes.
DEFLATION = 540.396 / 550.148
SERIAL_BUSY_MS = 540.396

# NMPC section 4.1, already deflated. Complement of the steel family, so that
# the grand total below is the whole measured M4 prefill.
NON_STEEL_FAMILIES = [
    ("routed_gather_gemm (MoE `W`)", 76, 260.907),
    ("attention_core", 40, 27.630),
    ("nvfp4_dense_qmm (shared expert)", 116, 19.648),
    ("elementwise", 234, 4.648),
    ("qk_norm_rope", 41, 4.136),
    ("sort_scatter (- arange)", 78, 2.598),
    ("moe_tail", 38, 2.535),
    ("rms_norm", 83, 1.691),
    ("router tournament", 40, 0.940),
    ("lm_head", 5, 0.655),
    ("other", 3, 0.308),
]

M4_BF16_PEAK_TFLOPS = 8.0     # rule 80 reference for this host
M5_BF16_PEAK_TFLOPS = 60.0    # rule 80 reference for the ranked host


def parse_gpuprof(path):
    """Return the ordered list of steel-GEMM command-buffer records."""
    recs = []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            f = line.split()
            if len(f) < 6:
                continue
            names = f[5].split("|")
            gemm = [n for n in names if n.startswith("steel_gemm_")
                    and "_accum_" not in n]
            if not gemm:
                continue
            if len(gemm) != 1:
                raise SystemExit("unexpected multi-GEMM command buffer: %s" % f[5])
            recs.append({
                "kernel": gemm[0],
                "ms": (float(f[2]) - float(f[1])) * 1000.0,
                "with_accum": any("_accum_" in n for n in names),
            })
    return recs


def main():
    census = json.load(open(CENSUS))
    t2 = [r for r in census["rows"] if r["tier"] == 2]
    t1 = [r for r in census["rows"] if r["tier"] == 1]
    t2.sort(key=lambda r: r["seq"])
    t1.sort(key=lambda r: r["seq"])
    n = len(t2)
    if n != 237 or len(t1) != 237:
        raise SystemExit("census is not 237+237 rows")

    recs = parse_gpuprof(LOG)
    if len(recs) % n:
        raise SystemExit("recovered %d steel records, not a multiple of %d"
                         % (len(recs), n))
    passes = [recs[i * n:(i + 1) * n] for i in range(len(recs) // n)]

    # The census records the kernel base name; the runtime profiler records the
    # fully specialised name, which extends it with the template suffix.
    expect = [r["kernel"] for r in t2]
    for pi, p in enumerate(passes):
        for i, r in enumerate(p):
            if not r["kernel"].startswith(expect[i]):
                raise SystemExit("pass %d diverges from the census at slot %d:\n"
                                 "  gpuprof: %s\n  census : %s"
                                 % (pi, i, r["kernel"], expect[i]))
    # A split-K record must carry its accum; a regular record must not.
    for p in passes:
        for i, r in enumerate(p):
            if r["with_accum"] != (t2[i]["path"] == "splitk"):
                raise SystemExit("accum pairing mismatch at slot %d" % i)

    # NMPC's profile block averages the 5 warm requests. Pick the trailing
    # window whose regular / split-K sums reproduce the published 182.988 /
    # 35.584 ms, and fail loudly if none does.
    target_reg, target_spk = 182.988, 35.584
    chosen = None
    for start in range(len(passes)):
        win = passes[start:]
        if len(win) != 5:
            continue
        reg = sum(sum(p[i]["ms"] for p in win) / len(win)
                  for i in range(n) if t2[i]["path"] == "regular")
        spk = sum(sum(p[i]["ms"] for p in win) / len(win)
                  for i in range(n) if t2[i]["path"] == "splitk")
        if abs(reg - target_reg) < 0.05 and abs(spk - target_spk) < 0.05:
            chosen = (start, win, reg, spk)
    if chosen is None:
        raise SystemExit("no 5-pass window reproduces NMPC 4.3 (182.988/35.584)")
    start, win, reg_ms, spk_ms = chosen

    rows = []
    for i, c in enumerate(t2):
        s = [p[i]["ms"] for p in win]
        mean = statistics.mean(s)
        rows.append({
            "seq": c["seq"], "M": c["M"], "N": c["N"], "K": c["K"],
            "path": c["path"], "site": c["site"], "kernel": c["kernel"],
            "threadgroups": c["threadgroups"], "tg_per_core": c["tg_per_core"],
            "gflop": c["gflop"],
            "ms_raw_mean": mean,
            "ms_raw_sd": statistics.stdev(s),
            "ms": mean * DEFLATION,
        })

    total = sum(r["ms"] for r in rows)

    # ---- buckets: (N, K, path) is the shape family; exhaustive, disjoint ----
    buckets = {}
    for i, r in enumerate(rows):
        key = (r["N"], r["K"], r["path"])
        b = buckets.setdefault(key, {
            "N": r["N"], "K": r["K"], "path": r["path"], "site": r["site"],
            "n": 0, "gflop": 0.0, "ms": 0.0, "tg_per_core": r["tg_per_core"],
            "m5_tg_per_core": t1[i]["tg_per_core"], "m5_path": t1[i]["path"],
        })
        b["n"] += 1
        b["gflop"] += r["gflop"]
        b["ms"] += r["ms"]
    blist = sorted(buckets.values(), key=lambda b: -b["ms"])
    for b in blist:
        b["tflops"] = b["gflop"] / b["ms"]          # GFLOP/ms == TFLOP/s
        b["pct_peak"] = 100.0 * b["tflops"] / M4_BF16_PEAK_TFLOPS
        b["pct_steel"] = 100.0 * b["ms"] / total
        b["pct_prefill"] = 100.0 * b["ms"] / SERIAL_BUSY_MS

    out = {
        "tier": 2,
        "tier_label": "observed-M4Pro",
        "source_log": "research/pr270-logs/split1.worker.err",
        "acquisition": "SPLIT=1, one steel GEMM per command buffer; a split-K "
                       "GEMM is charged together with its inseparable "
                       "steel_gemm_splitk_accum in the same buffer",
        "passes_recorded": len(passes),
        "warm_window_first_pass_index": start,
        "warm_window_size": len(win),
        "deflation_factor": DEFLATION,
        "serial_busy_ms": SERIAL_BUSY_MS,
        "check_regular_raw_ms": reg_ms,
        "check_splitk_raw_ms": spk_ms,
        "steel_total_ms": total,
        "buckets": blist,
        "rows": rows,
    }
    json.dump(out, open(OUT_JSON, "w"), indent=1, sort_keys=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    # ------------------------------- report -------------------------------
    print("passes recovered            : %d x %d dispatches" % (len(passes), n))
    print("warm window                 : passes %d..%d" % (start, len(passes) - 1))
    print("join                        : 237/237 kernel names match in all %d "
          "passes" % len(passes))
    print("check vs NMPC 4.3 raw       : regular %.3f ms (published 182.988), "
          "split-K %.3f ms (published 35.584)" % (reg_ms, spk_ms))
    print("steel wall, deflated        : %.3f ms (NMPC 4.1 published 214.698)"
          % total)
    print()
    hdr = ("%-34s %4s %9s %9s %7s %7s %8s %8s %7s"
           % ("bucket (N,K,path) / site", "n", "GFLOP", "ms", "%steel",
              "%prefil", "TFLOP/s", "%M4peak", "TG/core"))
    print(hdr)
    print("-" * len(hdr))
    cum = 0.0
    for b in blist:
        cum += b["pct_steel"]
        label = "N=%-5d K=%-5d %-8s" % (b["N"], b["K"], b["path"])
        print("%-34s %4d %9.1f %9.3f %7.2f %7.2f %8.2f %8.1f %7.2f"
              % (label, b["n"], b["gflop"], b["ms"], b["pct_steel"],
                 b["pct_prefill"], b["tflops"], b["pct_peak"], b["tg_per_core"]))
    print("-" * len(hdr))
    print("%-34s %4d %9.1f %9.3f %7.2f %7.2f %8.2f %8.1f"
          % ("STEEL TOTAL", sum(b["n"] for b in blist),
             sum(b["gflop"] for b in blist), total, 100.0,
             100.0 * total / SERIAL_BUSY_MS,
             sum(b["gflop"] for b in blist) / total,
             100.0 * (sum(b["gflop"] for b in blist) / total)
             / M4_BF16_PEAK_TFLOPS))
    print()
    print("complement of the steel family (NMPC 4.1, already deflated):")
    grand = total
    gcalls = sum(b["n"] for b in blist) + 155  # 155 accum ride with their GEMM
    for name, calls, ms in NON_STEEL_FAMILIES:
        grand += ms
        gcalls += calls
        print("  %-34s %4d %30.3f ms  %6.2f %%" % (name, calls, ms,
                                                   100.0 * ms / SERIAL_BUSY_MS))
    print("  %-34s %4d %30.3f ms  %6.2f %%" % ("GRAND TOTAL", gcalls, grand,
                                               100.0 * grand / SERIAL_BUSY_MS))
    print()

    # ---------------- concentration, measured in milliseconds ----------------
    ms_sorted = sorted((r["ms"] for r in rows), reverse=True)
    for k in (1, 5, 10, 20, 31, 61, 82, 118):
        print("  top %3d of 237 dispatches carry %6.2f %% of the steel wall"
              % (k, 100.0 * sum(ms_sorted[:k]) / total))
    tail = [r for r in rows if t1[r["seq"]]["tg_per_core"] <= 1.6]
    head = [r for r in rows if t1[r["seq"]]["tg_per_core"] > 1.6]
    print()
    print("  M5 tail set (<=1.6 TG/core on 40 cores): %d dispatches, "
          "%.1f GFLOP, %.3f ms on M4 = %.2f %% of the steel wall"
          % (len(tail), sum(r["gflop"] for r in tail),
             sum(r["ms"] for r in tail),
             100.0 * sum(r["ms"] for r in tail) / total))
    print("  M5 head set (> 1.6 TG/core on 40 cores): %d dispatches, "
          "%.1f GFLOP, %.3f ms on M4 = %.2f %% of the steel wall"
          % (len(head), sum(r["gflop"] for r in head),
             sum(r["ms"] for r in head),
             100.0 * sum(r["ms"] for r in head) / total))

    # Gini over the 237 measured milliseconds.
    xs = sorted(r["ms"] for r in rows)
    nn = len(xs)
    gini = (2 * sum((i + 1) * x for i, x in enumerate(xs))
            / (nn * sum(xs))) - (nn + 1) / nn
    print("  Gini of measured ms over the 237 dispatches: %.4f" % gini)
    print()

    # ---- where the measured deficit is, against the best observed bucket ----
    best = max(b["pct_peak"] for b in blist)
    print("measured M4 efficiency deficit, referenced to the best observed "
          "bucket (%.1f %% of peak):" % best)
    dtot = 0.0
    for b in blist:
        b["deficit_ms"] = b["ms"] * (1.0 - b["pct_peak"] / best)
        dtot += b["deficit_ms"]
    for b in blist:
        b["deficit_share"] = 100.0 * b["deficit_ms"] / dtot
    for b in sorted(blist, key=lambda x: -x["deficit_ms"]):
        print("  N=%-5d K=%-5d %-8s  %7.3f ms  %6.2f %% of the deficit"
              % (b["N"], b["K"], b["path"], b["deficit_ms"], b["deficit_share"]))
    print("  %-32s %7.3f ms  %6.2f %% of the measured steel wall"
          % ("TOTAL MEASURED DEFICIT", dtot, 100.0 * dtot / total))
    print()

    # ---- Tier 1: Projection B, per bucket, with the M5 route change flagged --
    print("TIER 1 (DERIVED, never observed): Projection B holds each bucket's "
          "M4 efficiency against the 60 TFLOP/s M5 reference.")
    m5tot = 0.0
    for b in blist:
        b["m5_proj_b_ms"] = b["gflop"] / (M5_BF16_PEAK_TFLOPS
                                          * b["pct_peak"] / 100.0)
        m5tot += b["m5_proj_b_ms"]
    for b in blist:
        flag = "ROUTE CHANGES" if b["m5_path"] != b["path"] else ""
        print("  N=%-5d K=%-5d M4 %-8s -> M5 %-8s  %7.3f ms  "
              "M5 %5.2f TG/core  %s"
              % (b["N"], b["K"], b["path"], b["m5_path"], b["m5_proj_b_ms"],
                 b["m5_tg_per_core"], flag))
    print("  %-46s %7.3f ms   (NMPC 4.3 published 28.6)" % ("TOTAL", m5tot))
    print()

    tail_b = [b for b in blist if b["m5_tg_per_core"] <= 1.6]
    head_b = [b for b in blist if b["m5_tg_per_core"] > 1.6]
    tail_ms = sum(b["m5_proj_b_ms"] for b in tail_b)
    wkwv = next(b for b in blist if (b["N"], b["K"]) == (1024, 2048))
    print("  M5 tail (<=1.6 TG/core): %.3f ms of the %.3f ms projection; "
          "wk/wv alone %.3f ms" % (tail_ms, m5tot, wkwv["m5_proj_b_ms"]))
    print("  M5 head (> 1.6 TG/core): %.3f ms"
          % sum(b["m5_proj_b_ms"] for b in head_b))
    print()

    # ---- the 11.40 ms M5-specific residual: bound, do not attribute ----
    RESID = 11.40
    PRICE = 0.3781          # %/ms of score, total (prospective) price
    PRICE_NMPC = 0.374750
    BAR = 1.438             # % of cs needed to take the standing record
    JOINT_CEILING = 9.33    # ms, advisor's non-additive tail ceiling
    floor_ms = wkwv["gflop"] / (M5_BF16_PEAK_TFLOPS * best / 100.0)
    print("the %.2f ms M5-specific residual is NOT attributable by any "
          "measurement in hand; these are the admissible apportionments:" % RESID)
    print("  a perfect wk/wv fix cannot go below the best observed efficiency "
          "%.1f %% => %.3f ms floor" % (best, floor_ms))
    scenarios = [
        ("residual diffuse, apportioned by projected ms",
         RESID * wkwv["m5_proj_b_ms"] / m5tot),
        ("residual diffuse, apportioned by dispatch count",
         RESID * wkwv["n"] / sum(b["n"] for b in blist)),
        ("residual concentrated in the M5 tail, by dispatch count",
         RESID * wkwv["n"] / sum(b["n"] for b in tail_b)),
        ("residual concentrated in the M5 tail, by GFLOP",
         RESID * wkwv["gflop"] / sum(b["gflop"] for b in tail_b)),
    ]
    print("  %-56s %9s %9s %9s %9s"
          % ("apportionment", "wkwv ms", "recover", "% score", "verdict"))
    for name, share in scenarios:
        totms = wkwv["m5_proj_b_ms"] + share
        rec = totms - floor_ms
        pct = rec * PRICE
        if rec > JOINT_CEILING:
            verdict = "INADMISSIBLE (> %.2f ms ceiling)" % JOINT_CEILING
        elif pct >= BAR:
            verdict = "clears %.3f %%" % BAR
        else:
            verdict = "SHORT of %.3f %%" % BAR
        print("  %-56s %9.3f %9.3f %9.3f  %s"
              % (name, totms, rec, pct, verdict))
    print("  bar in milliseconds: %.3f %% / %.4f %%/ms = %.3f ms "
          "(NMPC's 0.374750 %%/ms gives %.3f ms)"
          % (BAR, PRICE, BAR / PRICE, BAR / PRICE_NMPC))
    print()
    print("wrote %s" % os.path.relpath(OUT_CSV, ROOT))
    print("wrote %s" % os.path.relpath(OUT_JSON, ROOT))
    json.dump(out, open(OUT_JSON, "w"), indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
