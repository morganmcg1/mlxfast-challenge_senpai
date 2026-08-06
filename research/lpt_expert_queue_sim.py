#!/usr/bin/env python3
"""Step-0 gate for PR #142: rows-per-expert artifact + LPT makespan simulation.

Two jobs:

1. Emit a citable rows-per-expert artifact (CSV + JSON + schema README) from the
   already-measured `research/prefill-512-route-histogram.txt` probe so other
   experiments (e.g. PR #143 expert-slab dedup census) can join against it.

2. Simulate the makespan of the routed MoE gather-GEMM threadgroup grid on a
   40-core M5 Max under three schedules -- dense (today), compacted
   (empty-expert threadgroups removed) and LPT (compacted + longest-first) --
   and convert the makespan delta into score via the S elasticity
   (-1 ms of S = +0.362%).

Usage:
  python3 research/lpt_expert_queue_sim.py               # artifact + sim
  python3 research/lpt_expert_queue_sim.py --no-artifact # sim only
"""

import argparse
import ast
import csv
import json
import math
import os
import statistics

HIST = "research/prefill-512-route-histogram.txt"
OUTDIR = "research/artifacts"

# --- measured dispatch geometry (Vendor/mlx-swift .../metal/quantized.cpp) ----
# gather_qmm_rhs -> gather_qmm_rhs_nax (:1593) when is_nax_available().
# grid_dims(:1917) = ( N/bn , egroups , 1 ) on the expert-aligned path.
# egroups = darkbloom_expert_gather_groups() = 256 (:1379), xmajor_ct pinned 0.
# tiling variant 5 (:darkbloom_stage_bm128_variant) -> bm=64 wm=4 wn=1, SM=16.
EGROUPS = 256
BM = 64
BN = 64
BK = 64
GROUP_SIZE = 16  # nvfp4 gs16 -> 1 scale byte per 16 weights
BITS = 4

# The two routed gather calls per MoE layer, certified by the accept gate
# (quantized.cpp:1659-1671): (K==512 && N==2048) and (K==2048 && N==1024).
DISPATCHES = [("gate_up", 512, 2048), ("down", 2048, 1024)]

LAYERS_PER_FORWARD = 38
CORES = 40  # M5 Max
S_MS = 97.89475  # frontier prefill wall-clock, ms
SCORE_PER_MS = 0.362  # -1 ms of S = +0.362% on ns


def parse(path):
    layers = []
    for line in open(path):
        if "routehist" not in line or "counts=" not in line:
            continue
        counts = ast.literal_eval(line.split("counts=", 1)[1].strip())
        rows = int(line.split("rows=", 1)[1].split()[0])
        layers.append((rows, counts))
    return layers


def pct(sorted_vals, q):
    if not sorted_vals:
        return 0
    i = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[i]


def stats(vals):
    s = sorted(vals)
    nz = [v for v in s if v > 0]
    return {
        "n": len(s),
        "sum": sum(s),
        "zero_count": len(s) - len(nz),
        "zero_frac": (len(s) - len(nz)) / len(s) if s else 0.0,
        "min": s[0] if s else 0,
        "median": pct(s, 0.50),
        "mean": sum(s) / len(s) if s else 0.0,
        "p90": pct(s, 0.90),
        "p99": pct(s, 0.99),
        "max": s[-1] if s else 0,
        "stdev": statistics.pstdev(s) if len(s) > 1 else 0.0,
        "mean_nonzero": sum(nz) / len(nz) if nz else 0.0,
    }


def chunk_bytes(K):
    """DRAM bytes one BM-chunk threadgroup-iteration reads for its BN x K slice."""
    return BN * K * BITS // 8 + BN * K // GROUP_SIZE


def list_schedule(tasks, machines):
    """Greedy list scheduling: each task goes to the earliest-free machine.

    `tasks` is consumed in the given order, which is exactly how a GPU
    dispatches threadgroups to freeing execution slots.
    Returns the makespan.
    """
    import heapq

    heap = [0.0] * machines
    heapq.heapify(heap)
    for c in tasks:
        t = heapq.heappop(heap)
        heapq.heappush(heap, t + c)
    return max(heap)


def build_artifact(records, outdir):
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, "route-histogram-prefill512.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["layer_index", "expert_id", "rows", "chunks_bm64"])
        for li, (_rows, counts) in enumerate(records):
            for e, n in enumerate(counts):
                w.writerow([li, e, n, math.ceil(n / BM)])

    per_layer = []
    for li, (rows, counts) in enumerate(records):
        st = stats(counts)
        st["layer_index"] = li
        st["seq_rows"] = rows
        st["chunks_bm64"] = sum(math.ceil(n / BM) for n in counts)
        st["nonzero_experts"] = st["n"] - st["zero_count"]
        per_layer.append(st)

    pooled = stats([n for _r, c in records for n in c])
    pooled["chunks_bm64"] = sum(l["chunks_bm64"] for l in per_layer)
    pooled["nonzero_experts"] = pooled["n"] - pooled["zero_count"]
    pooled["max_over_mean_per_layer"] = statistics.mean(
        l["max"] / l["mean"] for l in per_layer
    )

    tiles = {}
    for name, K, N in DISPATCHES:
        ncols = N // BN
        dense_tgs = sum(ncols * EGROUPS for _ in records)
        compact_tgs = sum(ncols * l["nonzero_experts"] for l in per_layer)
        tiles[name] = {
            "K": K,
            "N": N,
            "column_tiles": ncols,
            "dense_threadgroups": dense_tgs,
            "compacted_threadgroups": compact_tgs,
            "launch_reduction_ratio": dense_tgs / compact_tgs,
            "chunk_threadgroup_iterations": ncols * pooled["chunks_bm64"],
            "chunk_dram_bytes": chunk_bytes(K),
        }

    doc = {
        "schema_version": 1,
        "source_probe": HIST,
        "source_commit": "3e8e435 (DARKBLOOM_ROUTE_HISTOGRAM, reverted; PR #11)",
        "host": "Apple M4 Pro (routing is model+prompt dependent, host independent)",
        "workload": "512-token prefill, 38 MoE layers, 256 experts, top-8",
        "warmup_forwards_dropped": 1,
        "layers": len(records),
        "geometry": {
            "expert_groups": EGROUPS,
            "BM": BM,
            "BN": BN,
            "BK": BK,
            "group_size": GROUP_SIZE,
            "bits": BITS,
            "note": "grid=(N/BN, egroups); one threadgroup per (expert, column tile)",
        },
        "pooled": pooled,
        "per_layer": per_layer,
        "dispatch_tiles": tiles,
    }
    json_path = os.path.join(outdir, "route-histogram-prefill512-stats.json")
    with open(json_path, "w") as f:
        json.dump(doc, f, indent=2)
    return csv_path, json_path, doc


def simulate(records, eps_ns_list, resident_list, t_gather_ms_list, verbose=True):
    """Return rows of {eps_ns, R, T_gather, delta_ms_*, delta_score_*}."""
    # Per-dispatch task lists in launch order (x fastest = all column tiles of
    # expert 0, then expert 1, ...). Cost unit: one BM-chunk of the SMALLEST
    # dispatch (gate_up, K=512). Down (K=2048) costs 4x per chunk.
    unit_bytes = chunk_bytes(512)

    dispatch_tasks = []  # (name, tasks_dense_template, weight)
    for name, K, N in DISPATCHES:
        ncols = N // BN
        w = chunk_bytes(K) / unit_bytes
        for _rows, counts in records:
            dense = []
            for e in range(EGROUPS):
                c = math.ceil(counts[e] / BM) * w  # 0 if empty -> replaced by eps
                for _ in range(ncols):
                    dense.append((e, c))
            dispatch_tasks.append((name, dense))

    total_work = sum(c for _n, d in dispatch_tasks for _e, c in d)

    n_dense = sum(len(d) for _n, d in dispatch_tasks)
    n_empty = sum(1 for _n, d in dispatch_tasks for _e, c in d if c == 0)
    print(
        f"per forward: dense TGs={n_dense}  empty TGs={n_empty} "
        f"({n_empty/n_dense*100:.2f}%)  total work={total_work:.0f} unit-chunks\n"
    )

    # Compaction's absolute saving is exactly n_empty * eps / C -- it is
    # independent of the chunk-time calibration, so the break-even eps is closed
    # form. LPT's saving is the only part that scales with T_gather.
    print("break-even eps (compaction alone, slot-bound model):")
    for R in resident_list:
        C = CORES * R
        print(
            f"  R={R:<2} C={C:<4}  >=1.0ms needs eps >= {C*1e6/n_empty:8.0f} ns"
            f"   |  >=3.0ms needs eps >= {3*C*1e6/n_empty:8.0f} ns"
        )
    print()

    rows = []
    for R in resident_list:
        C = CORES * R
        print(f"  ideal balanced lower bound at C={C}: {total_work/C:.1f} unit-chunks")
        for t_gather in t_gather_ms_list:
            # Calibrate: total_work unit-chunks executed on C slots in t_gather ms
            # under the ideal (perfectly balanced) schedule.
            unit_chunk_ms = t_gather * C / total_work
            unit_chunk_ns = unit_chunk_ms * 1e6
            for eps_ns in eps_ns_list:
                eps = eps_ns / unit_chunk_ns  # empty-TG cost in unit-chunks
                m_dense = m_compact = m_lpt = 0.0
                for _name, dense in dispatch_tasks:
                    dl = [c if c > 0 else eps for _e, c in dense]
                    cl = [c for _e, c in dense if c > 0]
                    m_dense += list_schedule(dl, C)
                    m_compact += list_schedule(cl, C)
                    m_lpt += list_schedule(sorted(cl, reverse=True), C)
                d_compact = (m_dense - m_compact) * unit_chunk_ms
                d_lpt = (m_dense - m_lpt) * unit_chunk_ms
                rows.append(
                    {
                        "R": R,
                        "C": C,
                        "t_gather_ms": t_gather,
                        "unit_chunk_ns": unit_chunk_ns,
                        "eps_ns": eps_ns,
                        "eps_units": eps,
                        "M_dense": m_dense,
                        "M_compact": m_compact,
                        "M_lpt": m_lpt,
                        "delta_ms_compact": d_compact,
                        "delta_ms_lpt": d_lpt,
                        "delta_ms_lpt_only": d_lpt - d_compact,
                        "score_pct_lpt": d_lpt * SCORE_PER_MS,
                    }
                )
                if verbose:
                    print(
                        f"R={R:<2} C={C:<4} T_gather={t_gather:>4.1f}ms "
                        f"chunk={unit_chunk_ns:7.1f}ns eps={eps_ns:>6.0f}ns  "
                        f"M_dense={m_dense:9.1f} M_compact={m_compact:9.1f} "
                        f"M_lpt={m_lpt:9.1f}  "
                        f"dms_compact={d_compact:6.3f} dms_lpt={d_lpt:6.3f} "
                        f"(+{d_lpt*SCORE_PER_MS:.3f}%)"
                    )
    return rows


def egroups_sweep(records, eps_ns_list, resident_list, t_gather_ms_list):
    """Compare the proposed device compaction against simply lowering egroups.

    `DARKBLOOM_EXPERT_GATHER_GROUPS` (quantized.cpp:1379) already lets one
    threadgroup serially own 256/egroups expert slots. A threadgroup is only
    empty when *every* slot it owns is empty, so the empty count falls
    superlinearly while the grid also shrinks -- both without new code.
    """
    unit_bytes = chunk_bytes(512)
    print("\n=== alternative: lower expert_groups (existing env knob) ===")
    for eg in (256, 128, 64, 32):
        per = EGROUPS // eg
        tasks_by_dispatch = []
        for name, K, N in DISPATCHES:
            ncols = N // BN
            w = chunk_bytes(K) / unit_bytes
            for _rows, counts in records:
                t = []
                for g in range(eg):
                    work = sum(
                        math.ceil(n / BM) for n in counts[g * per : (g + 1) * per]
                    )
                    for _ in range(ncols):
                        t.append(work * w)
                tasks_by_dispatch.append(t)
        n_tg = sum(len(t) for t in tasks_by_dispatch)
        n_empty = sum(1 for t in tasks_by_dispatch for c in t if c == 0)
        total = sum(c for t in tasks_by_dispatch for c in t)
        print(
            f"\negroups={eg:<4} slots/TG={per:<2} TGs/fwd={n_tg:<7} "
            f"empty={n_empty:<6} ({n_empty/n_tg*100:5.2f}%)  work={total:.0f}"
        )
        for R in resident_list:
            C = CORES * R
            for t_gather in t_gather_ms_list:
                unit_chunk_ms = t_gather * C / total
                for eps_ns in eps_ns_list:
                    eps = eps_ns / (unit_chunk_ms * 1e6)
                    m = sum(
                        list_schedule([c if c > 0 else eps for c in t], C)
                        for t in tasks_by_dispatch
                    )
                    ms = m * unit_chunk_ms
                    # ideal == t_gather by construction of unit_chunk_ms
                    empty_ms = n_empty * eps_ns * 1e-6 / C
                    # charging eps to *every* launch, not just empty ones
                    all_ms = n_tg * eps_ns * 1e-6 / C
                    print(
                        f"    R={R} C={C:<4} T={t_gather:>4.1f}ms eps={eps_ns:>5}ns "
                        f"-> makespan {ms:7.3f} ms  "
                        f"[empty {empty_ms:5.3f} + imbalance {ms-t_gather-empty_ms:5.3f}]"
                        f"  all-TG-charged {ms-empty_ms+all_ms:7.3f} ms"
                    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", default=HIST)
    ap.add_argument("--outdir", default=OUTDIR)
    ap.add_argument("--skip-forwards", type=int, default=1)
    ap.add_argument("--no-artifact", action="store_true")
    ap.add_argument("--no-sim", action="store_true")
    args = ap.parse_args()

    layers = parse(args.hist)
    records = layers[args.skip_forwards * LAYERS_PER_FORWARD :]
    print(f"parsed {len(layers)} layer records; using {len(records)} non-warmup\n")

    if not args.no_artifact:
        csv_path, json_path, doc = build_artifact(records, args.outdir)
        p = doc["pooled"]
        print(f"artifact: {csv_path}\n          {json_path}")
        print(
            f"pooled  n={p['n']} sum={p['sum']} zero={p['zero_count']} "
            f"({p['zero_frac']*100:.2f}%) min={p['min']} med={p['median']} "
            f"mean={p['mean']:.2f} p90={p['p90']} p99={p['p99']} max={p['max']} "
            f"stdev={p['stdev']:.2f}"
        )
        print(f"pooled  chunks_bm64={p['chunks_bm64']} "
              f"(re-read factor {p['chunks_bm64']/p['nonzero_experts']:.4f}) "
              f"max/mean per layer={p['max_over_mean_per_layer']:.2f}x")
        for name, t in doc["dispatch_tiles"].items():
            print(
                f"  {name:<8} K={t['K']:<5} N={t['N']:<5} cols={t['column_tiles']:<3} "
                f"dense_TG={t['dense_threadgroups']:<7} "
                f"compact_TG={t['compacted_threadgroups']:<7} "
                f"reduction={t['launch_reduction_ratio']:.4f}x "
                f"chunk_bytes={t['chunk_dram_bytes']}"
            )
        print()

    if not args.no_sim:
        simulate(
            records,
            eps_ns_list=[100, 300, 1000],
            resident_list=[1, 2, 4, 6],
            t_gather_ms_list=[25.0, 40.0, 60.0],
        )
        egroups_sweep(
            records,
            eps_ns_list=[300],
            resident_list=[2, 4],
            t_gather_ms_list=[40.0],
        )


if __name__ == "__main__":
    main()
